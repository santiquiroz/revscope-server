from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://revscope:revscope@localhost:5432/revscope"

    # none  = sin auth (LAN); token = Bearer compartido; oidc = JWT de cualquier issuer OIDC
    auth_mode: Literal["none", "token", "oidc"] = "none"
    auth_token: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = "revscope"


@lru_cache
def get_settings() -> Settings:
    return Settings()
