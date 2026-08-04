import asyncpg

from .config import get_settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS potholes (
    id          BIGSERIAL PRIMARY KEY,
    geom        geometry(Point, 4326) NOT NULL,
    severity_g  REAL NOT NULL,
    reports     INT NOT NULL DEFAULT 1,
    last_report TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS potholes_geom_idx ON potholes USING GIST (geom);

CREATE TABLE IF NOT EXISTS ghosts (
    id          BIGSERIAL PRIMARY KEY,
    finish_geom geometry(Point, 4326) NOT NULL,
    rider       TEXT NOT NULL,
    time_ms     BIGINT NOT NULL,
    points_json JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ghosts_finish_idx ON ghosts USING GIST (finish_geom);
"""

pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global pool
    pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close_pool() -> None:
    if pool:
        await pool.close()


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "pool no inicializado"
    return pool
