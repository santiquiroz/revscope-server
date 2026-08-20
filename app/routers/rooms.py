"""Rodadas en grupo: sala efímera con código + fan-out de posiciones por WebSocket.

Las posiciones NUNCA tocan la base de datos — una rodada es efímera por diseño.
La sala muere sola cuando sale el último miembro.

Protocolo v2: además de `pos` (compat con clientes viejos, sin `type`), soporta
`dest` (destino compartido) y `race` (arrancada sincronizada). El estado de sala
(`dest`/`race` vigentes) se guarda en memoria y se retransmite como `room_state`
a todo el que se conecta o pide `hello` — así un que llega tarde ve lo que ya
acordó el grupo."""

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..auth import Identity, get_identity, get_ws_identity
from ..config import Settings, get_settings

router = APIRouter(prefix="/v1/rooms", tags=["rooms"])

CODE_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "")
MAX_ROOM_SIZE = 20
WS_AUTH_FAILED_CLOSE_CODE = 4401
WS_ROOM_UNAVAILABLE_CLOSE_CODE = 4004

POS_FIELDS = ("lat", "lon", "speed_kmh", "heading_deg")
DEST_FIELDS = ("lat", "lon", "name")
RACE_FIELDS = ("action", "start_at_ms")

# code → {"members": {rider: WebSocket}, "state": {"dest": dict|None, "race": dict|None}}
_rooms: dict[str, dict] = {}


def _new_room_state() -> dict:
    return {"dest": None, "race": None}


@router.post("")
async def create_room(_: Identity = Depends(get_identity)) -> dict:
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    _rooms.setdefault(code, {"members": {}, "state": _new_room_state()})
    return {"code": code}


def _unique_rider_name(members: dict, base: str) -> str:
    if base not in members:
        return base
    n = 2
    while f"{base}-{n}" in members:
        n += 1
    return f"{base}-{n}"


def _room_state_message(room: dict, you: str) -> dict:
    return {"type": "room_state", "you": you, **room["state"]}


def _projected(payload: dict, fields: tuple) -> dict:
    return {k: payload.get(k) for k in fields}


def _build_pos_message(rider: str, payload: dict) -> dict:
    return {"type": "pos", "rider": rider, **_projected(payload, POS_FIELDS)}


def _build_dest_message(rider: str, payload: dict) -> dict:
    return {"type": "dest", "rider": rider, **_projected(payload, DEST_FIELDS)}


def _build_race_message(rider: str, payload: dict) -> dict:
    return {"type": "race", "rider": rider, **_projected(payload, RACE_FIELDS)}


def _apply_dest(room: dict, message: dict) -> None:
    room["state"]["dest"] = message


def _apply_race(room: dict, message: dict, payload: dict) -> None:
    room["state"]["race"] = message if payload.get("action") == "start" else None


def _dispatch(rider: str, room: dict, payload: dict) -> dict | None:
    mtype = payload.get("type", "pos")
    if mtype == "pos":
        return _build_pos_message(rider, payload)
    if mtype == "dest":
        message = _build_dest_message(rider, payload)
        _apply_dest(room, message)
        return message
    if mtype == "race":
        message = _build_race_message(rider, payload)
        _apply_race(room, message, payload)
        return message
    return None


ECHO_TO_SENDER_TYPES = ("dest", "race")


async def _broadcast(members: dict, sender: str, message: dict, include_sender: bool = False) -> None:
    for name, peer in list(members.items()):
        if name == sender and not include_sender:
            continue
        try:
            await peer.send_json(message)
        except Exception:
            members.pop(name, None)


def _room_unavailable(room: dict | None) -> bool:
    return room is None or len(room["members"]) >= MAX_ROOM_SIZE


async def _resolve_ws_rider_name(websocket: WebSocket, rider: str, settings: Settings) -> str | None:
    """Valida el handshake y devuelve el nombre final del member, o None si falla el auth.

    En modos autenticados (token/oidc) el nombre sale de la identidad validada, no
    del cliente — el `?rider=` de la query es solo el fallback autodeclarado del
    modo none, así un JWT válido no puede hacerse pasar por otro nombre.
    """
    try:
        identity = await get_ws_identity(websocket.headers, settings, rider)
    except HTTPException:
        await websocket.close(code=WS_AUTH_FAILED_CLOSE_CODE)
        return None
    return (identity.display_name or rider)[:32]


@router.websocket("/{code}/ws")
async def room_ws(
    websocket: WebSocket,
    code: str,
    rider: str = "anonimo",
    settings: Settings = Depends(get_settings),
) -> None:
    room = _rooms.get(code.upper())
    if _room_unavailable(room):
        await websocket.close(code=WS_ROOM_UNAVAILABLE_CLOSE_CODE)
        return

    rider = rider[:32]
    resolved_rider = await _resolve_ws_rider_name(websocket, rider, settings)
    if resolved_rider is None:
        return

    await websocket.accept()
    members = room["members"]
    rider = _unique_rider_name(members, resolved_rider)
    members[rider] = websocket
    try:
        await websocket.send_json(_room_state_message(room, rider))
        while True:
            payload = await websocket.receive_json()
            mtype = payload.get("type", "pos")
            if mtype == "hello":
                await websocket.send_json(_room_state_message(room, rider))
                continue
            message = _dispatch(rider, room, payload)
            if message is None:
                continue
            await _broadcast(members, rider, message, include_sender=mtype in ECHO_TO_SENDER_TYPES)
    except WebSocketDisconnect:
        pass
    finally:
        members.pop(rider, None)
        if not members:
            _rooms.pop(code.upper(), None)
