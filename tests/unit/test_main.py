"""Test module for FastAPI application."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def test_app():
    """Create a test FastAPI application."""
    return create_app()


@pytest.fixture
def mock_mongodb_client():
    """Create a mock MongoDB client."""
    mock_client = MagicMock()
    mock_client.return_value = MagicMock()
    mock_client.return_value.__getitem__.return_value = MagicMock()
    return mock_client


class TestMainApplication:
    """Test cases for the main FastAPI application."""

    def test_root_endpoint(self, test_app):
        """Test root endpoint."""
        client = TestClient(test_app)
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome to Mansion Watch API"}

    def test_health_check_healthy(self, mock_mongodb_client, test_app):
        """Test health check endpoint when database is healthy."""
        # Set up the app state
        test_app.mongodb_client = mock_mongodb_client.return_value
        test_app.mongodb = mock_mongodb_client.return_value.__getitem__.return_value
        test_app.mongodb.command = AsyncMock()

        client = TestClient(test_app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "database": "connected",
        }

    def test_health_check_unhealthy(self, mock_mongodb_client, test_app):
        """Test health check endpoint when database is unhealthy."""
        # Mock the MongoDB client to raise an exception on ping
        mock_db = mock_mongodb_client.return_value.__getitem__.return_value
        mock_db.command = AsyncMock(side_effect=Exception("Connection failed"))

        # Set up the app state
        test_app.mongodb_client = mock_mongodb_client.return_value
        test_app.mongodb = mock_db

        client = TestClient(test_app)
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Connection failed",
        }

    def test_cors_middleware(self, test_app):
        """Test CORS middleware configuration."""
        client = TestClient(test_app)
        response = client.get("/", headers={"Origin": "http://example.com"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"

    def test_request_logging(self, caplog, test_app):
        """Test request logging middleware."""
        with caplog.at_level(logging.INFO):
            client = TestClient(test_app)
            response = client.get("/")
            assert response.status_code == 200
            assert any(
                "Method: GET Path: / Status: 200" in record.message
                for record in caplog.records
            )

    def test_process_time_header(self, test_app):
        """Test process time header is added to response."""
        client = TestClient(test_app)
        response = client.get("/")
        assert response.status_code == 200
        assert "x-process-time" in response.headers
        assert float(response.headers["x-process-time"]) >= 0
