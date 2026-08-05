"""Briefs de conducción de zona: combustible, peajes, restricciones y normas por lugar.

Modelo server-first: la app pregunta aquí PRIMERO (gratis, instantáneo). Si no hay
brief fresco para la zona, la app lo genera con su IA (web search) y lo CONTRIBUYE de
vuelta con POST — así el siguiente viajero lo recibe sin gastar IA. Los precios de
combustible caducan, así que un brief más viejo que el TTL se considera ausente.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Identity, get_identity
from ..db import get_pool

router = APIRouter(prefix="/v1/zone-brief", tags=["zone"])

# Los precios de combustible se mueven; un brief más viejo que esto se re-genera.
FRESH_TTL_HOURS = 7 * 24


def place_key(place: str, country: str | None) -> str:
    raw = f"{place.strip().lower()}|{(country or '').strip().lower()}"
    return re.sub(r"\s+", " ", raw)


class ZoneBriefIn(BaseModel):
    place: str = Field(min_length=1, max_length=120)
    country: str | None = Field(default=None, max_length=80)
    body: str = Field(min_length=1, max_length=2000)


class ZoneBriefOut(BaseModel):
    place: str
    country: str | None
    body: str
    age_hours: float
    contributors: int


@router.get("", response_model=ZoneBriefOut | None)
async def get_brief(place: str, country: str | None = None) -> ZoneBriefOut | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT place_label, country, body,
               EXTRACT(EPOCH FROM (now() - updated_at)) / 3600.0 AS age_hours,
               contributors
        FROM zone_briefs WHERE place_key = $1
        """,
        place_key(place, country),
    )
    if row is None or row["age_hours"] > FRESH_TTL_HOURS:
        return None
    return ZoneBriefOut(
        place=row["place_label"], country=row["country"], body=row["body"],
        age_hours=round(row["age_hours"], 1), contributors=row["contributors"],
    )


@router.post("", response_model=ZoneBriefOut)
async def contribute(body: ZoneBriefIn, _: Identity = Depends(get_identity)) -> ZoneBriefOut:
    if not body.place.strip():
        raise HTTPException(400, "place vacío")
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO zone_briefs (place_key, place_label, country, body, contributors, updated_at)
        VALUES ($1, $2, $3, $4, 1, now())
        ON CONFLICT (place_key) DO UPDATE
          SET body = EXCLUDED.body,
              place_label = EXCLUDED.place_label,
              country = EXCLUDED.country,
              contributors = zone_briefs.contributors + 1,
              updated_at = now()
        RETURNING place_label, country, body, 0.0 AS age_hours, contributors
        """,
        place_key(body.place, body.country), body.place.strip(), body.country, body.body.strip(),
    )
    return ZoneBriefOut(
        place=row["place_label"], country=row["country"], body=row["body"],
        age_hours=0.0, contributors=row["contributors"],
    )
