from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from ..auth.device_code import refresh_token
from ..auth.scopes import DEFAULT_SCOPES
from ..auth.token_store import TokenBundle, TokenStore
from ..config import settings


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self, store: TokenStore) -> None:
        self.store = store

    def _is_expired(self, expires_at: int | None) -> bool:
        if not expires_at:
            return False
        return time.time() > (expires_at - 60)

    async def _ensure_token(self) -> TokenBundle:
        bundle = self.store.load()
        if not bundle or not bundle.access_token:
            raise RuntimeError("Not authenticated. Run teams.auth.device_code_start first.")

        # Optional: restrict account
        if settings.ms_allowed_upn and bundle.account_upn and settings.ms_allowed_upn != bundle.account_upn:
            raise RuntimeError("Authenticated account not allowed by MS_ALLOWED_UPN")

        if bundle.refresh_token and self._is_expired(bundle.expires_at):
            tok = await refresh_token(bundle.refresh_token, DEFAULT_SCOPES)
            expires_in = int(tok.get("expires_in", 3600))
            new_bundle = TokenBundle(
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token", bundle.refresh_token),
                expires_at=int(time.time()) + expires_in,
                id_token=tok.get("id_token"),
                account_upn=bundle.account_upn,
            )
            self.store.save(new_bundle)
            return new_bundle

        return bundle

    async def get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        b = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{GRAPH_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {b.access_token}"},
            )
            r.raise_for_status()
            return r.json()

    async def post(self, path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        b = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{GRAPH_BASE}{path}",
                json=json_body,
                headers={"Authorization": f"Bearer {b.access_token}"},
            )
            r.raise_for_status()
            return r.json()
