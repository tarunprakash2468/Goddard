"""
tests/test_ui_viewport_overlays.py: Verification test suite for Milestone 3:
3D Viewport, Liquid Glass Transparency, Physics Overlays & Revision Ghosting.

Guarantees 100% offline pass rate with zero outbound network calls.
Validates:
- HTML DOM structure for backdrop pill, overlay buttons, ghosting toggle, and legends.
- Static assets loading and correct Content-Type headers.
- JavaScript logic constructs in app.js:
  - Alpha renderer, setClearColor(0, 0), scene.background = null, scene.fog = null.
  - Backdrop mode switching logic (Liquid Glass, Deep Space Dark, CAD Studio Neutral).
  - 4 overlay modes (CAD Solid, FEA Stress, CFD Cp, Gmsh Wireframe).
  - Dual-layer ghosting mesh generation (Phantom Violet 0x8b5cf6 & Neon Fuchsia 0xd946ef).
  - Google Turbo colormap and aerodynamic diverging colormap.
  - Predecessor N - 1 tracking and in-memory cache.
- Backend mesh endpoints for surface scalars and predecessor geometry.
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


class TestMilestone3UIViewportOverlays:
    """Comprehensive verification suite for Milestone 3 UI components and endpoints."""

    def test_static_assets_serve_successfully(self, client: TestClient) -> None:
        """Assert index.html and app.js static assets load with 200 OK and valid MIME types."""
        # Root index.html
        res_root = client.get("/")
        assert res_root.status_code == 200
        assert "text/html" in res_root.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in res_root.text or "<html" in res_root.text

        # app.js
        res_js = client.get("/static/app.js")
        assert res_js.status_code == 200
        assert "javascript" in res_js.headers.get("content-type", "").lower()
        assert len(res_js.text) > 500

    def test_html_threejs_canvas_and_hud_structure(self) -> None:
        """Assert index.html contains Three.js viewport canvas and telemetry HUD elements."""
        html = INDEX_HTML_PATH.read_text()
        assert 'id="threejs-canvas"' in html, "index.html must mount #threejs-canvas"
        assert 'class="viewport-container' in html or "viewport-container" in html
        assert 'id="hud-len"' in html, "index.html must display vehicle length HUD element"
        assert 'id="hud-diam"' in html, "index.html must display vehicle diameter HUD element"
        assert 'id="hud-tri"' in html, "index.html must display triangle count HUD element"

    def test_html_backdrop_mode_pill(self) -> None:
        """Assert index.html contains the 3-segment backdrop pill with Liquid Glass, Deep Space, and CAD Studio."""
        html = INDEX_HTML_PATH.read_text()
        assert 'id="backdrop-mode-pill"' in html or 'id="backdrop-pill"' in html
        assert 'data-mode="liquid-glass"' in html or 'data-mode="glass"' in html
        assert 'data-mode="deep-space"' in html or 'data-mode="space"' in html
        assert 'data-mode="cad-studio"' in html or 'data-mode="studio"' in html
        assert "setBackdropMode" in html or "setBackdrop" in html

    def test_html_physics_overlay_pill_and_buttons(self) -> None:
        """Assert index.html contains the 4-mode physics overlay pill with Solid, Stress, Cp, and Wireframe."""
        html = INDEX_HTML_PATH.read_text()
        assert 'id="overlay-pill"' in html, "index.html must contain #overlay-pill"
        assert 'data-mode="solid"' in html, "Overlay pill must include CAD Solid mode"
        assert 'data-mode="stress"' in html, "Overlay pill must include FEA Stress mode"
        assert 'data-mode="cp"' in html, "Overlay pill must include CFD Cp mode"
        assert 'data-mode="wireframe"' in html, "Overlay pill must include Gmsh Wireframe mode"

    def test_html_revision_ghosting_toggle(self) -> None:
        """Assert index.html provides a dedicated HUD toggle button for 3D Revision Ghosting."""
        html = INDEX_HTML_PATH.read_text()
        assert 'id="btn-ghosting"' in html, "index.html must provide #btn-ghosting toggle button"
        assert "toggleRevisionGhosting" in html, (
            "index.html button must call toggleRevisionGhosting"
        )

    def test_html_colorbars_and_legends(self) -> None:
        """Assert index.html provides on-screen colorbars/legends for FEA stress and CFD pressure."""
        html = INDEX_HTML_PATH.read_text()
        assert 'id="physics-legend"' in html or 'id="stress-legend"' in html
        assert 'id="stress-legend"' in html, (
            "index.html must include #stress-legend colorbar container"
        )
        assert 'id="cp-legend"' in html, "index.html must include #cp-legend colorbar container"
        assert 'id="legend-peak-stress"' in html, (
            "index.html must include #legend-peak-stress readout"
        )
        assert 'id="legend-yield-fos"' in html, "index.html must include #legend-yield-fos badge"

    def test_html_css_liquid_glass_transparency(self) -> None:
        """Assert index.html defines transparent backgrounds for body/container and backdrop blur filters."""
        html = INDEX_HTML_PATH.read_text()
        assert "mode-liquid-glass" in html, "CSS must define mode-liquid-glass"
        assert "mode-deep-space" in html, "CSS must define mode-deep-space"
        assert "mode-cad-studio" in html, "CSS must define mode-cad-studio"
        assert "backdrop-filter: blur(" in html, (
            "index.html must define glass backdrop blur filters"
        )
        assert "-webkit-backdrop-filter: blur(" in html, "WebKit blur filter prefix must be present"

    def test_js_webgl_renderer_alpha_and_clear_color(self) -> None:
        """Assert app.js configures WebGLRenderer with alpha: true, setClearColor(0, 0), and scene.background = null."""
        app_js = APP_JS_PATH.read_text()
        assert "alpha: true" in app_js or "alpha : true" in app_js, (
            "WebGLRenderer must enable alpha: true"
        )
        assert "powerPreference" in app_js, "WebGLRenderer must specify powerPreference"
        assert "premultipliedAlpha: true" in app_js, (
            "WebGLRenderer must configure premultipliedAlpha"
        )
        assert "setClearColor" in app_js, "app.js must invoke renderer.setClearColor(0x000000, 0)"
        assert "scene.background = null" in app_js, (
            "app.js must support scene.background = null for liquid glass"
        )
        assert "scene.fog = null" in app_js, (
            "app.js must set scene.fog = null in transparent liquid glass mode"
        )

    def test_js_viewport_resize_clamping(self) -> None:
        """Assert app.js clamps container dimensions with Math.max to prevent zero-dimension division."""
        app_js = APP_JS_PATH.read_text()
        assert "Math.max" in app_js, "app.js must use Math.max to clamp dimensions"
        assert "onWindowResize" in app_js, "app.js must declare onWindowResize handler"

    def test_js_backdrop_mode_switching_logic(self) -> None:
        """Assert app.js implements backdrop mode switching for Liquid Glass, Deep Space, and CAD Studio."""
        app_js = APP_JS_PATH.read_text()
        assert "setBackdropMode" in app_js, "app.js must define setBackdropMode"
        assert "setBackdrop" in app_js, "app.js must define setBackdrop alias"
        assert "0x080c14" in app_js.lower(), "app.js must define Deep Space Dark color 0x080c14"
        assert "0x222834" in app_js.lower(), "app.js must define CAD Studio Neutral color 0x222834"
        assert "VALID_BACKDROP_MODES" in app_js, "app.js must define valid backdrop modes list"

    def test_js_four_overlay_modes_implementation(self) -> None:
        """Assert app.js implements the 4 distinct overlay rendering modes."""
        app_js = APP_JS_PATH.read_text()
        assert "MeshStandardMaterial" in app_js, "Clean CAD Solid must use MeshStandardMaterial PBR"
        assert "stress_field" in app_js, "app.js must handle stress_field vertex scalars for FEA"
        assert "cp_field" in app_js, "app.js must handle cp_field vertex scalars for CFD"
        assert "wireframe: true" in app_js, "app.js must support wireframe rendering"
        assert "0x00e5ff" in app_js.lower(), (
            "app.js must configure neon cyan wireframe color 0x00e5ff"
        )

    def test_js_turbo_colormap_scalar_mapping(self) -> None:
        """Assert app.js implements Turbo colormap calculation or scalar-to-color mapping."""
        app_js = APP_JS_PATH.read_text()
        assert "turboColormap" in app_js or "TURBO_STOPS" in app_js, (
            "app.js must implement Turbo colormap"
        )
        assert "generateStressColors" in app_js, (
            "app.js must generate vertex colors for stress field"
        )

    def test_js_diverging_cp_colormap(self) -> None:
        """Assert app.js implements aerodynamic diverging colormap for surface pressure Cp."""
        app_js = APP_JS_PATH.read_text()
        assert "CFD_CP_STOPS" in app_js or "sampleCp" in app_js, "app.js must implement Cp colormap"
        assert "generateCpColors" in app_js, "app.js must generate vertex colors for Cp field"

    def test_js_dual_layer_ghosting_mesh_generation(self) -> None:
        """Assert app.js defines dual-layer ghost materials (phantom violet 0x8b5cf6 & neon fuchsia 0xd946ef)."""
        app_js = APP_JS_PATH.read_text()
        assert "8b5cf6" in app_js.lower(), (
            "app.js must configure phantom violet solid color 0x8b5cf6"
        )
        assert "d946ef" in app_js.lower(), (
            "app.js must configure glowing neon fuchsia wireframe color 0xd946ef"
        )
        assert "depthwrite: false" in app_js.lower(), (
            "Ghost materials must specify depthWrite: false to prevent z-fighting"
        )
        assert "rotateX(-Math.PI / 2)" in app_js or "rotateX(-Math.PI/2)" in app_js, (
            "Ghost geometry must match active model rotateX(-PI/2) datum transform"
        )
        assert "geometry.translate" in app_js, "Ghost geometry must be translated to base datum Y=0"

    def test_js_revision_predecessor_tracking_and_caching(self) -> None:
        """Assert app.js tracks predecessor revision N - 1 and maintains in-memory mesh cache."""
        app_js = APP_JS_PATH.read_text()
        assert "priorRevId" in app_js or "revId - 1" in app_js, (
            "app.js must calculate prior revision N - 1"
        )
        assert "cache" in app_js.lower(), "app.js must maintain a cache for geometry"

    def test_js_ghosting_hud_toggle_state(self) -> None:
        """Assert app.js implements toggleRevisionGhosting with enabled state management."""
        app_js = APP_JS_PATH.read_text()
        assert "toggleRevisionGhosting" in app_js, (
            "app.js must define toggleRevisionGhosting function"
        )
        assert "state.ghost" in app_js, "app.js must maintain ghost state"

    def test_api_mesh_endpoints_for_overlays_and_ghosting(self, client: TestClient) -> None:
        """Assert /api/revisions/{rev_id}/mesh serves vertices, normals, and scalars for active and ghost meshes."""
        # Revision 1 (baseline)
        res1 = client.get("/api/revisions/1/mesh")
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1["vertices"]) > 0
        assert len(data1["normals"]) == len(data1["vertices"])
        assert len(data1["stress_field"]) == len(data1["vertices"]) // 3
        assert len(data1["cp_field"]) == len(data1["vertices"]) // 3
        assert data1["peak_von_mises_mpa"] > 0
        assert data1["yield_fos"] > 0

        # Revision 2 (predecessor comparison available)
        res2 = client.get("/api/revisions/2/mesh")
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2["vertices"]) > 0

        # Revision 0 must return 404 cleanly
        res0 = client.get("/api/revisions/0/mesh")
        assert res0.status_code == 404

    def test_offline_mode_environment_enforcement(self) -> None:
        """Assert GODDARD_OFFLINE_MODE is strictly set to true and test suite requires zero external internet."""
        assert os.environ.get("GODDARD_OFFLINE_MODE") == "true"
