"""Identidad sin base de usuarios propia.

El servidor valida credenciales, nunca las almacena. En `oidc` acepta JWT de
cualquier issuer OpenID Connect (Keycloak, Authentik, Google, un proveedor
propio…): descubre el JWKS vía /.well-known/openid-configuration y lo cachea.
Cambiar de proveedor de identidad = cambiar una URL en .env.
"""

import time
from dataclasses import dataclass
from typing import Mapping

import httpx
from fastapi import Depends, HTTPException, Request
from jose import jwt
from jose.exceptions import JWTError

from .config import Settings, get_settings

JWKS_CACHE_TTL_S = 3600


@dataclass
class Identity:
    subject: str
    display_name: str


_jwks_cache: dict = {"keys": None, "fetched_at": 0.0, "issuer": ""}


async def _jwks_for(issuer: str) -> dict:
    now = time.time()
    if _jwks_cache["keys"] and _jwks_cache["issuer"] == issuer and now - _jwks_cache["fetched_at"] < JWKS_CACHE_TTL_S:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=10) as client:
        discovery = (await client.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration")).json()
        keys = (await client.get(discovery["jwks_uri"])).json()
    _jwks_cache.update(keys=keys, fetched_at=now, issuer=issuer)
    return keys


def _bearer_from_headers(headers: Mapping[str, str]) -> str:
    header = headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Falta el header Authorization: Bearer")
    return header[7:].strip()


async def _identity_from_bearer_token(token: str, settings: Settings, fallback_name: str) -> Identity:
    """Valida un Bearer token en modo token/oidc. Compartido por el flujo HTTP
    (get_identity) y el handshake de WebSocket (get_ws_identity)."""
    if settings.auth_mode == "token":
        if not settings.auth_token or token != settings.auth_token:
            raise HTTPException(403, "Token inválido")
        return Identity(subject=f"token:{fallback_name}", display_name=fallback_name)

    # oidc
    try:
        claims = jwt.decode(
            token,
            await _jwks_for(settings.oidc_issuer),
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise HTTPException(401, f"JWT inválido: {e}") from e
    name = claims.get("preferred_username") or claims.get("name") or claims["sub"][:12]
    return Identity(subject=claims["sub"], display_name=str(name)[:32])


async def get_identity(request: Request, settings: Settings = Depends(get_settings)) -> Identity:
    if settings.auth_mode == "none":
        # Identidad autodeclarada — solo para LAN/grupos de confianza
        name = request.headers.get("x-rider-name", "anonimo")[:32]
        return Identity(subject=f"anon:{name}", display_name=name)

    token = _bearer_from_headers(request.headers)
    fallback_name = request.headers.get("x-rider-name", "rider")[:32]
    return await _identity_from_bearer_token(token, settings, fallback_name)


async def get_ws_identity(headers: Mapping[str, str], settings: Settings, self_declared_name: str) -> Identity:
    """Equivalente de get_identity para el handshake de WebSocket.

    En modo `none` la identidad sigue siendo autodeclarada (el nombre viene de la
    query string, no hay header propio). En `token`/`oidc` exige el mismo
    Authorization: Bearer que el flujo HTTP, leído de los headers del handshake.
    """
    if settings.auth_mode == "none":
        return Identity(subject=f"anon:{self_declared_name}", display_name=self_declared_name)

    token = _bearer_from_headers(headers)
    return await _identity_from_bearer_token(token, settings, self_declared_name)
