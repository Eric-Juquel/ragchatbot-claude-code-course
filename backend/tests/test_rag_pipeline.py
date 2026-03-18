"""
Integration tests for the full RAG pipeline.

Uses real ChromaDB (temp dir) + real DocumentProcessor.
AIGenerator is mocked to avoid real API calls.

Expected failures (revealing bugs):
- test_add_course_metadata_with_none_fields_raises: PASSES with pytest.raises —
  confirms Bug 1 at the pipeline level.
- test_add_course_content_with_none_lesson_number_raises: PASSES with pytest.raises —
  confirms Bug 2 at the pipeline level.
- test_last_lesson_chunk_context_prefix_inconsistency: PASSES and documents Bug 4
  (inconsistent prefix on last lesson chunks vs other lessons).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from document_processor import DocumentProcessor
from vector_store import VectorStore
from rag_system import RAGSystem
from models import Course, Lesson, CourseChunk


# ---------------------------------------------------------------------------
# File fixtures — synthetic course documents
# ---------------------------------------------------------------------------

@pytest.fixture
def test_course_file(tmp_path):
    """Well-formed course file: has instructor, course_link, and 2 lessons."""
    content = (
        "Course Title: Integration Test Course\n"
        "Course Link: https://example.com/course\n"
        "Course Instructor: Test Author\n"
        "\n"
        "Lesson 0: Introduction\n"
        "Lesson Link: https://example.com/lesson0\n"
        "This is the introduction to the course. It covers the basics of the subject matter.\n"
        "Students will learn foundational concepts and prepare for advanced topics.\n"
        "\n"
        "Lesson 1: Core Concepts\n"
        "Lesson Link: https://example.com/lesson1\n"
        "This lesson explains the core concepts. Variables store data values.\n"
        "Functions group reusable code blocks. Classes define object blueprints.\n"
        "Understanding these concepts is essential for writing good software.\n"
    )
    path = tmp_path / "test_course.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def test_course_file_no_instructor(tmp_path):
    """Course file missing the 'Course Instructor:' line — triggers Bug 1."""
    content = (
        "Course Title: No Instructor Course\n"
        "Course Link: https://example.com/course\n"
        "\n"
        "Lesson 1: Only Lesson\n"
        "Lesson Link: https://example.com/lesson1\n"
        "Some lesson content here for testing purposes.\n"
    )
    path = tmp_path / "no_instructor.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def test_course_file_no_lessons(tmp_path):
    """Course file with NO lesson markers — triggers the fallback path in
    document_processor.py lines 245-257, producing lesson_number=None (Bug 2)."""
    content = (
        "Course Title: No Lessons Course\n"
        "Course Link: https://example.com/course\n"
        "Course Instructor: Someone\n"
        "\n"
        "This is plain content with no lesson markers.\n"
        "It will be treated as a single chunk with no lesson number.\n"
        "The lesson_number field will be None, causing Bug 2.\n"
    )
    path = tmp_path / "no_lessons.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def test_course_file_multi_chunk_lessons(tmp_path):
    """Course file designed to produce multiple chunks per lesson (for Bug 4 test)."""
    # 300-char sentences so a small chunk_size forces multiple chunks
    sentence = "This is a sentence that contains enough words to help fill a chunk boundary. "
    lesson_content = (sentence * 6).strip()

    content = (
        "Course Title: Multi Chunk Course\n"
        "Course Link: https://example.com/course\n"
        "Course Instructor: Author\n"
        "\n"
        f"Lesson 0: First Lesson\n"
        f"Lesson Link: https://example.com/lesson0\n"
        f"{lesson_content}\n"
        "\n"
        f"Lesson 1: Last Lesson\n"
        f"Lesson Link: https://example.com/lesson1\n"
        f"{lesson_content}\n"
    )
    path = tmp_path / "multi_chunk.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# DocumentProcessor tests
# ---------------------------------------------------------------------------

class TestDocumentProcessor:
    def test_parses_standard_format(self, test_course_file):
        """Well-formed course file produces correct Course and CourseChunk objects.
        All lesson_numbers must be integers (not None)."""
        dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
        course, chunks = dp.process_course_document(test_course_file)

        assert course.title == "Integration Test Course"
        assert course.instructor == "Test Author"
        assert course.course_link == "https://example.com/course"
        assert len(course.lessons) == 2
        assert course.lessons[0].lesson_number == 0
        assert course.lessons[1].lesson_number == 1

        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk.lesson_number, int), (
                f"lesson_number should be int, got {chunk.lesson_number!r}"
            )

    def test_missing_instructor_produces_none(self, test_course_file_no_instructor):
        """When 'Course Instructor:' line is absent, course.instructor should be None.
        This is the precondition for Bug 1."""
        dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
        course, _ = dp.process_course_document(test_course_file_no_instructor)

        assert course.instructor is None, (
            "Expected instructor=None when header is missing"
        )

    def test_no_lessons_produces_none_lesson_numbers(self, test_course_file_no_lessons):
        """When no 'Lesson N:' markers are found, the fallback path is taken and
        chunk.lesson_number is None — the precondition for Bug 2."""
        dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
        course, chunks = dp.process_course_document(test_course_file_no_lessons)

        assert len(chunks) > 0, "Fallback path should still produce chunks"
        none_chunks = [c for c in chunks if c.lesson_number is None]
        assert len(none_chunks) > 0, (
            "Expected at least one chunk with lesson_number=None from fallback path"
        )


# ---------------------------------------------------------------------------
# VectorStore metadata constraint tests (Bug 1 & 2 at pipeline level)
# ---------------------------------------------------------------------------

class TestVectorStoreMetadataConstraints:
    def test_add_course_metadata_with_none_instructor_succeeds(
        self, vector_store, test_course_file_no_instructor
    ):
        """BUG 1 FIXED (pipeline level): Processes a no-instructor file; after the fix,
        add_course_metadata() coerces None to '' and stores without raising."""
        dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
        course, _ = dp.process_course_document(test_course_file_no_instructor)

        assert course.instructor is None  # Confirm precondition

        # Should NOT raise after the fix
        vector_store.add_course_metadata(course)
        assert vector_store.get_course_count() == 1

    def test_add_course_content_with_none_lesson_number_succeeds(
        self, vector_store, test_course_file_no_lessons
    ):
        """BUG 2 FIXED (pipeline level): Processes a no-lessons file; after the fix,
        add_course_content() coerces None to -1 and stores without raising."""
        dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
        course, chunks = dp.process_course_document(test_course_file_no_lessons)

        course.instructor = "Patched Author"
        vector_store.add_course_metadata(course)

        none_chunks = [c for c in chunks if c.lesson_number is None]
        assert len(none_chunks) > 0  # Confirm precondition

        # Should NOT raise after the fix
        vector_store.add_course_content(chunks)
        results = vector_store.search(query="plain content")
        assert not results.is_empty()


# ---------------------------------------------------------------------------
# Full RAGSystem pipeline tests (mocked AIGenerator)
# ---------------------------------------------------------------------------

class TestRAGSystemPipeline:
    def test_chunks_added_after_add_course_document(self, mock_rag_config, test_course_file):
        """add_course_document() on a well-formed file stores data in ChromaDB.
        Verifies get_course_count()==1 and chunk_count>0."""
        with patch("anthropic.Anthropic"):
            rag = RAGSystem(mock_rag_config)
            course, chunk_count = rag.add_course_document(test_course_file)

        assert course is not None
        assert course.title == "Integration Test Course"
        assert chunk_count > 0
        assert rag.vector_store.get_course_count() == 1

    def test_query_returns_response_and_sources(self, mock_rag_config, test_course_file):
        """Full pipeline: ingest one document, then call query() with mocked AIGenerator.
        Verifies that the return is (str, list)."""
        with patch("anthropic.Anthropic"):
            rag = RAGSystem(mock_rag_config)
            rag.add_course_document(test_course_file)

            # Mock the AI generator to avoid real API calls
            rag.ai_generator.generate_response = MagicMock(return_value="Mocked answer")

            session_id = rag.session_manager.create_session()
            response, sources = rag.query("What are the core concepts?", session_id=session_id)

        assert isinstance(response, str)
        assert response == "Mocked answer"
        assert isinstance(sources, list)

    def test_session_history_updated_after_query(self, mock_rag_config, test_course_file):
        """After query(), session history contains the original query text."""
        with patch("anthropic.Anthropic"):
            rag = RAGSystem(mock_rag_config)
            rag.add_course_document(test_course_file)
            rag.ai_generator.generate_response = MagicMock(return_value="Answer")

            session_id = rag.session_manager.create_session()
            rag.query("Tell me about variables", session_id=session_id)

        history = rag.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "Tell me about variables" in history

    def test_query_without_session_still_returns_response(self, mock_rag_config, test_course_file):
        """query() works even without a session_id (history is None, no crash)."""
        with patch("anthropic.Anthropic"):
            rag = RAGSystem(mock_rag_config)
            rag.add_course_document(test_course_file)
            rag.ai_generator.generate_response = MagicMock(return_value="No session answer")

            response, sources = rag.query("What is this course about?", session_id=None)

        assert response == "No session answer"


# ---------------------------------------------------------------------------
# Bug 4: Inconsistent last-lesson chunk prefix
# ---------------------------------------------------------------------------

class TestChunkContextPrefixInconsistency:
    def test_all_lessons_have_consistent_chunk_prefix(
        self, test_course_file_multi_chunk_lessons
    ):
        """BUG 4 FIXED: After the fix, all lessons (including the last one) apply the
        same rule: only the first chunk gets 'Lesson N content:' prefix; subsequent
        chunks have no prefix. Verifies consistency across all lessons."""
        dp = DocumentProcessor(chunk_size=200, chunk_overlap=0)
        course, chunks = dp.process_course_document(test_course_file_multi_chunk_lessons)

        lesson_0_chunks = [c for c in chunks if c.lesson_number == 0]
        lesson_1_chunks = [c for c in chunks if c.lesson_number == 1]

        assert len(lesson_0_chunks) >= 1, "Need chunks from lesson 0"
        assert len(lesson_1_chunks) >= 1, "Need chunks from lesson 1"

        # Both lessons: only the first chunk should be prefixed
        for lesson_num, lesson_chunks in [(0, lesson_0_chunks), (1, lesson_1_chunks)]:
            assert lesson_chunks[0].content.startswith(f"Lesson {lesson_num} content:"), (
                f"First chunk of lesson {lesson_num} should start with 'Lesson {lesson_num} content:', "
                f"got: {lesson_chunks[0].content[:80]!r}"
            )
            for subsequent_chunk in lesson_chunks[1:]:
                assert not subsequent_chunk.content.startswith("Lesson"), (
                    f"Non-first chunk of lesson {lesson_num} should NOT have lesson prefix, "
                    f"got: {subsequent_chunk.content[:80]!r}"
                )
                assert not subsequent_chunk.content.startswith("Course"), (
                    f"Non-first chunk of lesson {lesson_num} should NOT have course prefix, "
                    f"got: {subsequent_chunk.content[:80]!r}"
                )
