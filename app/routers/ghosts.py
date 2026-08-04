"""Fantasmas compartidos: la mejor vuelta de cada rider por pista. Una "pista"
se identifica por la cercanía de su línea de meta (300 m) — sin registro manual
de circuitos. Subir es opt-in explícito por vuelta desde la app."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Identity, get_identity
from ..db import get_pool

router = APIRouter(prefix="/v1/ghosts", tags=["ghosts"])

TRACK_RADIUS_M = 300.0
MAX_POINTS = 20_000


class GhostUpload(BaseModel):
    finish_lat: float = Field(ge=-90, le=90)
    finish_lon: float = Field(ge=-180, le=180)
    time_ms: int = Field(gt=0)
    # [[lat, lon, t_ms], …] relativo al cruce de meta
    points: list[list[float]] = Field(max_length=MAX_POINTS)


class GhostSummary(BaseModel):
    id: int
    rider: str
    time_ms: int


@router.post("", response_model=GhostSummary)
async def upload(body: GhostUpload, identity: Identity = Depends(get_identity)) -> GhostSummary:
    import json

    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO ghosts (finish_geom, rider, time_ms, points_json)
        VALUES (ST_SetSRID(ST_MakePoint($1, $2), 4326), $3, $4, $5::jsonb)
        RETURNING id, rider, time_ms
        """,
        body.finish_lon, body.finish_lat, identity.display_name, body.time_ms, json.dumps(body.points),
    )
    return GhostSummary(**dict(row))


@router.get("", response_model=list[GhostSummary])
async def for_track(near: str) -> list[GhostSummary]:
    """near = lat,lon de la línea de meta — devuelve las vueltas de esa pista, mejores primero."""
    try:
        lat, lon = (float(p) for p in near.split(","))
    except ValueError as e:
        raise HTTPException(400, "near debe ser lat,lon") from e
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, rider, time_ms FROM ghosts
        WHERE ST_DWithin(finish_geom::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
        ORDER BY time_ms ASC
        LIMIT 50
        """,
        lon, lat, TRACK_RADIUS_M,
    )
    return [GhostSummary(**dict(r)) for r in rows]


@router.get("/{ghost_id}")
async def download(ghost_id: int) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, rider, time_ms, points_json FROM ghosts WHERE id = $1", ghost_id
    )
    if not row:
        raise HTTPException(404, "Fantasma no encontrado")
    return {"id": row["id"], "rider": row["rider"], "time_ms": row["time_ms"], "points": row["points_json"]}
