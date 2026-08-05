from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .routers import ghosts, potholes, rooms, zone


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(
    title="revscope-server",
    description="Servidor colaborativo auto-hosteable para RevScope",
    lifespan=lifespan,
)

app.include_router(potholes.router)
app.include_router(rooms.router)
app.include_router(ghosts.router)
app.include_router(zone.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}
