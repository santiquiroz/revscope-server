from contextlib import contextmanager

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import app.routers.rooms as rooms_module
from app.auth import Identity
from app.config import Settings, get_settings
from app.main import app

client = TestClient(app)

TOKEN_AUTH_SECRET = "secreto-de-prueba-123"


def _create_room():
    r = client.post("/v1/rooms", headers={"X-Rider-Name": "ana"})
    assert r.status_code == 200
    return r.json()["code"]


@contextmanager
def _token_auth_mode():
    """Fuerza auth_mode=token solo para el bloque `with` — la sala se crea
    afuera, en modo none, para no arrastrar la exigencia de Authorization
    al setup del test."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="token", auth_token=TOKEN_AUTH_SECRET
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_pos_legacy_sin_type_se_relayea():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()  # room_state inicial
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()  # room_state inicial
            a.send_json({"lat": 6.2, "lon": -75.5, "speed_kmh": 30.0})
            msg = b.receive_json()
            assert msg["rider"] == "ana" and msg["lat"] == 6.2


def test_dest_se_guarda_y_se_replayea_a_late_joiner():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        a.send_json({"type": "dest", "lat": 6.3, "lon": -75.6, "name": "Chilis"})
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            state = b.receive_json()
            assert state["type"] == "room_state"
            assert state["dest"]["name"] == "Chilis" and state["dest"]["rider"] == "ana"


def test_race_start_broadcast_y_estado():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()
            a.send_json({"type": "race", "action": "start", "start_at_ms": 123})
            msg = b.receive_json()
            assert msg["type"] == "race" and msg["action"] == "start" and msg["rider"] == "ana"


def test_hello_devuelve_room_state():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        a.send_json({"type": "hello", "v": 2})
        msg = a.receive_json()
        assert msg["type"] == "room_state"


def test_nombre_duplicado_gana_sufijo():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a2:
            a2.receive_json()
            a2.send_json({"lat": 1.0, "lon": 2.0, "speed_kmh": None})
            msg = a.receive_json()
            assert msg["rider"] == "ana-2"


def test_ws_sin_authorization_cierra_4401():
    code = _create_room()
    with _token_auth_mode():
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana"):
                pass
        assert exc_info.value.code == 4401


def test_ws_token_equivocado_cierra_4401():
    code = _create_room()
    with _token_auth_mode():
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/v1/rooms/{code}/ws?rider=ana",
                headers={"Authorization": "Bearer token-que-no-es"},
            ):
                pass
        assert exc_info.value.code == 4401


def test_ws_token_correcto_conecta_y_recibe_room_state():
    code = _create_room()
    with _token_auth_mode():
        with client.websocket_connect(
            f"/v1/rooms/{code}/ws?rider=ana",
            headers={"Authorization": f"Bearer {TOKEN_AUTH_SECRET}"},
        ) as a:
            msg = a.receive_json()
            assert msg["type"] == "room_state"


def test_ws_autenticado_usa_nombre_de_identidad_no_el_query_param(monkeypatch):
    async def _fake_get_ws_identity(headers, settings, self_declared_name):
        return Identity(subject="sub:carlos", display_name="carlos-real")

    monkeypatch.setattr(rooms_module, "get_ws_identity", _fake_get_ws_identity)
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=impostor") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()
            a.send_json({"lat": 1.0, "lon": 2.0, "speed_kmh": None})
            msg = b.receive_json()
            assert msg["rider"] == "carlos-real"


def test_dest_se_ecoa_al_emisor():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()
            a.send_json({"type": "dest", "lat": 6.3, "lon": -75.6, "name": "Chilis"})
            own = a.receive_json()
            other = b.receive_json()
            assert own == other
            assert own["type"] == "dest" and own["rider"] == "ana" and own["name"] == "Chilis"


def test_race_se_ecoa_al_emisor():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()
            a.send_json({"type": "race", "action": "start", "start_at_ms": 123})
            own = a.receive_json()
            other = b.receive_json()
            assert own == other
            assert own["type"] == "race" and own["rider"] == "ana" and own["action"] == "start"


def test_pos_no_se_ecoa_al_emisor():
    """receive_json() del test client no soporta timeout y bloquearía para
    siempre si esperáramos un eco que nunca llega — en cambio, mandamos un
    `hello` justo después del `pos` y verificamos que lo próximo que le llega
    a la propia conexión es la respuesta al hello (room_state), no un eco de
    pos colado antes en la cola."""
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=beto") as b:
            b.receive_json()
            a.send_json({"lat": 6.2, "lon": -75.5, "speed_kmh": 30.0})
            msg = b.receive_json()
            assert msg["rider"] == "ana"
            a.send_json({"type": "hello", "v": 2})
            next_on_a = a.receive_json()
            assert next_on_a["type"] == "room_state"


def test_room_state_trae_you():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        state = a.receive_json()
        assert state["you"] == "ana"


def test_room_state_you_usa_nombre_con_sufijo_de_duplicado():
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a:
        a.receive_json()
        with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=ana") as a2:
            state = a2.receive_json()
            assert state["you"] == "ana-2"


def test_room_state_you_usa_display_name_de_identidad_autenticada(monkeypatch):
    async def _fake_get_ws_identity(headers, settings, self_declared_name):
        return Identity(subject="sub:carlos", display_name="carlos-real")

    monkeypatch.setattr(rooms_module, "get_ws_identity", _fake_get_ws_identity)
    code = _create_room()
    with client.websocket_connect(f"/v1/rooms/{code}/ws?rider=impostor") as a:
        state = a.receive_json()
        assert state["you"] == "carlos-real"
