import sys
import os

# Add backend/ to sys.path so imports like `from vector_store import VectorStore` resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock
from models import Course, Lesson, CourseChunk
from vector_store import VectorStore


@pytest.fixture
def vector_store(tmp_path):
    """Real ChromaDB in a temp directory — isolated per test."""
    chroma_path = str(tmp_path / "chroma")
    return VectorStore(
        chroma_path=chroma_path,
        embedding_model="all-MiniLM-L6-v2",
        max_results=5,
    )


@pytest.fixture
def minimal_course():
    """A well-formed Course with two lessons and no None fields."""
    return Course(
        title="Test Python Course",
        course_link="https://example.com/python",
        instructor="Jane Smith",
        lessons=[
            Lesson(lesson_number=1, title="Introduction", lesson_link="https://example.com/python/1"),
            Lesson(lesson_number=2, title="Core Concepts", lesson_link="https://example.com/python/2"),
        ],
    )


@pytest.fixture
def minimal_chunks(minimal_course):
    """Three CourseChunks with integer lesson_numbers — no None values."""
    return [
        CourseChunk(
            content="Python is a high-level programming language known for its readability.",
            course_title=minimal_course.title,
            lesson_number=1,
            chunk_index=0,
        ),
        CourseChunk(
            content="Variables store data values. Functions group reusable code blocks together.",
            course_title=minimal_course.title,
            lesson_number=2,
            chunk_index=1,
        ),
        CourseChunk(
            content="Loops allow repeating code. Lists store multiple items in a single variable.",
            course_title=minimal_course.title,
            lesson_number=2,
            chunk_index=2,
        ),
    ]


@pytest.fixture
def mock_rag_config(tmp_path):
    """MagicMock config with all required fields for RAGSystem."""
    config = MagicMock()
    config.CHROMA_PATH = str(tmp_path / "chroma")
    config.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    config.MAX_RESULTS = 5
    config.MAX_HISTORY = 2
    config.ANTHROPIC_API_KEY = "fake-key-for-testing"
    config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
    config.CHUNK_SIZE = 800
    config.CHUNK_OVERLAP = 100
    return config
