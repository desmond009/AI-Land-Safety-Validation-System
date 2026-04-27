import os

from fastapi.testclient import TestClient

os.environ["KGIS_USE_LIVE"] = "false"

from main import app

# Coordinates validated against real KGIS thematic data (Bengaluru district).


def test_high_risk_bannerghatta_forest_and_restricted() -> None:
    """Bannerghatta Biological Park: overlaps both forest and notified forest layers."""
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.8000, "longitude": 77.5760},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "HIGH"
    assert payload["risk_score"] >= 70
    assert any(flag.startswith("Inside forest zone") for flag in payload["flags"])
    assert any(flag.startswith("Inside restricted land") for flag in payload["flags"])
    assert "Overall risk level: HIGH" in payload["explanation"]

    ds = payload["data_source"]
    assert set(ds.keys()) == {"water", "forest", "restricted"}
    for meta in ds.values():
        assert meta["source"] in {"local_file", "live_kgis", "env_url", "cache"}
        # fetched_at may be None for local files with no mtime, otherwise ISO string
        assert meta["fetched_at"] is None or "T" in meta["fetched_at"]


def test_medium_risk_jakkuru_forest_plantation() -> None:
    """Jakkuru/Allalsandra plantation (Yelahanka range): inside a KGIS forest polygon."""
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 13.0719, "longitude": 77.5993},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "MEDIUM"
    assert 30 < payload["risk_score"] <= 70
    assert any(flag.startswith("Inside forest zone") for flag in payload["flags"])


def test_low_risk_mg_road_urban_core() -> None:
    """MG Road, central Bengaluru: dense urban area, no sensitive GIS layer overlap."""
    with TestClient(app) as client:
        response = client.post(
            "/analyze-location",
            json={"latitude": 12.9756, "longitude": 77.6097},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "LOW"
    assert payload["risk_score"] <= 30
    assert payload["flags"] == []
