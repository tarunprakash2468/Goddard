"""
Centralized CAD State Manager and Schemas for Goddard.

Manages active CAD mode ("mock" vs "live"), Onshape credentials,
persistence to .env, and dynamic switching without server restart.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any, Literal

import requests
from pydantic import BaseModel, field_validator


class CADStatusResponse(BaseModel):
    connected: bool
    mode: Literal["mock", "live"]
    document_id: str
    access_key_configured: bool


class CADModeRequest(BaseModel):
    mode: Literal["mock", "live"]


class CADModeResponse(BaseModel):
    status: str = "ok"
    mode: Literal["mock", "live"]
    connected: bool


class CADConfigRequest(BaseModel):
    access_key: str
    secret_key: str
    document_id: str

    @field_validator("*")
    @classmethod
    def validate_no_control_chars(cls, v: str) -> str:
        if isinstance(v, str):
            if "\x00" in v:
                raise ValueError("Value cannot contain null bytes (\\x00)")
            if "\n" in v or "\r" in v:
                raise ValueError("Value cannot contain newline characters (\\n, \\r)")
        return v


class CADConfigResponse(BaseModel):
    status: str = "ok"
    configured: bool = True
    document_id: str


class CADStateManager:
    """
    Centralized state manager for CAD mode and Onshape credentials.
    Supports dynamic toggling between mock and live modes without restarting the daemon.
    """

    def __init__(self, env_path: pathlib.Path | None = None) -> None:
        self._env_path = env_path
        self._load_from_env()

    @property
    def env_path(self) -> pathlib.Path:
        if self._env_path is not None:
            return self._env_path
        custom = os.getenv("GODDARD_ENV_FILE")
        if custom:
            return pathlib.Path(custom)
        repo_root = pathlib.Path(
            os.getenv("GODDARD_ROOT", pathlib.Path(__file__).resolve().parent.parent.parent)
        )
        return repo_root / ".env"

    def _load_from_env(self) -> None:
        self.access_key = os.getenv("ONSHAPE_ACCESS_KEY", "")
        self.secret_key = os.getenv("ONSHAPE_SECRET_KEY", "")
        self.document_id = os.getenv("ONSHAPE_DOCUMENT_ID") or os.getenv(
            "ONSHAPE_DID", "mock-doc-001"
        )
        offline = os.getenv("GODDARD_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
        mock_env = os.getenv("GODDARD_MOCK_ONSHAPE", "").lower() in ("1", "true", "yes")
        if (
            offline
            or mock_env
            or not self.access_key_configured
            or not self.secret_key
            or self.secret_key == "your_secret_key_here"
        ):
            self.mode: Literal["mock", "live"] = "mock"
        else:
            self.mode = "live"

    @property
    def access_key_configured(self) -> bool:
        return bool(self.access_key and self.access_key != "your_access_key_here")

    def get_client(self) -> Any:
        from goddard.client.client import OnshapeClient
        from goddard.client.mock import MockOnshapeClient

        if self.mode == "mock":
            return MockOnshapeClient(
                access_key=self.access_key or "mock_access",
                secret_key=self.secret_key or "mock_secret",
            )
        return OnshapeClient(
            access_key=self.access_key,
            secret_key=self.secret_key,
            fallback_to_mock=False,
        )

    def check_connection(self) -> bool:
        """
        Validates live CAD connectivity to Onshape API.
        Short-circuits in offline mock mode or when GODDARD_OFFLINE_MODE is enabled.
        """
        if self.mode == "mock":
            return False
        if (
            not self.access_key_configured
            or not self.secret_key
            or self.secret_key == "your_secret_key_here"
            or self.access_key == "your_access_key_here"
        ):
            return False
        if os.getenv("GODDARD_OFFLINE_MODE", "").lower() in ("1", "true", "yes"):
            return False

        try:
            resp = requests.get(
                "https://cad.onshape.com/api/v6/users/sessioninfo",
                auth=(self.access_key, self.secret_key),
                headers={"Accept": "application/json"},
                timeout=1.5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.check_connection(),
            "mode": self.mode,
            "document_id": self.document_id,
            "access_key_configured": self.access_key_configured,
        }

    def set_mode(self, mode: Literal["mock", "live"]) -> dict[str, Any]:
        if mode not in ("mock", "live"):
            raise ValueError(f"Invalid mode '{mode}'. Must be 'mock' or 'live'.")
        self.mode = mode
        connected = self.check_connection() if mode == "live" else False
        return {
            "status": "ok",
            "mode": self.mode,
            "connected": connected,
        }

    def set_config(self, access_key: str, secret_key: str, document_id: str) -> dict[str, Any]:
        for field_name, val in [
            ("access_key", access_key),
            ("secret_key", secret_key),
            ("document_id", document_id),
        ]:
            if "\x00" in val:
                raise ValueError(f"{field_name} cannot contain null bytes (\\x00)")
            if "\n" in val or "\r" in val:
                raise ValueError(f"{field_name} cannot contain newline characters (\\n, \\r)")

        self.access_key = access_key
        self.secret_key = secret_key
        self.document_id = document_id

        os.environ["ONSHAPE_ACCESS_KEY"] = access_key
        os.environ["ONSHAPE_SECRET_KEY"] = secret_key
        os.environ["ONSHAPE_DOCUMENT_ID"] = document_id
        os.environ["ONSHAPE_DID"] = document_id

        self._persist_to_env()
        return {
            "status": "ok",
            "configured": True,
            "document_id": self.document_id,
        }

    def _persist_to_env(self) -> None:
        p = self.env_path
        lines: list[str] = []
        if p.exists():
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []

        keys_map = {
            "ONSHAPE_ACCESS_KEY": self.access_key,
            "ONSHAPE_SECRET_KEY": self.secret_key,
            "ONSHAPE_DOCUMENT_ID": self.document_id,
            "ONSHAPE_DID": self.document_id,
        }
        updated = set()
        out_lines: list[str] = []
        for line in lines:
            matched = False
            stripped = line.strip()
            for k, v in keys_map.items():
                if stripped.startswith(f"{k}=") or stripped.startswith(f"export {k}="):
                    prefix = "export " if stripped.startswith("export ") else ""
                    out_lines.append(f"{prefix}{k}={v}")
                    updated.add(k)
                    matched = True
                    break
            if not matched:
                out_lines.append(line)

        for k, v in keys_map.items():
            if k not in updated:
                out_lines.append(f"{k}={v}")

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


cad_state = CADStateManager()
