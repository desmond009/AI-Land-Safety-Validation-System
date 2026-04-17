from fastapi.testclient import TestClient

from main import app


def test_high_risk_inside_water_and_near_restricted() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9720, "longitude": 77.5955},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "High"
    assert payload["risk_score"] >= 70
    assert "Inside water body" in payload["flags"]
    assert "Final risk level is High" in payload["explanation"]


def test_medium_risk_inside_forest_zone() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9640, "longitude": 77.5980},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "Medium"
    assert 30 < payload["risk_score"] <= 70
    assert "Inside forest zone" in payload["flags"]


def test_low_risk_far_from_sensitive_layers() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9900, "longitude": 77.6200},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "Low"
    assert payload["risk_score"] <= 30
    assert payload["flags"] == []
