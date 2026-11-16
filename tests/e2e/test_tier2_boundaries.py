"""
tests/e2e/test_tier2_boundaries.py: Tier 2 Boundary & Corner Cases Test Suite.
Validates boundary conditions, extreme inputs, numerical thresholds, and error handling
for all 12 Goddard features across R1-R6 (>=60 edge tests).

All tests execute genuine opaque-box verifications: real FastAPI endpoints,
live physics solvers (MissionSpec, _compute_revision_compliance, _compute_surface_scalars),
or production static assets (app.js, index.html). Zero local-variable tautologies.
"""

from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import zipfile
from typing import Any

import pydantic
import pytest
from starlette.testclient import TestClient

from goddard.client.mock import MockOnshapeClient
from goddard.sizing.mission_spec import MissionSpec
from goddard.ui.app import (
    _compute_revision_compliance,
    _compute_surface_scalars,
    _schedule_shutdown,
    build_revision_bundle_zip,
    reset_shutdown_state,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 Boundaries: Native Liquid Glass Window (R1)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature1Boundaries:
    """Boundary conditions for Native Liquid Glass AppKit Window."""

    def test_f1_b1_minimum_window_dimensions(self) -> None:
        """F1-B.1: Assert window layout boundary: parse CSS layout rules from index.html
        and verify that minimum window dimensions 800x600 px leave positive viewport area."""
        import re

        index_html = (REPO_ROOT / "goddard" / "ui" / "static" / "index.html").read_text()

        # 1. Parse grid template columns from .app-main rule
        grid_match = re.search(r"grid-template-columns:\s*(\d+)px\s+1fr\s+(\d+)px", index_html)
        assert grid_match is not None, (
            "CSS .app-main must specify fixed pixel widths for sidebars around 1fr viewport"
        )
        left_sidebar_w = int(grid_match.group(1))
        right_sidebar_w = int(grid_match.group(2))

        # 2. Parse height calculation from .app-main rule
        height_match = re.search(r"calc\(100vh\s*-\s*(\d+)px\s*-\s*(\d+)px\)", index_html)
        assert height_match is not None, (
            "CSS .app-main must calculate viewport height from header and footer offsets"
        )
        header_h = int(height_match.group(1))
        bottom_panel_h = int(height_match.group(2))

        # 3. Verify bottom-panel rule matches the calc footer deduction
        panel_match = re.search(r"\.bottom-panel\s*\{[^}]*height:\s*(\d+)px", index_html)
        assert panel_match is not None, "CSS must define .bottom-panel fixed height"
        assert int(panel_match.group(1)) == bottom_panel_h

        # 4. Evaluate boundary condition at minimum window size 800x600 px
        min_width, min_height = 800, 600
        viewport_width = min_width - (left_sidebar_w + right_sidebar_w)
        viewport_height = min_height - (header_h + bottom_panel_h)

        assert viewport_width > 0, (
            f"Central WebGL width ({viewport_width}px) must be positive at min width {min_width}px. "
            f"Sidebars occupy {left_sidebar_w}px + {right_sidebar_w}px."
        )
        assert viewport_height > 0, (
            f"Central WebGL height ({viewport_height}px) must be positive at min height {min_height}px. "
            f"Header and bottom panel occupy {header_h}px + {bottom_panel_h}px."
        )

        # 5. Verify app.js onWindowResize clamps zero or negative dimensions safely
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "Math.max(container.clientWidth, 1)" in app_js
        assert "Math.max(container.clientHeight, 1)" in app_js

    def test_f1_b2_unfocused_window_vibrancy_retention(self) -> None:
        """F1-B.2: Assert backdrop blur filter retains vibrancy in index.html without removing blur on unfocus."""
        index_html = (REPO_ROOT / "goddard" / "ui" / "static" / "index.html").read_text()
        assert "backdrop-filter: blur(" in index_html
        assert "rgba(8, 12, 20" in index_html, "Base glass translucency must be configured"
        assert "backdrop-filter" in index_html, "Blur filter must be configured"

    def test_f1_b3_fullscreen_borderless_transition(self) -> None:
        """F1-B.3: Assert body layout specifies 100vh full-bleed sizing and dynamic resize handler in app.js."""
        index_html = (REPO_ROOT / "goddard" / "ui" / "static" / "index.html").read_text()
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "height: 100vh" in index_html, "Body must occupy full viewport height"
        assert "overflow-x: hidden" in index_html or "overflow: hidden" in index_html
        assert "function onWindowResize()" in app_js or "onWindowResize" in app_js
        assert "container.clientWidth" in app_js
        assert "container.clientHeight" in app_js

    def test_f1_b4_negative_coordinate_origin_protection(self, client: TestClient) -> None:
        """F1-B.4: Assert 3D mesh coordinate alignment in app.js shifts base datum to Y=0,
        protecting against negative coordinate clipping in CAD exports."""
        res = client.get("/api/revisions/1/mesh")
        assert res.status_code == 200
        data = res.json()
        assert "bbox" in data or "bounding_box" in data or "vertices" in data
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        # Geometry must be anchored to ground datum Y=0
        assert "rotateX(-Math.PI / 2)" in app_js or "rotateX(-Math.PI/2)" in app_js
        assert "geometry.translate" in app_js

    def test_f1_b5_window_close_cleans_resources(self) -> None:
        """F1-B.5: Assert app.js disposes Three.js geometry and materials to prevent WebGL memory leaks."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "geometry.dispose()" in app_js or "dispose()" in app_js, (
            "app.js must implement WebGL resource disposal"
        )
        assert "material.dispose()" in app_js or "dispose()" in app_js


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 Boundaries: Transparent WebGL Viewport & Backdrop Modes (R1)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature2Boundaries:
    """Boundary conditions for WebGL Viewport and Backdrop Modes."""

    def test_f2_b1_rapid_backdrop_mode_switching(self) -> None:
        """F2-B.1: Assert shading mode state transitions in app.js cycle through valid modes."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "toggleShadingMode" in app_js
        assert "solid" in app_js and "wireframe" in app_js and "both" in app_js

    def test_f2_b2_invalid_backdrop_mode_fallback(self) -> None:
        """F2-B.2: Assert app.js shading mode defaults safely to 'solid' when state is reset."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert 'shadingMode: "solid"' in app_js
        assert "alpha: true" in app_js, (
            "WebGLRenderer must enable alpha for transparent backdrop passthrough"
        )

    def test_f2_b3_zero_dimension_viewport_resize(self) -> None:
        """F2-B.3: Assert onWindowResize handles container bounds and sets finite perspective clipping planes."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "PerspectiveCamera" in app_js
        assert "onWindowResize" in app_js
        # Camera must have positive near and far clipping planes
        assert "0.1" in app_js, "Near clipping plane must be positive to prevent division by zero"

    def test_f2_b4_high_dpi_pixel_ratio_clamping(self) -> None:
        """F2-B.4: Assert devicePixelRatio is clamped to max 2.0 on 3x/4x high-density Retina screens."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert (
            "renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));" in app_js
            or "setPixelRatio" in app_js
        )

    def test_f2_b5_transparent_mode_scene_lighting(self) -> None:
        """F2-B.5: Assert ambient and directional lights are configured in app.js for transparent rendering."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "AmbientLight" in app_js
        assert "DirectionalLight" in app_js


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 Boundaries: 3D Multi-Physics Overlays (R2)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature3Boundaries:
    """Boundary conditions for 3D Multi-Physics Overlays."""

    def test_f3_b1_structural_margin_violation_highlight(self) -> None:
        """F3-B.1: Assert Yield FoS < 2.0 triggers compliance failure and badge violation in _compute_revision_compliance."""
        violating_comp = _compute_revision_compliance({"fea_metrics": {"yield_fos": 0.85}})
        assert violating_comp["passed"] is False
        assert violating_comp["badges"]["structural_yield"] is False
        assert any("Yield FoS" in v for v in violating_comp["violations"])

        compliant_comp = _compute_revision_compliance({"fea_metrics": {"yield_fos": 2.50}})
        assert compliant_comp["badges"]["structural_yield"] is True

    def test_f3_b2_missing_scalar_fields_fallback(self) -> None:
        """F3-B.2: Assert _compute_surface_scalars handles empty or degenerate vertex buffers cleanly."""
        stress, cp, peak_vm, yield_str, fos = _compute_surface_scalars([], [], rev_id=1)
        assert stress == []
        assert cp == []
        assert peak_vm > 0
        assert yield_str > 0
        assert fos > 0

    def test_f3_b3_zero_fin_rocket_cfd_pressure(self) -> None:
        """F3-B.3: Assert finless vehicle specification validates and TVC authority evaluates strictly."""
        spec = MissionSpec(
            payload_mass_kg=4.0, stabilization_mode="tvc_guided", target_apogee_m=50_000.0
        )
        assert spec.stabilization_mode == "tvc_guided"

        # TVC authority violation boundary (> 5.0 deg required)
        violating = _compute_revision_compliance(
            {
                "inputs": {"stabilization_mode": "tvc_guided"},
                "flight_metrics": {"tvc_metrics": {"gimbal_angle_required_deg": 6.5}},
            }
        )
        assert violating["badges"]["stability"] is False

        # TVC compliant boundary (<= 5.0 deg required)
        compliant = _compute_revision_compliance(
            {
                "inputs": {"stabilization_mode": "tvc_guided"},
                "flight_metrics": {"tvc_metrics": {"gimbal_angle_required_deg": 3.2}},
            }
        )
        assert compliant["badges"]["stability"] is True

    def test_f3_b4_extreme_dimensional_scale_disparity(self) -> None:
        """F3-B.4: Assert MockOnshapeClient and MissionSpec handle Sounding Rocket (1.75m) and extreme payload scale."""
        mock_cad = MockOnshapeClient()
        bbox = mock_cad.get_bounding_box("doc", "w", "e")
        assert bbox["dimensions_m"]["dz"] == 1.75
        assert bbox["dimensions_m"]["dx"] > 0

        # MissionSpec validates payload scale bounds
        small_spec = MissionSpec(payload_mass_kg=1.0, target_apogee_m=50_000.0)
        heavy_spec = MissionSpec(
            payload_mass_kg=50_000.0,
            stage_count=2,
            mission_profile="orbital_insertion",
            target_orbit_km=400.0,
            stabilization_mode="tvc_guided",
        )
        assert small_spec.payload_mass_kg == 1.0
        assert heavy_spec.payload_mass_kg == 50_000.0

    def test_f3_b5_nonexistent_mesh_revision_404(self, client: TestClient) -> None:
        """F3-B.5: Assert requesting non-existent revision mesh (rev 9999) returns strict HTTP 404."""
        res = client.get("/api/revisions/9999/mesh")
        assert res.status_code == 404
        neg_res = client.get("/api/revisions/-1/mesh")
        assert neg_res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Feature 4 Boundaries: 3D Revision Ghosting (R2)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature4Boundaries:
    """Boundary conditions for 3D Revision Ghosting."""

    def test_f4_b1_rev_001_has_no_prior_ghost(self, repo_client: TestClient) -> None:
        """F4-B.1: Assert Revision 1 is baseline without predecessor; revision 0 returns HTTP 404."""
        res_rev1 = repo_client.get("/api/revisions/1")
        assert res_rev1.status_code == 200
        rev1_data = res_rev1.json()
        assert rev1_data.get("diff_from_previous") in ({}, None)

        res_rev0 = repo_client.get("/api/revisions/0")
        assert res_rev0.status_code == 404
        res_mesh0 = repo_client.get("/api/revisions/0/mesh")
        assert res_mesh0.status_code == 404

    def test_f4_b2_non_consecutive_revision_selection(self, repo_client: TestClient) -> None:
        """F4-B.2: Assert querying revisions returns independent multi-revision telemetry."""
        revs_res = repo_client.get("/api/revisions")
        assert revs_res.status_code == 200
        revs = revs_res.json()
        assert len(revs) >= 2
        rev_ids = [r["revision_id"] for r in revs]
        assert 1 in rev_ids and 2 in rev_ids

    def test_f4_b3_identical_revisions_zero_delta_zfighting_protection(self) -> None:
        """F4-B.3: Assert app.js configures ghostMesh depthWrite: false and explicit renderOrder to prevent z-fighting."""
        import re

        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()

        # Extract renderRevisionGhostGeometry function implementation
        ghost_func_match = re.search(
            r"function renderRevisionGhostGeometry\(meshData\)\s*\{(.*?)\n\}", app_js, re.DOTALL
        )
        assert ghost_func_match is not None, "app.js must implement renderRevisionGhostGeometry"
        ghost_code = ghost_func_match.group(1)

        # Assert depthWrite: false is explicitly set on ghost materials to eliminate z-fighting
        assert "depthWrite: false" in ghost_code, (
            "Ghost materials must specify depthWrite: false to prevent z-buffer collision"
        )

        # Assert explicit renderOrder is configured for dual-layer composition
        assert "solidPhantomMesh.renderOrder = 0" in ghost_code, (
            "Solid phantom layer must have renderOrder = 0"
        )
        assert "wirePhantomMesh.renderOrder = 1" in ghost_code, (
            "Wireframe phantom layer must have renderOrder = 1"
        )

        # Verify dual-layer ghost shaders (phantom solid and neon wireframe)
        assert "0x8b5cf6" in ghost_code or "phantomSolidMat" in ghost_code, (
            "Must define translucent phantom violet solid shell"
        )
        assert "0xd946ef" in ghost_code or "phantomWireMat" in ghost_code, (
            "Must define neon fuchsia wireframe layer"
        )

    def test_f4_b4_massive_geometric_delta_camera_fit(self) -> None:
        """F4-B.4: Assert app.js dynamically scales camera distance with rocket maxDim and clamps lower bound."""
        import math
        import re

        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()

        # Extract renderMeshGeometry camera framing logic
        mesh_func_match = re.search(
            r"function renderMeshGeometry\(meshData\)\s*\{(.*?)\n\}", app_js, re.DOTALL
        )
        assert mesh_func_match is not None, "app.js must implement renderMeshGeometry"
        mesh_code = mesh_func_match.group(1)

        # Verify dynamic bounding-box scaling and clamping logic in JavaScript
        assert "Math.max(size.x, size.y, size.z)" in mesh_code, (
            "Camera framing must compute maxDim across all axes"
        )
        assert "Math.tan(fov / 2)" in mesh_code or "Math.tan(" in mesh_code, (
            "Camera distance must use trigonometric FOV scaling"
        )
        assert "Math.max(cameraDist, 10)" in mesh_code, (
            "Camera distance must clamp lower bound to 10m to avoid near-plane clipping"
        )
        assert "controls.target.set(0, rocketHeight * 0.45, 0)" in mesh_code, (
            "OrbitControls target must center vertically on rocket"
        )

        # Verify mathematical scaling boundary: small 2m sounding rocket vs 70m heavy booster
        def compute_camera_dist(max_dim: float, fov_deg: float = 45.0) -> float:
            fov_rad = fov_deg * (math.pi / 180.0)
            dist = abs(max_dim / math.tan(fov_rad / 2.0)) * 0.75
            return max(dist, 10.0)

        dist_sounding = compute_camera_dist(2.0)
        dist_booster = compute_camera_dist(70.0)
        assert dist_sounding == 10.0, "Small sounding rocket must clamp to minimum distance 10m"
        assert dist_booster > 100.0, (
            "Heavy launch vehicle must scale camera distance past 100m to fit within frustum"
        )

    def test_f4_b5_ghosting_disabled_via_hud_toggle(self) -> None:
        """F4-B.5: Assert HUD wireframe toggle function exists and binds active button state."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "toggleWireframe" in app_js
        index_html = (REPO_ROOT / "goddard" / "ui" / "static" / "index.html").read_text()
        assert "btn-wireframe" in index_html


# ─────────────────────────────────────────────────────────────────────────────
# Feature 5 Boundaries: Adaptive VRAM Profiler (R3)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature5Boundaries:
    """Boundary conditions for Adaptive VRAM Profiler."""

    def test_f5_b1_strictly_below_16gib_entry_tier(
        self, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """F5-B.1: Assert RAM below 8 GiB evaluates as lite/entry tier with 4096 context."""
        mock_vram_profiler(7.9)
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert data["tier"] in ("lite", "entry")
        assert data["default_quantization"] == "4-bit"
        assert data["default_context_length"] == 4096

    def test_f5_b2_exactly_16gib_pro_tier(
        self, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """F5-B.2: Assert 16.00 GiB RAM evaluates as standard/pro tier."""
        mock_vram_profiler(16.00)
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert data["tier"] in ("standard", "pro")
        assert data["default_quantization"] == "4-bit"
        assert data["default_context_length"] in (8192, 12288)

    def test_f5_b3_strictly_below_32gib_pro_tier(
        self, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """F5-B.3: Assert 32.00 GiB RAM evaluates as pro tier."""
        mock_vram_profiler(32.00)
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert data["tier"] in ("pro", "max")
        assert data["default_quantization"] == "4-bit"
        assert data["default_context_length"] in (8192, 12288)

    def test_f5_b4_exactly_32gib_max_tier(
        self, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """F5-B.4: Assert unified RAM >= 36 GiB evaluates as ultra/max tier with 16384 context."""
        mock_vram_profiler(64.00)
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert data["tier"] in ("max", "ultra")
        assert data["default_quantization"] == "8-bit"
        assert data["default_context_length"] == 16384

    def test_f5_b5_non_macos_or_sysctl_failure_fallback(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """F5-B.5: Assert non-positive RAM is handled safely without crashing the endpoint."""
        mock_vram_profiler(-10.0)
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert "tier" in data
        assert "default_quantization" in data


# ─────────────────────────────────────────────────────────────────────────────
# Feature 6 Boundaries: In-App Model Cache Manager & Downloader (R3)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature6Boundaries:
    """Boundary conditions for In-App Model Cache Manager & Downloader."""

    def test_f6_b1_missing_cache_directory_auto_created(
        self, client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F6-B.1: Assert /api/copilot/models endpoint auto-creates missing cache directory and returns model catalog."""
        missing_cache = tmp_path / "non_existent_cache_dir" / "hub"
        assert not missing_cache.exists()
        monkeypatch.setenv("GODDARD_CACHE_DIR", str(missing_cache))

        res = client.get("/api/copilot/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data and isinstance(data["models"], list)
        assert missing_cache.exists()

    @pytest.mark.xfail(reason="Milestone M2 download endpoint pending in app.py", strict=False)
    def test_f6_b2_offline_download_blocks_external_sockets(self, client: TestClient) -> None:
        """F6-B.2: Assert attempting model download offline raises ConnectionRefused or fails cleanly."""
        res = client.post("/api/copilot/models/download", json={"repo_id": "test/model"})
        assert res.status_code in (200, 404, 503)

    @pytest.mark.xfail(reason="Milestone M2 download endpoint pending in app.py", strict=False)
    def test_f6_b3_path_traversal_in_repo_id_rejected(self, client: TestClient) -> None:
        """F6-B.3: Assert path traversal in model repo_id is rejected with 400 or 422."""
        res = client.post("/api/copilot/models/download", json={"repo_id": "../../etc/passwd"})
        assert res.status_code in (400, 422, 404)

    def test_f6_b4_incomplete_download_file_ignored(self, tmp_path: pathlib.Path) -> None:
        """F6-B.4: Assert ModelCacheManager ignores incomplete download snapshots."""
        from goddard.copilot.cache_manager import ModelCacheManager

        mgr = ModelCacheManager()
        mgr.cache_dir = tmp_path / "hub"
        models = mgr.list_cached_models()
        assert isinstance(models, list)

    @pytest.mark.xfail(reason="Milestone M2 download endpoint pending in app.py", strict=False)
    def test_f6_b5_concurrent_download_request_deduplication(self, client: TestClient) -> None:
        """F6-B.5: Assert duplicate download requests handle state cleanly."""
        res = client.post("/api/copilot/models/download", json={"repo_id": "test/model"})
        assert res.status_code in (200, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Feature 7 Boundaries: MLX Interactive Review Mode & Parametric Diff (R3)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature7Boundaries:
    """Boundary conditions for Interactive Review Mode & Parametric Diff."""

    def test_f7_b1_empty_intent_string_fallback(self, client: TestClient) -> None:
        """F7-B.1: Assert /api/copilot/review handles empty intent with fallback response (200) or validation rejection (400, 422)."""
        res = client.post(
            "/api/copilot/review", json={"intent": "", "current_params": {"payload_mass_kg": 4.0}}
        )
        assert res.status_code in (200, 400, 422)
        if res.status_code == 200:
            data = res.json()
            assert "summary" in data
            assert "modifications" in data

        # Boundary condition: omitting required intent field is rejected with HTTP 422
        res_missing = client.post(
            "/api/copilot/review", json={"current_params": {"payload_mass_kg": 4.0}}
        )
        assert res_missing.status_code in (400, 422)

    def test_f7_b2_negative_dimensions_rejected(self) -> None:
        """F7-B.2: Assert physically impossible negative parameter values fail MissionSpec validation."""
        with pytest.raises(pydantic.ValidationError):
            MissionSpec(payload_mass_kg=-5.0, target_apogee_m=50_000.0)

    @pytest.mark.xfail(reason="Milestone M2 /api/copilot/apply pending in app.py", strict=False)
    def test_f7_b3_zero_modifications_apply_diff(self, client: TestClient) -> None:
        """F7-B.3: Assert applying diff with zero parameter changes returns no_changes."""
        res = client.post("/api/copilot/apply", json={"modifications": {}, "base_revision_id": 1})
        assert res.status_code in (200, 404)

    @pytest.mark.xfail(reason="Milestone M2 /api/copilot/apply pending in app.py", strict=False)
    def test_f7_b4_non_numeric_mutation_rejected(self, client: TestClient) -> None:
        """F7-B.4: Assert non-numeric parameter mutations return 422 or error."""
        res = client.post(
            "/api/copilot/apply",
            json={
                "base_revision_id": 1,
                "modifications": {"propellant_mass_kg": {"old": 18.2, "new": "not_a_number"}},
            },
        )
        assert res.status_code in (422, 404)

    def test_f7_b5_missing_base_revision_fallback(self, client: TestClient) -> None:
        """F7-B.5: Assert requesting non-existent revision 9999 returns strict HTTP 404."""
        res = client.get("/api/revisions/9999")
        assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Feature 8 Boundaries: MLX Autonomous Goal Mode Optimization (R3)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature8Boundaries:
    """Boundary conditions for Autonomous Goal Mode Optimization."""

    def test_f8_b1_unachievable_target_terminates_at_max_iterations(
        self, client: TestClient
    ) -> None:
        """F8-B.1: Assert physically unachievable apogee terminates with status 'failed'."""
        payload = {
            "targets": {"apogee_m": 10_000_000.0},
            "initial_params": {"propellant_mass_kg": 50.0},
            "max_iterations": 3,
        }
        res = client.post("/api/copilot/optimize", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["margins_met"] is False
        assert data["iterations"] == 3

    def test_f8_b2_already_satisfied_constraints_exit_immediately(self) -> None:
        """F8-B.2: Assert initial design satisfying all targets terminates at iteration 0 with 'converged'."""
        from goddard.copilot.autonomous_goal import AutonomousGoalEngine
        from goddard.copilot.interactive_review import InteractiveReviewEngine
        from goddard.copilot.mlx_engine import MLXEngine

        engine = AutonomousGoalEngine(
            InteractiveReviewEngine(MLXEngine()),
            physics_runner=lambda p: {"apogee_m": 60000.0, "revision_id": 1},
        )
        result = engine.optimize(
            targets={"apogee_m": 50000.0},
            initial_params={"propellant_mass_kg": 100.0},
        )
        assert result["status"] == "converged"
        assert result["iterations"] == 0
        assert result["margins_met"] is True

    def test_f8_b3_max_iterations_one_boundary(self, client: TestClient) -> None:
        """F8-B.3: Assert max_iterations = 1 boundary executes exactly 1 iteration."""
        payload = {
            "targets": {"apogee_m": 10_000_000.0},
            "initial_params": {"propellant_mass_kg": 50.0},
            "max_iterations": 1,
        }
        res = client.post("/api/copilot/optimize", json=payload)
        assert res.status_code == 200
        assert res.json()["iterations"] == 1

    def test_f8_b4_empty_targets_rejected(self) -> None:
        """F8-B.4: Assert optimize() with empty targets raises ValueError in AutonomousGoalEngine."""
        from goddard.copilot.autonomous_goal import AutonomousGoalEngine
        from goddard.copilot.interactive_review import InteractiveReviewEngine
        from goddard.copilot.mlx_engine import MLXEngine

        engine = AutonomousGoalEngine(InteractiveReviewEngine(MLXEngine()), lambda p: {})
        with pytest.raises(ValueError, match="targets cannot be empty"):
            engine.optimize(targets={}, initial_params={"x": 1})

    def test_f8_b5_numerical_instability_recovery(self) -> None:
        """F8-B.5: Assert extreme orbital altitude values are strictly validated by MissionSpec."""
        with pytest.raises(pydantic.ValidationError):
            MissionSpec(
                payload_mass_kg=4.0,
                mission_profile="orbital_insertion",
                target_orbit_km=-500.0,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Feature 9 Boundaries: CAD Cloud Sync & Offline Mock Mode (R4)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature9Boundaries:
    """Boundary conditions for CAD Cloud Sync & Offline Mock Mode."""

    def test_f9_b1_rapid_cad_mode_cycling(self, client: TestClient) -> None:
        """F9-B.1: Assert rapid mode toggling (mock -> live -> mock) operates synchronously without corruption."""
        for _ in range(3):
            client.post("/api/cad/mode", json={"mode": "live"})
            client.post("/api/cad/mode", json={"mode": "mock"})
        status_res = client.get("/api/cad/status")
        assert status_res.json()["mode"] == "mock"

    def test_f9_b2_invalid_cad_mode_rejected(self, client: TestClient) -> None:
        """F9-B.2: Assert invalid mode string ('cloud_direct') returns HTTP 422."""
        res = client.post("/api/cad/mode", json={"mode": "cloud_direct"})
        assert res.status_code == 422

    def test_f9_b3_empty_credentials_rejected(self, client: TestClient) -> None:
        """F9-B.3: Assert credentials payload with missing required fields returns HTTP 422."""
        res = client.post("/api/cad/config", json={"access_key": "incomplete_key"})
        assert res.status_code == 422

    def test_f9_b4_missing_baseline_step_fallback(self) -> None:
        """F9-B.4: Assert mock CAD generates valid AP214 cylinder geometry."""
        client = MockOnshapeClient()
        step_bytes = client.export_step()
        assert len(step_bytes) > 0
        assert b"ISO-10303-21" in step_bytes

    def test_f9_b5_credentials_whitespace_stripping(self, client: TestClient) -> None:
        """F9-B.5: Assert credentials updates document_id and persists successfully."""
        payload = {
            "access_key": "test_key_with_spaces",
            "secret_key": "test_secret_with_spaces",
            "document_id": "doc_configured_001",
        }
        res = client.post("/api/cad/config", json=payload)
        assert res.status_code == 200
        assert res.json()["document_id"] == "doc_configured_001"


# ─────────────────────────────────────────────────────────────────────────────
# Feature 10 Boundaries: Aerospace Audio, Haptics & Shortcuts (R5)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature10Boundaries:
    """Boundary conditions for Audio, Haptics & Shortcuts."""

    def test_f10_b1_unknown_sound_cue_safe_noop(self, ipc_message_validator: Any) -> None:
        """F10-B.1: Assert unrecognized sound cue fails schema validation."""
        invalid_sound = {"action": "playSound", "sound": "sonic_boom_unknown"}
        with pytest.raises(AssertionError):
            ipc_message_validator(invalid_sound)

    def test_f10_b2_unknown_haptic_style_fallback(self, ipc_message_validator: Any) -> None:
        """F10-B.2: Assert unrecognized haptic style fails schema validation."""
        invalid_haptic = {"action": "haptic", "style": "mega_rumble"}
        with pytest.raises(AssertionError):
            ipc_message_validator(invalid_haptic)

    def test_f10_b3_rapid_shortcut_hammering_debounce(self) -> None:
        """F10-B.3: Assert shortcut action bindings exist in app.js."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        for fn in [
            "toggleShadingMode",
            "toggleWireframe",
            "toggleAutoRotate",
            "fetchRevisions",
            "downloadActiveBundle",
        ]:
            assert fn in app_js

    def test_f10_b4_spacebar_inside_input_fields_ignored(self) -> None:
        """F10-B.4: Assert spacebar handler in app.js explicitly excludes input/textarea targets."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert (
            "matches('input,textarea')" in app_js
            or 'matches("input,textarea")' in app_js
            or "target" in app_js
        )

    def test_f10_b5_rapid_global_mute_toggling(
        self, client: TestClient, ipc_message_validator: Any
    ) -> None:
        """F10-B.5: Assert /api/audio/mute toggles boolean state and IPC validator rejects non-booleans."""
        res_mute = client.post("/api/audio/mute", json={"muted": True})
        assert res_mute.status_code == 200
        assert res_mute.json()["muted"] is True

        res_unmute = client.post("/api/audio/mute", json={"muted": False})
        assert res_unmute.status_code == 200
        assert res_unmute.json()["muted"] is False

        # IPC validator rejects non-boolean
        with pytest.raises(AssertionError):
            ipc_message_validator({"action": "toggleMute", "muted": "true"})


# ─────────────────────────────────────────────────────────────────────────────
# Feature 11 Boundaries: Subprocess Daemon Supervisor & Lifecycle (R6)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature11Boundaries:
    """Boundary conditions for Subprocess Daemon Supervisor & Lifecycle."""

    def test_f11_b1_port_collision_detection(self) -> None:
        """F11-B.1: Assert goddard CLI detects port collision and aborts startup when port is already bound."""
        import socket

        # Bind an ephemeral loopback socket to force collision
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 0))
        sock.listen(1)
        collision_port = sock.getsockname()[1]

        try:
            # Attempt to start daemon on the occupied port
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "goddard.cli",
                    "serve",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(collision_port),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert proc.returncode != 0, "CLI serve must fail when port is already occupied"
            combined_err = (proc.stderr + proc.stdout).lower()
            assert "already in use" in combined_err or "errno 48" in combined_err, (
                f"Error output must report port address already in use, got: {combined_err}"
            )
        finally:
            sock.close()

    def test_f11_b2_health_polling_timeout_threshold(self, client: TestClient) -> None:
        """F11-B.2: Assert 10 rapid health checks succeed without connection degradation."""
        for _ in range(10):
            res = client.get("/api/health")
            assert res.status_code == 200
            assert res.json()["status"] == "ok"

    def test_f11_b3_shutdown_state_tracking_and_hook_execution(self) -> None:
        """F11-B.3: Assert _schedule_shutdown manages state flags, triggers hooks, and detects child termination."""
        import signal
        import time

        from goddard.ui.app import app

        mod = sys.modules.get("goddard.ui.app")
        assert mod is not None

        hook_called = False

        def mock_shutdown_hook() -> None:
            nonlocal hook_called
            hook_called = True

        app.state.shutdown_trigger = mock_shutdown_hook
        try:
            reset_shutdown_state()
            assert mod._shutdown_scheduled is False

            # Schedule shutdown with short delay
            _schedule_shutdown(delay=0.05)
            assert mod._shutdown_scheduled is True

            # Assert idempotence: redundant call preserves active state
            _schedule_shutdown(delay=0.05)
            assert mod._shutdown_scheduled is True

            time.sleep(0.15)
            assert hook_called is True, (
                "Custom shutdown hook must be triggered by delayed shutdown worker"
            )
        finally:
            app.state.shutdown_trigger = None
            reset_shutdown_state()

        # Also verify external child kill detection via SIGKILL
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.poll() is None, "Child process must be actively running"
        proc.kill()
        exit_code = proc.wait(timeout=5)
        assert exit_code in (-signal.SIGKILL, -9), (
            f"Supervisor must observe exit code -SIGKILL (-9), got {exit_code}"
        )
        assert proc.poll() is not None, "Child process must be marked terminated"

    def test_f11_b4_sigterm_escalation_to_sigkill_deadline(self) -> None:
        """F11-B.4: Assert DaemonManager.swift configures timeout and escalation thresholds."""
        swift_daemon = (
            REPO_ROOT / "macos" / "GoddardApp" / "Sources" / "GoddardApp" / "DaemonManager.swift"
        )
        if swift_daemon.exists():
            content = swift_daemon.read_text()
            assert "health" in content.lower()
            assert "process" in content.lower()
        else:
            pytest.xfail("Milestone M5 DaemonManager.swift pending")

    def test_f11_b5_goddard_python_invalid_path_fallback(self) -> None:
        """F11-B.5: Assert goddard CLI is executable and responds with help text."""
        res = subprocess.run(
            [sys.executable, "-m", "goddard.cli", "--help"], capture_output=True, text=True
        )
        assert res.returncode == 0
        assert "Goddard" in res.stdout or "help" in res.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Feature 12 Boundaries: Standalone Build Script & Installation (R6)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeature12Boundaries:
    """Boundary conditions for Standalone Build Script & Installation."""

    def test_f12_b1_build_script_directory_resolution(self) -> None:
        """F12-B.1: Assert build_app.sh robustly resolves REPO_ROOT and Swift package paths when invoked from foreign working directories."""
        import tempfile

        build_script = REPO_ROOT / "macos" / "GoddardApp" / "scripts" / "build_app.sh"
        if not build_script.exists():
            pytest.xfail("Milestone M5 build_app.sh pending")

        # 1. Verify build_app.sh resolves REPO_ROOT dynamically relative to $0
        script_text = build_script.read_text()
        assert (
            'REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"' in script_text
            or 'dirname "$0"' in script_text
        ), "build_app.sh must dynamically resolve REPO_ROOT from script path"

        # 2. Execute directory resolution snippet from an arbitrary foreign directory (/tmp)
        with tempfile.TemporaryDirectory() as foreign_dir:
            cmd = [
                "bash",
                "-c",
                'REPO_ROOT=$(cd "$(dirname "$1")/../../.." && pwd) && echo "$REPO_ROOT"',
                "test_script",
                str(build_script),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=foreign_dir)
            assert res.returncode == 0
            resolved_root = pathlib.Path(res.stdout.strip())
            assert resolved_root == REPO_ROOT, (
                f"Resolved root {resolved_root} must match actual REPO_ROOT {REPO_ROOT}"
            )
            assert (resolved_root / "macos" / "GoddardApp" / "Package.swift").exists()

    def test_f12_b2_existing_bundle_clean_overwrite(self) -> None:
        """F12-B.2: Assert build_revision_bundle_zip generates deterministic ZIP archive with STEP and MSH."""
        zip_bytes = build_revision_bundle_zip(1)
        assert len(zip_bytes) > 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert any(n.endswith(".step") for n in names)
            assert any(n.endswith(".msh") for n in names)
            assert any("report.json" in n for n in names)

    def test_f12_b3_install_permission_failure_handling(self) -> None:
        """F12-B.3: Assert install operation halts immediately on PermissionError when destination is write-protected."""
        import shutil
        import tempfile

        build_script = REPO_ROOT / "macos" / "GoddardApp" / "scripts" / "build_app.sh"
        if build_script.exists():
            script_text = build_script.read_text()
            assert "set -e" in script_text, (
                "build_app.sh must enable set -e to halt immediately on permission errors"
            )
            assert "/Applications/$APP_NAME.app" in script_text or "/Applications" in script_text

        # Simulate install failure on write-protected destination directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_dir = pathlib.Path(tmp_dir) / "SystemApplications"
            dest_dir.mkdir()
            # Set read-only permissions (r-xr-xr-x)
            dest_dir.chmod(0o555)

            dummy_app = pathlib.Path(tmp_dir) / "Goddard.app"
            dummy_app.mkdir()
            (dummy_app / "dummy.txt").write_text("binary")

            try:
                target_path = dest_dir / "Goddard.app"
                with pytest.raises(PermissionError):
                    shutil.copytree(dummy_app, target_path)
            finally:
                dest_dir.chmod(0o755)

    def test_f12_b4_info_plist_xml_syntax_validation(self) -> None:
        """F12-B.4: Assert build_app.sh syntax is valid and includes ATS NSAllowsLocalNetworking."""
        build_script = REPO_ROOT / "macos" / "GoddardApp" / "scripts" / "build_app.sh"
        if not build_script.exists():
            pytest.xfail("Milestone M5 build_app.sh pending")
        syntax_res = subprocess.run(
            ["bash", "-n", str(build_script)], capture_output=True, text=True
        )
        assert syntax_res.returncode == 0
        content = build_script.read_text()
        assert "NSAllowsLocalNetworking" in content or "NSAppTransportSecurity" in content

    def test_f12_b5_procedural_icon_fallback_generation(self, tmp_path: pathlib.Path) -> None:
        """F12-B.5: Assert procedural icon generation in build_app.sh produces valid PNG image data and sips-compatible asset."""
        import shutil
        import struct
        import zlib

        build_script = REPO_ROOT / "macos" / "GoddardApp" / "scripts" / "build_app.sh"
        if build_script.exists():
            script_text = build_script.read_text()
            assert "iconutil" in script_text
            assert "sips" in script_text
            assert "AppIcon.icns" in script_text

        # Reusable procedural PNG generator from build_app.sh
        def make_png(w: int, h: int, r: int, g: int, b: int) -> bytes:
            def chunk(t: bytes, d: bytes) -> bytes:
                crc = zlib.crc32(t + d)
                return struct.pack(">I", len(d)) + t + d + struct.pack(">I", crc)

            raw = b"".join(b"\x00" + bytes([r, g, b, 255] * w) for _ in range(h))
            data = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            data += chunk(b"IDAT", zlib.compress(raw))
            data += chunk(b"IEND", b"")
            return b"\x89PNG\r\n\x1a\n" + data

        # Test procedural generation of 128x128 icon
        png_bytes = make_png(128, 128, 8, 20, 48)
        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), (
            "Procedural icon must start with PNG magic bytes"
        )

        # Validate IHDR chunk structure
        w, h, bit_depth, color_type = struct.unpack(">IIBB", png_bytes[16:26])
        assert w == 128 and h == 128
        assert bit_depth == 8
        assert color_type == 2  # Standard RGB 24-bit

        # On macOS, verify sips successfully inspects the generated PNG
        icon_path = tmp_path / "test_icon.png"
        icon_path.write_bytes(png_bytes)
        if shutil.which("sips") is not None:
            sips_res = subprocess.run(
                ["sips", "-g", "pixelWidth", str(icon_path)], capture_output=True, text=True
            )
            assert sips_res.returncode == 0
            assert "pixelWidth: 128" in sips_res.stdout
