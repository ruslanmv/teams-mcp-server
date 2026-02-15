from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    id_token: str | None
    account_upn: str | None


class TokenStore:
    def __init__(self, path: str = "data/token.json.enc") -> None:
        if not settings.token_key:
            raise RuntimeError("TEAMS_MCP_TOKEN_KEY is required")
        self._fernet = Fernet(settings.token_key.encode("utf-8"))
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def load(self) -> Optional[TokenBundle]:
        if not os.path.exists(self._path):
            return None
        raw = open(self._path, "rb").read()
        try:
            dec = self._fernet.decrypt(raw)
        except InvalidToken:
            return None
        data = json.loads(dec.decode("utf-8"))
        return TokenBundle(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at"),
            id_token=data.get("id_token"),
            account_upn=data.get("account_upn"),
        )

    def save(self, bundle: TokenBundle) -> None:
        data = {
            "access_token": bundle.access_token,
            "refresh_token": bundle.refresh_token,
            "expires_at": bundle.expires_at,
            "id_token": bundle.id_token,
            "account_upn": bundle.account_upn,
        }
        enc = self._fernet.encrypt(json.dumps(data).encode("utf-8"))
        with open(self._path, "wb") as f:
            f.write(enc)

    def clear(self) -> None:
        if os.path.exists(self._path):
            os.remove(self._path)
