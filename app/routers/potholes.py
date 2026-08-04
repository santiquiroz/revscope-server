"""Huecos crowdsourced. Mismo dedupe de 30 m que la app hace localmente, pero
server-side y entre TODOS los usuarios: un golpe cerca de un hueco conocido
suma un reporte (confianza) en vez de duplicar el punto. Nunca se guarda quién
reportó ni su recorrido — solo el punto y la severidad."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Identity, get_identity
from ..db import get_pool

router = APIRouter(prefix="/v1/potholes", tags=["potholes"])

CLUSTER_RADIUS_M = 30.0


class PotholeReport(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    severity_g: float = Field(ge=1.0, le=10.0)


class Pothole(BaseModel):
    id: int
    lat: float
    lon: float
    severity_g: float
    reports: int


@router.post("", response_model=Pothole)
async def report(body: PotholeReport, _: Identity = Depends(get_identity)) -> Pothole:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM potholes
            WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
            LIMIT 1
            """,
            body.lon, body.lat, CLUSTER_RADIUS_M,
        )
        if row:
            updated = await conn.fetchrow(
                """
                UPDATE potholes
                SET reports = reports + 1,
                    severity_g = GREATEST(severity_g, $2),
                    last_report = now()
                WHERE id = $1
                RETURNING id, ST_Y(geom) AS lat, ST_X(geom) AS lon, severity_g, reports
                """,
                row["id"], body.severity_g,
            )
        else:
            updated = await conn.fetchrow(
                """
                INSERT INTO potholes (geom, severity_g)
                VALUES (ST_SetSRID(ST_MakePoint($1, $2), 4326), $3)
                RETURNING id, ST_Y(geom) AS lat, ST_X(geom) AS lon, severity_g, reports
                """,
                body.lon, body.lat, body.severity_g,
            )
    return Pothole(**dict(updated))


@router.get("", response_model=list[Pothole])
async def in_bbox(bbox: str) -> list[Pothole]:
    """bbox = minLon,minLat,maxLon,maxLat (el mismo viewport del mapa de la app)."""
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in bbox.split(","))
    except ValueError as e:
        raise HTTPException(400, "bbox debe ser minLon,minLat,maxLon,maxLat") from e
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, ST_Y(geom) AS lat, ST_X(geom) AS lon, severity_g, reports
        FROM potholes
        WHERE geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        LIMIT 2000
        """,
        min_lon, min_lat, max_lon, max_lat,
    )
    return [Pothole(**dict(r)) for r in rows]
