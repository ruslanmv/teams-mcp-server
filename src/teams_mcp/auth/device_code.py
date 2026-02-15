from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from ..config import settings


AUTH_BASE = "https://login.microsoftonline.com"


async def device_code_start(scopes: list[str]) -> Dict[str, Any]:
    if not settings.ms_client_id:
        raise RuntimeError("MS_CLIENT_ID missing")

    url = f"{AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/devicecode"
    data = {"client_id": settings.ms_client_id, "scope": " ".join(scopes)}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, data=data)
        r.raise_for_status()
        return r.json()


async def device_code_poll(device_code: str) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": settings.ms_client_id,
        "device_code": device_code,
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, data=data)
        # 400 is normal while waiting (authorization_pending)
        if r.status_code == 400:
            return r.json()
        r.raise_for_status()
        return r.json()


async def refresh_token(refresh_token: str, scopes: list[str]) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.ms_client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(scopes),
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, data=data)
        r.raise_for_status()
        return r.json()
