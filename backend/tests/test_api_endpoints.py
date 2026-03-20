"""
API endpoint tests for the RAG chatbot.

Uses the `api_client` fixture from conftest.py, which spins up a minimal
FastAPI app (no static-file mount) backed by a mock RAGSystem. This avoids
the frontend/ directory dependency that makes importing app.py directly fail
in CI / test environments.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_returns_200_with_valid_query(self, api_client):
        response = api_client.post("/api/query", json={"query": "What is Python?"})
        assert response.status_code == 200

    def test_response_contains_required_fields(self, api_client):
        response = api_client.post("/api/query", json={"query": "Tell me about FastAPI"})
        body = response.json()
        assert "answer" in body
        assert "sources" in body
        assert "session_id" in body

    def test_answer_is_string(self, api_client):
        response = api_client.post("/api/query", json={"query": "What is a list?"})
        assert isinstance(response.json()["answer"], str)

    def test_sources_is_list(self, api_client):
        response = api_client.post("/api/query", json={"query": "Explain functions"})
        assert isinstance(response.json()["sources"], list)

    def test_new_session_id_assigned_when_not_provided(self, api_client):
        response = api_client.post("/api/query", json={"query": "Hello"})
        body = response.json()
        assert body["session_id"]  # non-empty

    def test_provided_session_id_is_preserved(self, api_client):
        session_id = "my-existing-session"
        response = api_client.post(
            "/api/query",
            json={"query": "Continue the conversation", "session_id": session_id},
        )
        assert response.json()["session_id"] == session_id

    def test_missing_query_field_returns_422(self, api_client):
        response = api_client.post("/api/query", json={})
        assert response.status_code == 422

    def test_rag_error_returns_500(self, api_client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("DB unavailable")
        response = api_client.post("/api/query", json={"query": "Will this explode?"})
        assert response.status_code == 500
        mock_rag_system.query.side_effect = None  # restore for subsequent tests


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:
    def test_returns_200(self, api_client):
        response = api_client.get("/api/courses")
        assert response.status_code == 200

    def test_response_contains_required_fields(self, api_client):
        body = api_client.get("/api/courses").json()
        assert "total_courses" in body
        assert "course_titles" in body

    def test_total_courses_is_integer(self, api_client):
        body = api_client.get("/api/courses").json()
        assert isinstance(body["total_courses"], int)

    def test_course_titles_is_list(self, api_client):
        body = api_client.get("/api/courses").json()
        assert isinstance(body["course_titles"], list)

    def test_course_titles_match_mock_data(self, api_client):
        body = api_client.get("/api/courses").json()
        assert body["total_courses"] == 2
        assert "Python Basics" in body["course_titles"]
        assert "Advanced FastAPI" in body["course_titles"]

    def test_analytics_error_returns_500(self, api_client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("Chroma offline")
        response = api_client.get("/api/courses")
        assert response.status_code == 500
        mock_rag_system.get_course_analytics.side_effect = None


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id}
# ---------------------------------------------------------------------------

class TestDeleteSessionEndpoint:
    def test_returns_200_and_cleared_status(self, api_client):
        response = api_client.delete("/api/session/abc-123")
        assert response.status_code == 200
        assert response.json() == {"status": "cleared"}

    def test_delegates_to_session_manager(self, api_client, mock_rag_system):
        api_client.delete("/api/session/xyz-789")
        mock_rag_system.session_manager.clear_session.assert_called_once_with("xyz-789")
