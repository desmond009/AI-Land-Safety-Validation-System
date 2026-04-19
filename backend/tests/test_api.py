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
    assert payload["risk_level"] == "HIGH"
    assert payload["risk_score"] >= 70
    assert any(flag.startswith("Inside water body") for flag in payload["flags"])
    assert "Final risk level is HIGH" in payload["explanation"]


def test_medium_risk_inside_forest_zone() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9640, "longitude": 77.5980},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "MEDIUM"
    assert 30 < payload["risk_score"] <= 70
    assert any(flag.startswith("Inside forest zone") for flag in payload["flags"])


def test_low_risk_far_from_sensitive_layers() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9900, "longitude": 77.6200},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "LOW"
    assert payload["risk_score"] <= 30
    assert payload["flags"] == []
