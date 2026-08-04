"""Rodadas en grupo: sala efímera con código + fan-out de posiciones por WebSocket.

Las posiciones NUNCA tocan la base de datos — una rodada es efímera por diseño.
La sala muere sola cuando sale el último miembro."""

import secrets
import string

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..auth import Identity, get_identity

router = APIRouter(prefix="/v1/rooms", tags=["rooms"])

CODE_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "")
MAX_ROOM_SIZE = 20

# code → {rider_name → WebSocket}
_rooms: dict[str, dict[str, WebSocket]] = {}


@router.post("")
async def create_room(_: Identity = Depends(get_identity)) -> dict:
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    _rooms.setdefault(code, {})
    return {"code": code}


@router.websocket("/{code}/ws")
async def room_ws(websocket: WebSocket, code: str, rider: str = "anonimo") -> None:
    room = _rooms.get(code.upper())
    if room is None or len(room) >= MAX_ROOM_SIZE:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    rider = rider[:32]
    room[rider] = websocket
    try:
        while True:
            # La app manda {"lat":…,"lon":…,"speed_kmh":…}; se retransmite tal cual
            # con el nombre del emisor a todos los demás de la sala.
            payload = await websocket.receive_json()
            message = {"rider": rider, **{k: payload.get(k) for k in ("lat", "lon", "speed_kmh")}}
            for name, peer in list(room.items()):
                if name == rider:
                    continue
                try:
                    await peer.send_json(message)
                except Exception:
                    room.pop(name, None)
    except WebSocketDisconnect:
        pass
    finally:
        room.pop(rider, None)
        if not room:
            _rooms.pop(code.upper(), None)
