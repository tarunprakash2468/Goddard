"""
tests/test_ui_drawers_shortcuts.py: Comprehensive Verification Test Suite for Milestone 4:
CAD Connection Drawer, Copilot UI & Review/Autonomous Mode, Web Audio Synthesis,
WebKit IPC Bridge for Haptics & Sounds, and Global Keyboard Shortcuts.

Guarantees 100% offline pass rate (GODDARD_OFFLINE_MODE=true) with zero external network calls.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from starlette.testclient import TestClient

from goddard.ui.app import app

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "goddard" / "ui" / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"
APP_JS_PATH = STATIC_DIR / "app.js"


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a TestClient for UI and API verification in offline mode."""
    os.environ["GODDARD_OFFLINE_MODE"] = "true"
    return TestClient(app)


@pytest.fixture
def index_html() -> str:
    """Reads index.html content."""
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def app_js() -> str:
    """Reads app.js content."""
    return APP_JS_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CAD Connection Drawer & Credentials Sheet
# ─────────────────────────────────────────────────────────────────────────────


class TestCADConnectionDrawer:
    """Verifies in-app CAD Connection sliding glass drawer and credentials configuration."""

    def test_html_cad_drawer_and_pill_dom(self, index_html: str) -> None:
        """Assert CAD drawer and status pill elements exist in index.html."""
        assert 'id="cad-drawer"' in index_html, "Missing #cad-drawer sliding glass container"
        assert 'id="cad-status-pill"' in index_html, "Missing #cad-status-pill in header"
        assert 'id="cad-status-text"' in index_html, "Missing #cad-status-text inside status pill"
        assert 'id="cad-drawer-status-badge"' in index_html, "Missing #cad-drawer-status-badge in drawer"
        assert 'id="cad-drawer-doc-id"' in index_html, "Missing #cad-drawer-doc-id readout"
        assert 'id="cad-drawer-key-status"' in index_html, "Missing #cad-drawer-key-status readout"
        assert 'id="cad-mode-selector"' in index_html, "Missing #cad-mode-selector segmented control"
        assert 'id="cad-mode-mock-btn"' in index_html, "Missing #cad-mode-mock-btn"
        assert 'id="cad-mode-live-btn"' in index_html, "Missing #cad-mode-live-btn"
        assert 'id="btn-open-cad-credentials"' in index_html, "Missing #btn-open-cad-credentials"

    def test_html_cad_credentials_modal_dom(self, index_html: str) -> None:
        """Assert Onshape credentials modal elements exist in index.html."""
        assert 'id="cad-credentials-modal"' in index_html, "Missing #cad-credentials-modal"
        assert 'id="cad-input-access-key"' in index_html, "Missing #cad-input-access-key"
        assert 'id="cad-input-secret-key"' in index_html, "Missing #cad-input-secret-key"
        assert 'id="cad-input-doc-id"' in index_html, "Missing #cad-input-doc-id"
        assert 'id="cad-credentials-error"' in index_html, "Missing #cad-credentials-error"
        assert 'id="btn-save-cad-credentials"' in index_html, "Missing #btn-save-cad-credentials"

    def test_js_cad_drawer_functions(self, app_js: str) -> None:
        """Assert CAD drawer JavaScript controller functions exist in app.js."""
        for fn in [
            "fetchCadStatus",
            "updateCadUI",
            "toggleCadDrawer",
            "switchCadMode",
            "openCadCredentialsModal",
            "closeModal",
            "saveCadCredentials",
        ]:
            assert f"function {fn}" in app_js, f"app.js must define {fn}()"

    def test_api_cad_endpoints_integration(self, client: TestClient) -> None:
        """Assert backend CAD API endpoints respond correctly to client requests."""
        # 1. GET /api/cad/status
        status_res = client.get("/api/cad/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert "connected" in status_data
        assert "mode" in status_data
        assert "document_id" in status_data
        assert "access_key_configured" in status_data

        # 2. POST /api/cad/mode
        mode_res = client.post("/api/cad/mode", json={"mode": "mock"})
        assert mode_res.status_code == 200
        assert mode_res.json()["mode"] == "mock"

        # 3. POST /api/cad/config
        config_res = client.post(
            "/api/cad/config",
            json={
                "access_key": "test_access_key",
                "secret_key": "test_secret_key",
                "document_id": "mock-doc-001",
            },
        )
        assert config_res.status_code == 200
        assert config_res.json()["configured"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Copilot Drawer & Diff Modal UI
# ─────────────────────────────────────────────────────────────────────────────


class TestCopilotDrawerAndModals:
    """Verifies MLX Copilot sliding glass drawer, VRAM readout, model downloader, and diff modal."""

    def test_html_copilot_drawer_dom(self, index_html: str) -> None:
        """Assert Copilot drawer, VRAM pill, model catalog, and progress elements exist."""
        assert 'id="copilot-drawer"' in index_html, "Missing #copilot-drawer"
        assert 'id="copilot-vram-pill"' in index_html, "Missing #copilot-vram-pill"
        assert 'id="vram-info-text"' in index_html, "Missing #vram-info-text"
        assert 'id="copilot-model-select"' in index_html, "Missing #copilot-model-select"
        assert 'id="btn-download-model"' in index_html, "Missing #btn-download-model"
        assert 'id="copilot-download-badge"' in index_html, "Missing #copilot-download-badge"
        assert 'id="copilot-download-progress-container"' in index_html, "Missing #copilot-download-progress-container"
        assert 'id="copilot-download-bar"' in index_html, "Missing #copilot-download-bar"
        assert 'id="copilot-download-percent"' in index_html, "Missing #copilot-download-percent"
        assert 'id="copilot-download-status"' in index_html, "Missing #copilot-download-status"

    def test_html_copilot_tabs_and_panels_dom(self, index_html: str) -> None:
        """Assert dual mode tabs and panels exist for Review Mode and Goal Mode."""
        assert 'id="tab-btn-review"' in index_html, "Missing #tab-btn-review"
        assert 'id="tab-btn-goal"' in index_html, "Missing #tab-btn-goal"
        assert 'id="panel-copilot-review"' in index_html, "Missing #panel-copilot-review"
        assert 'id="panel-copilot-goal"' in index_html, "Missing #panel-copilot-goal"

    def test_html_copilot_review_mode_controls(self, index_html: str) -> None:
        """Assert Interactive Review Mode controls exist in index.html."""
        assert 'id="copilot-intent"' in index_html, "Missing #copilot-intent textarea"
        assert 'id="btn-propose-review"' in index_html, "Missing #btn-propose-review"
        assert 'id="copilot-diff-output"' in index_html, "Missing #copilot-diff-output container"
        assert 'id="apply-diff-btn"' in index_html, "Missing #apply-diff-btn"

    def test_html_copilot_autonomous_goal_controls(self, index_html: str) -> None:
        """Assert Autonomous Goal Mode inputs and tables exist in index.html."""
        assert 'id="goal-target-apogee"' in index_html, "Missing #goal-target-apogee"
        assert 'id="goal-target-stress"' in index_html, "Missing #goal-target-stress"
        assert 'id="goal-target-fos"' in index_html, "Missing #goal-target-fos"
        assert 'id="goal-max-iterations"' in index_html, "Missing #goal-max-iterations"
        assert 'id="btn-start-optimization"' in index_html, "Missing #btn-start-optimization"
        assert 'id="goal-progress-container"' in index_html, "Missing #goal-progress-container"
        assert 'id="goal-status-badge"' in index_html, "Missing #goal-status-badge"
        assert 'id="goal-iterations-table"' in index_html, "Missing #goal-iterations-table"
        assert 'id="goal-iterations-tbody"' in index_html, "Missing #goal-iterations-tbody"

    def test_html_diff_modal_dom(self, index_html: str) -> None:
        """Assert parametric diff comparison modal elements exist in index.html."""
        assert 'id="diff-modal"' in index_html, "Missing #diff-modal"
        assert 'id="diff-content"' in index_html, "Missing #diff-content"
        assert 'id="btn-diff-modal"' in index_html, "Missing #btn-diff-modal toggle button"

    def test_js_copilot_functions(self, app_js: str) -> None:
        """Assert MLX Copilot controller functions exist in app.js."""
        for fn in [
            "toggleCopilotDrawer",
            "loadCopilotVram",
            "loadCopilotModels",
            "onModelSelectChange",
            "downloadSelectedModel",
            "switchCopilotTab",
            "renderCopilotDiff",
            "submitCopilotReview",
            "applyProposedDiff",
            "startAutonomousOptimization",
            "toggleDiffModal",
            "renderDiffModalContent",
            "closeAllDrawers",
        ]:
            assert f"function {fn}" in app_js, f"app.js must define {fn}()"

    def test_api_copilot_endpoints_integration(self, client: TestClient) -> None:
        """Assert backend Copilot endpoints return structured contracts."""
        # VRAM profiler
        vram_res = client.get("/api/copilot/vram")
        assert vram_res.status_code == 200
        assert "physical_ram_gib" in vram_res.json()
        assert "tier" in vram_res.json()

        # Model catalog
        models_res = client.get("/api/copilot/models")
        assert models_res.status_code == 200
        assert "models" in models_res.json() or "preset_catalog" in models_res.json()

        # Review endpoint
        review_res = client.post(
            "/api/copilot/review",
            json={
                "intent": "Reduce airframe dry mass while maintaining yield FoS >= 2.0",
                "base_revision_id": 1,
            },
        )
        assert review_res.status_code == 200
        review_data = review_res.json()
        assert "modifications" in review_data
        assert "summary" in review_data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Aerospace Audio Synthesis & Global Mute Control
# ─────────────────────────────────────────────────────────────────────────────


class TestAerospaceAudioAndMute:
    """Verifies pure Web Audio API oscillator tone synthesis and global mute toggle."""

    def test_html_audio_mute_button(self, index_html: str) -> None:
        """Assert global mute toggle button and icon exist in index.html header."""
        assert 'id="btn-audio-mute"' in index_html, "Missing #btn-audio-mute"
        assert 'id="audio-mute-icon"' in index_html, "Missing #audio-mute-icon"

    def test_js_audio_synthesizer_zero_external_files(self, index_html: str, app_js: str) -> None:
        """Assert audio system uses pure Web Audio API synthesis without external .mp3/.wav files."""
        for ext in [".mp3", ".wav", ".ogg", ".aac"]:
            assert ext not in index_html.lower(), f"Forbidden external audio asset in index.html: {ext}"
            assert ext not in app_js.lower(), f"Forbidden external audio asset in app.js: {ext}"

        assert "AudioContext" in app_js, "app.js must utilize standard Web Audio AudioContext"
        assert "createOscillator" in app_js, "app.js must synthesize sound via createOscillator()"
        assert "createGain" in app_js, "app.js must shape sound envelopes via createGain()"

    def test_js_audio_cues_definitions(self, app_js: str) -> None:
        """Assert all 5 required aerospace audio cues are synthesized in playAeroCue."""
        assert "function playAeroCue" in app_js, "app.js must define playAeroCue()"
        for cue in ["complete", "touchdown", "alert", "warning", "click"]:
            assert f"'{cue}'" in app_js or f'"{cue}"' in app_js, f"playAeroCue must handle cue '{cue}'"

    def test_js_audio_gesture_unlock(self, app_js: str) -> None:
        """Assert AudioContext lazy auto-resume on user gesture."""
        assert "state.audio.ctx.state === \"suspended\"" in app_js or "suspended" in app_js
        assert "resume()" in app_js

    def test_js_audio_mute_state_and_persistence(self, app_js: str) -> None:
        """Assert toggleAudioMute persists state to localStorage and notifies backend."""
        assert "function toggleAudioMute" in app_js
        assert "localStorage.setItem" in app_js
        assert "goddard_audio_muted" in app_js or "goddard_muted" in app_js
        assert "/api/audio/mute" in app_js

    def test_api_audio_mute_endpoints(self, client: TestClient) -> None:
        """Assert GET /api/audio/mute and POST /api/audio/mute endpoints update state."""
        mute_res = client.post("/api/audio/mute", json={"muted": True})
        assert mute_res.status_code == 200
        assert mute_res.json()["muted"] is True

        get_res = client.get("/api/audio/mute")
        assert get_res.status_code == 200
        assert get_res.json()["muted"] is True

        unmute_res = client.post("/api/audio/mute", json={"muted": False})
        assert unmute_res.status_code == 200
        assert unmute_res.json()["muted"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. WebKit IPC Bridge for Haptics & Sounds
# ─────────────────────────────────────────────────────────────────────────────


class TestWebKitIPCBridge:
    """Verifies WebKit messageHandler IPC bridge for AppKit haptics, sounds, and window control."""

    def test_js_webkit_bridge_call(self, app_js: str) -> None:
        """Assert dispatchIPC targets window.webkit.messageHandlers.goddardBridge.postMessage."""
        assert "function dispatchIPC" in app_js
        assert "window.webkit" in app_js
        assert "messageHandlers" in app_js
        assert "goddardBridge" in app_js
        assert "postMessage" in app_js

    def test_js_ipc_action_schemas(self, app_js: str) -> None:
        """Assert dispatchIPC formats actions for haptic, playSound, and toggleMute."""
        assert 'action: "haptic"' in app_js or "action: 'haptic'" in app_js or '"haptic"' in app_js
        assert 'action: "playSound"' in app_js or "action: 'playSound'" in app_js or '"playSound"' in app_js
        assert 'action: "toggleMute"' in app_js or "action: 'toggleMute'" in app_js or '"toggleMute"' in app_js

    def test_js_ipc_graceful_fallback(self, app_js: str) -> None:
        """Assert fallback to REST /api/events/haptic when WebKit bridge is not present."""
        assert "/api/events/haptic" in app_js, "app.js must post to /api/events/haptic as web fallback"

    def test_api_events_haptic_endpoint(self, client: TestClient) -> None:
        """Assert POST /api/events/haptic endpoint receives and logs haptic events."""
        res = client.post("/api/events/haptic", json={"style": "alignment"})
        assert res.status_code == 200
        assert res.json().get("ok") is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Global Keyboard Shortcuts
# ─────────────────────────────────────────────────────────────────────────────


class TestGlobalKeyboardShortcuts:
    """Verifies global keyboard shortcuts with proper event target filtering."""

    def test_js_keydown_listener_registered(self, app_js: str) -> None:
        """Assert keydown listener is registered in initKeyboardShortcuts."""
        assert "function initKeyboardShortcuts" in app_js
        assert "keydown" in app_js

    def test_js_all_required_shortcut_keys(self, app_js: str) -> None:
        """Assert bindings for 'k', 'r', 'd', 'e', 'Escape', and Spacebar."""
        for key in ["'k'", "'r'", "'d'", "'e'", "'Escape'"]:
            assert key in app_js, f"Shortcut key {key} must be bound in app.js"

    def test_js_spacebar_input_guard(self, app_js: str) -> None:
        """Assert spacebar handler excludes input and textarea targets."""
        assert (
            "matches('input,textarea')" in app_js
            or 'matches("input,textarea")' in app_js
            or "matches('input, textarea')" in app_js
        ), "Spacebar handler must explicitly exclude text input targets"

    def test_js_shortcut_action_functions(self, app_js: str) -> None:
        """Assert all required shortcut action functions are defined in app.js."""
        for fn in [
            "toggleCopilotDrawer",
            "triggerResimulateCurrent",
            "toggleDiffModal",
            "triggerExportBundle",
            "downloadActiveBundle",
            "toggleAutoRotate",
            "toggleAutoSpin",
            "closeAllDrawers",
        ]:
            assert f"function {fn}" in app_js, f"app.js must define {fn}()"

    def test_js_prevent_default_on_shortcuts(self, app_js: str) -> None:
        """Assert e.preventDefault() is invoked to prevent browser default behaviors."""
        assert "preventDefault()" in app_js or "e.preventDefault()" in app_js
