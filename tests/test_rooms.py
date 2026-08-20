from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_room():
    r = client.post("/v1/rooms", headers={"X-Rider-Name": "ana"})
    assert r.status_code == 200
    return r.json()["code"]


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
