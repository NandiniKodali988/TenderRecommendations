from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


# --- /health ---

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- /recommendations/{id}/feedback ---

def test_feedback_helpful_accepted():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": "rec-1"}]

    with patch("api.get_client", return_value=mock_db), \
         patch("api.save_feedback") as mock_save:
        response = client.post("/recommendations/rec-1/feedback", json={"value": 1})

    assert response.status_code == 200
    assert response.json()["feedback"] == 1
    mock_save.assert_called_once()


def test_feedback_not_helpful_accepted():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": "rec-1"}]

    with patch("api.get_client", return_value=mock_db), \
         patch("api.save_feedback"):
        response = client.post("/recommendations/rec-1/feedback", json={"value": -1})

    assert response.status_code == 200
    assert response.json()["feedback"] == -1


def test_feedback_invalid_value_rejected():
    response = client.post("/recommendations/rec-1/feedback", json={"value": 2})
    assert response.status_code == 422


def test_feedback_zero_rejected():
    response = client.post("/recommendations/rec-1/feedback", json={"value": 0})
    assert response.status_code == 422


def test_feedback_recommendation_not_found():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    with patch("api.get_client", return_value=mock_db):
        response = client.post("/recommendations/nonexistent/feedback", json={"value": 1})

    assert response.status_code == 404


# --- /profiles/{id} ---

def test_get_profile_not_found():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    with patch("api.get_client", return_value=mock_db):
        response = client.get("/profiles/nonexistent-id")

    assert response.status_code == 404
