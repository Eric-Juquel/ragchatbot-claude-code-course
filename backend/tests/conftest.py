import sys
import os

# Add backend/ to sys.path so imports like `from vector_store import VectorStore` resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
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


# ---------------------------------------------------------------------------
# API fixtures — a minimal FastAPI app that mirrors app.py endpoints
# without mounting static files (which don't exist in the test environment).
# ---------------------------------------------------------------------------

class _QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class _QueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    session_id: str


class _CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


@pytest.fixture
def mock_rag_system():
    """Pre-configured MagicMock that mimics RAGSystem's public interface."""
    rag = MagicMock()
    rag.session_manager.create_session.return_value = "test-session-id"
    rag.query.return_value = ("Mocked answer", [{"title": "Test Course", "url": "https://example.com"}])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Python Basics", "Advanced FastAPI"],
    }
    return rag


@pytest.fixture
def api_client(mock_rag_system):
    """TestClient for a minimal FastAPI app that mirrors app.py without static files."""
    test_app = FastAPI()

    @test_app.post("/api/query", response_model=_QueryResponse)
    async def query_documents(request: _QueryRequest):
        try:
            session_id = request.session_id or mock_rag_system.session_manager.create_session()
            answer, sources = mock_rag_system.query(request.query, session_id)
            return _QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @test_app.delete("/api/session/{session_id}")
    async def delete_session(session_id: str):
        mock_rag_system.session_manager.clear_session(session_id)
        return {"status": "cleared"}

    @test_app.get("/api/courses", response_model=_CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return _CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return TestClient(test_app)
