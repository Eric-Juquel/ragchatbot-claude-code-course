"""
Unit tests for CourseSearchTool.execute() and VectorStore data loading.

Expected failures (revealing bugs):
- test_empty_result_returns_proper_message: FAILS — Bug 3: raw ChromaDB error string
  returned instead of friendly "No relevant content found" message.
- test_add_course_metadata_with_none_instructor_raises: PASSES with pytest.raises —
  confirms Bug 1 (ChromaDB rejects None metadata).
- test_add_course_content_with_none_lesson_number_raises: PASSES with pytest.raises —
  confirms Bug 2 (ChromaDB rejects None lesson_number).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from models import Course, Lesson, CourseChunk
from vector_store import VectorStore
from search_tools import CourseSearchTool


class TestCourseSearchToolHappyPath:
    def test_basic_search_returns_formatted_results(self, vector_store, minimal_course, minimal_chunks):
        """Seeds one course and performs an unfiltered search.
        Verifies the result contains the course title header [Course - Lesson N].
        Baseline happy path."""
        vector_store.add_course_metadata(minimal_course)
        vector_store.add_course_content(minimal_chunks)

        tool = CourseSearchTool(vector_store)
        result = tool.execute(query="Python programming language")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "[Test Python Course" in result

    def test_search_with_course_name_filter(self, vector_store, minimal_course, minimal_chunks):
        """Seeds two courses; filters by one course name.
        Verifies results come only from the targeted course."""
        # Add first course
        vector_store.add_course_metadata(minimal_course)
        vector_store.add_course_content(minimal_chunks)

        # Add a second course
        other_course = Course(
            title="Advanced JavaScript",
            course_link="https://example.com/js",
            instructor="John Doe",
            lessons=[Lesson(lesson_number=1, title="JS Basics", lesson_link="https://example.com/js/1")],
        )
        other_chunks = [
            CourseChunk(
                content="JavaScript is a scripting language used in web browsers and Node.js.",
                course_title="Advanced JavaScript",
                lesson_number=1,
                chunk_index=0,
            )
        ]
        vector_store.add_course_metadata(other_course)
        vector_store.add_course_content(other_chunks)

        tool = CourseSearchTool(vector_store)
        result = tool.execute(query="programming language concepts", course_name="Test Python Course")

        assert "Test Python Course" in result
        assert "Advanced JavaScript" not in result

    def test_search_with_lesson_number_filter(self, vector_store, minimal_course, minimal_chunks):
        """Filters search to lesson_number=1.
        Verifies header contains 'Lesson 1' and not lesson 2 content."""
        vector_store.add_course_metadata(minimal_course)
        vector_store.add_course_content(minimal_chunks)

        tool = CourseSearchTool(vector_store)
        result = tool.execute(query="introduction programming", lesson_number=1)

        assert isinstance(result, str)
        assert "Lesson 1" in result

    def test_sources_are_tracked_in_last_sources(self, vector_store, minimal_course, minimal_chunks):
        """After a successful search, tool.last_sources should contain
        dicts with 'label' and 'url' keys for UI attribution."""
        vector_store.add_course_metadata(minimal_course)
        vector_store.add_course_content(minimal_chunks)

        tool = CourseSearchTool(vector_store)
        tool.execute(query="Python variables and loops")

        assert len(tool.last_sources) > 0
        for source in tool.last_sources:
            assert "label" in source
            assert "url" in source


class TestCourseSearchToolEdgeCases:
    def test_empty_result_returns_proper_message(self, vector_store):
        """Searches an empty collection (no data seeded).
        Should return the friendly 'No relevant content found' message.

        BUG 3: This test FAILS because ChromaDB raises NotEnoughElementsException
        for n_results > collection size. The exception IS caught in VectorStore.search()
        and stored in results.error, but CourseSearchTool.execute() returns results.error
        (raw ChromaDB error string) instead of the friendly message.
        """
        tool = CourseSearchTool(vector_store)
        result = tool.execute(query="anything")

        assert isinstance(result, str)
        # This assertion will FAIL — revealing Bug 3
        assert "No relevant content found" in result, (
            f"Expected friendly message but got: {result!r}"
        )

    def test_error_for_unknown_course_name(self, vector_store, minimal_course, minimal_chunks):
        """Searching with a course_name that cannot be resolved returns an error string,
        not an exception. Tests the _resolve_course_name fallback path."""
        vector_store.add_course_metadata(minimal_course)
        vector_store.add_course_content(minimal_chunks)

        tool = CourseSearchTool(vector_store)
        result = tool.execute(query="something", course_name="NonExistentCourse")

        # Should return an error string, not raise
        assert isinstance(result, str)
        assert len(result) > 0


class TestChromaDBMetadataConstraints:
    def test_add_course_metadata_with_none_instructor_succeeds(self, vector_store):
        """BUG 1 FIXED: add_course_metadata() now coerces None to '' before storing.
        A course with instructor=None should be stored without raising."""
        course = Course(
            title="Null Instructor Course",
            course_link="https://example.com",
            instructor=None,  # Previously triggered Bug 1
            lessons=[],
        )
        # Should NOT raise after the fix
        vector_store.add_course_metadata(course)
        assert vector_store.get_course_count() == 1

    def test_add_course_metadata_with_none_course_link_succeeds(self, vector_store):
        """BUG 1 FIXED: course_link=None is coerced to '' before storing."""
        course = Course(
            title="No Link Course",
            course_link=None,  # Previously triggered Bug 1
            instructor="Someone",
            lessons=[],
        )
        vector_store.add_course_metadata(course)
        assert vector_store.get_course_count() == 1

    def test_add_course_content_with_none_lesson_number_succeeds(self, vector_store, minimal_course):
        """BUG 2 FIXED: lesson_number=None is coerced to -1 before storing.
        Chunks from the no-lesson fallback path should be stored without raising."""
        vector_store.add_course_metadata(minimal_course)

        chunk = CourseChunk(
            content="Some fallback content without a lesson number.",
            course_title=minimal_course.title,
            lesson_number=None,  # Previously triggered Bug 2
            chunk_index=0,
        )
        # Should NOT raise after the fix
        vector_store.add_course_content([chunk])
        # Verify it was stored (stored with lesson_number=-1)
        results = vector_store.search(query="fallback content")
        assert not results.is_empty()
