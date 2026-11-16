"""tests/e2e/conftest.py: Shared fixtures, offline network isolation, and isolated
test environments for the Goddard 4-Tier E2E Test Suite.

All tests interact directly with the real FastAPI application (goddard.ui.app.app).
No synthetic route interceptors, 404 suppressors, or mock routers are permitted.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import sys
from collections.abc import Callable
from typing import Any

import pytest
from starlette.testclient import TestClient

# Ensure repo root is at the front of sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Enforce Goddard offline mode globally across all E2E tests
os.environ["GODDARD_OFFLINE_MODE"] = "true"

from goddard.client.cad_state import cad_state  # noqa: E402
from goddard.ui.app import app, reset_shutdown_state  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# 1. Network Isolation Guard (100% Offline Assurance)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def offline_network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevents any outbound TCP network connections during E2E test execution.
    Allows only local loopback (127.0.0.1, localhost, ::1, 0.0.0.0, None).
    Covers both socket.socket.connect and socket.socket.connect_ex.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _is_loopback(address: Any) -> bool:
        if isinstance(address, tuple) and len(address) >= 2:
            host = address[0]
            return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0", None)
        return True

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if not _is_loopback(address):
            host = address[0] if isinstance(address, tuple) else address
            port = address[1] if isinstance(address, tuple) and len(address) > 1 else ""
            raise ConnectionRefusedError(
                f"E2E Offline Guard: Outbound network connection to {host}:{port} blocked."
            )
        return real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_loopback(address):
            return 111  # ECONNREFUSED
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Environment & Design Isolation Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_designs_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Creates an isolated temporary designs directory populated with seed revisions
    and geometry files, monkeypatching GODDARD_DESIGNS_DIR.
    Guarantees clean state isolation without contaminating the repository designs/ directory.
    """
    designs_dir = tmp_path / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(designs_dir))

    # Reset in-memory application lifecycle and CAD state
    reset_shutdown_state()
    cad_state.set_mode("mock")

    repo_designs = REPO_ROOT / "designs"
    if repo_designs.exists():
        # Copy baseline geometry and surface cache for rev_001 and rev_002
        for filename in [
            "rev_001.step",
            "rev_001.msh",
            "rev_001_surface.json",
            "rev_002.step",
            "rev_002.msh",
            "rev_002_surface.json",
        ]:
            src = repo_designs / filename
            if src.exists():
                shutil.copy(src, designs_dir / filename)

        for rev_dir in ["rev_001", "rev_002"]:
            src_dir = repo_designs / rev_dir
            if src_dir.exists():
                shutil.copytree(src_dir, designs_dir / rev_dir, dirs_exist_ok=True)

        # Seed design_ledger.json
        seed_ledger = repo_designs / "design_ledger.json"
        if seed_ledger.exists():
            try:
                data = json.loads(seed_ledger.read_text())[:3]
                (designs_dir / "design_ledger.json").write_text(json.dumps(data, indent=2))
            except Exception:
                pass

    return designs_dir


# ─────────────────────────────────────────────────────────────────────────────
# 3. Direct FastAPI Application Clients (Zero Wrapper / Facade Layer)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repo_client() -> TestClient:
    """TestClient operating directly on the real FastAPI app using repository designs/."""
    reset_shutdown_state()
    return TestClient(app)


@pytest.fixture
def client(isolated_designs_dir: pathlib.Path) -> TestClient:
    """TestClient operating directly on the real FastAPI app against isolated_designs_dir."""
    reset_shutdown_state()
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Helper Fixtures & Schema Validators
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_vram_profiler(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], int]:
    """Helper fixture to simulate different Apple Silicon unified memory tiers via env var and monkeypatch."""

    def _set_ram_gib(gib: float) -> int:
        bytes_val = int(gib * 1024 * 1024 * 1024)
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", str(bytes_val))
        try:
            from goddard.copilot.vram_profiler import VRAMProfiler

            monkeypatch.setattr(VRAMProfiler, "get_physical_ram_gib", lambda self: gib)
        except ImportError:
            pass
        return bytes_val

    return _set_ram_gib


@pytest.fixture
def mock_hf_cache(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Creates a mock ~/.cache/huggingface/hub directory structure."""
    hf_dir = tmp_path / "huggingface" / "hub"
    hf_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))

    # Create mock Qwen2.5 snapshot
    model_dir = hf_dir / "models--mlx-community--Qwen2.5-Coder-7B-Instruct-4bit"
    snapshots_dir = model_dir / "snapshots" / "main"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / "config.json").write_text('{"model_type": "qwen2"}')
    (snapshots_dir / "model.safetensors").write_bytes(b"\x00" * 4096)
    return hf_dir


@pytest.fixture
def ipc_message_validator() -> Callable[[dict[str, Any]], bool]:
    """Validates WebKit IPC message schemas according to PROJECT.md § Contract 4."""

    def _validate(msg: dict[str, Any]) -> bool:
        assert isinstance(msg, dict), "IPC message must be a dictionary"
        assert "action" in msg, "IPC message must contain 'action'"
        valid_actions = ("haptic", "playSound", "toggleMute", "exportBundle", "windowControl")
        assert msg["action"] in valid_actions, f"Unknown action: {msg['action']}"

        if msg["action"] == "haptic":
            assert msg.get("style") in ("generic", "alignment", "levelChange"), (
                f"Invalid style: {msg.get('style')}"
            )
        elif msg["action"] == "playSound":
            assert msg.get("sound") in ("touchdown", "complete", "alert", "warning", "click"), (
                f"Invalid sound: {msg.get('sound')}"
            )
        elif msg["action"] == "toggleMute":
            assert "muted" in msg and type(msg["muted"]) is bool, (
                "toggleMute requires boolean 'muted'"
            )
        elif msg["action"] == "exportBundle":
            assert "revisionId" in msg and type(msg["revisionId"]) is int, (
                "exportBundle requires integer 'revisionId'"
            )
        elif msg["action"] == "windowControl":
            assert msg.get("command") in ("minimize", "zoom", "close"), (
                f"Invalid window command: {msg.get('command')}"
            )
        return True

    return _validate


@pytest.fixture
def swift_appkit_specs() -> dict[str, Any]:
    """Authoritative AppKit window & packaging specifications (PROJECT.md & R1/R6).
    Used strictly as a reference contract.
    """
    return {
        "styleMask": [
            ".titled",
            ".closable",
            ".miniaturizable",
            ".resizable",
            ".fullSizeContentView",
        ],
        "titlebarAppearsTransparent": True,
        "titleVisibility": ".hidden",
        "isOpaque": False,
        "backgroundColor": ".clear",
        "visualEffectView": {
            "material": ".underWindowBackground",
            "blendingMode": ".behindWindow",
            "state": ".active",
        },
        "webView": {
            "drawsBackground": False,
            "underPageBackgroundColor": ".clear",
            "isOpaque": False,
        },
        "bundle": {
            "executable": "GoddardApp",
            "info_plist_keys": [
                "CFBundleExecutable",
                "CFBundleIdentifier",
                "NSAppTransportSecurity",
            ],
            "ats_local_networking": True,
        },
    }
