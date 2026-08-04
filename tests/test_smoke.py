"""Smoke sin base de datos: el árbol de rutas y la config cargan bien."""

from app.config import Settings
from app.main import app


def test_routes_registered():
    # app.openapi() aplana los routers incluidos sin disparar el lifespan (ni la DB)
    paths = app.openapi()["paths"]
    assert "/healthz" in paths
    assert "/v1/potholes" in paths
    assert "/v1/rooms" in paths
    assert "/v1/ghosts" in paths
    assert "/v1/ghosts/{ghost_id}" in paths


def test_default_settings_are_lan_friendly():
    s = Settings()
    assert s.auth_mode == "none"
    assert s.oidc_audience == "revscope"
