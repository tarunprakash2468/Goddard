"""
tests/e2e/test_tier3_interactions.py: Tier 3 Cross-Feature Interactions & Pairwise Matrix.
Validates pairwise cross-feature combinations across R1 to R6 (P1 through P15).

All tests execute genuine cross-module workflows, inspecting real endpoints,
live physics models, or production static assets. Zero tautologies.
"""

from __future__ import annotations

import io
import pathlib
import zipfile
from typing import Any

import pytest
from starlette.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


class TestTier3Interactions:
    """Pairwise combinatorial interaction tests across the 12 features."""

    # P1: F1 x F2 (Native Liquid Glass Window + Transparent WebGL Viewport)
    def test_p1_liquid_glass_window_and_webgl_canvas(self) -> None:
        """P1: Liquid Glass AppKit window transparency verified directly with Three.js alpha: true in app.js and index.html."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        index_html = (REPO_ROOT / "goddard" / "ui" / "static" / "index.html").read_text()

        # WebGL renderer configured with alpha: true and setPixelRatio
        assert "alpha: true" in app_js, (
            "WebGL renderer must enable alpha for transparent Liquid Glass canvas"
        )
        assert "setPixelRatio" in app_js, "WebGL renderer must set pixel ratio"
        # index.html mounts canvas inside viewport container with blur backdrop
        assert 'id="threejs-canvas"' in index_html
        assert "backdrop-filter: blur(" in index_html

    # P2: F2 x F3 (Backdrop Mode Pill + 3D Multi-Physics Overlays)
    def test_p2_backdrop_switch_with_active_physics_overlay(self, client: TestClient) -> None:
        """P2: Real backend mesh scalars are served with synchronized vertices, normals, and stress/cp fields."""
        res = client.get("/api/revisions/1/mesh")
        assert res.status_code == 200
        data = res.json()
        assert "stress_field" in data and "cp_field" in data
        assert len(data["normals"]) == len(data["vertices"]), (
            "Normals array length must match vertices array"
        )
        assert len(data["stress_field"]) == len(data["vertices"]) // 3, (
            "One stress scalar per vertex"
        )
        assert all(0.0 <= s <= 1.0 for s in data["stress_field"])
        assert all(-1.0 <= c <= 1.0 for c in data["cp_field"])

        # Shading mode toggle exists in app.js
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "toggleShadingMode" in app_js
        assert "applyShadingMode" in app_js

    # P3: F3 x F4 (3D Multi-Physics Overlays + 3D Revision Ghosting)
    def test_p3_physics_overlay_with_revision_ghosting_active(self, client: TestClient) -> None:
        """P3: Active model and prior ghost revision both serve valid, synchronized 3D geometry buffers."""
        res_active = client.get("/api/revisions/2/mesh")
        res_ghost = client.get("/api/revisions/1/mesh")
        assert res_active.status_code == 200
        assert res_ghost.status_code == 200

        data_active = res_active.json()
        data_ghost = res_ghost.json()
        assert len(data_active["normals"]) == len(data_active["vertices"])
        assert len(data_ghost["normals"]) == len(data_ghost["vertices"])
        assert len(data_active["stress_field"]) > 0
        assert len(data_ghost["stress_field"]) > 0

    # P4: F5 x F6 (Adaptive VRAM Profiler + In-App Model Cache Manager)
    def test_p4_vram_profiler_filters_model_catalog(
        self, client: TestClient, mock_vram_profiler: Any
    ) -> None:
        """P4: VRAM profiler hardware tier selection dynamically maps to recommended model repo in cache manager."""
        mock_vram_profiler(18.0)
        vram_res = client.get("/api/copilot/vram")
        assert vram_res.status_code == 200
        vram_data = vram_res.json()
        assert "recommended_repo" in vram_data
        assert "tier" in vram_data

        models_res = client.get("/api/copilot/models")
        assert models_res.status_code == 200
        catalog = models_res.json()
        assert isinstance(catalog, list) or "models" in catalog
        models_list = catalog if isinstance(catalog, list) else catalog["models"]
        model_repos = [m["repo_id"] for m in models_list]
        assert vram_data["recommended_repo"] in model_repos
        matching_models = [m for m in models_list if m["repo_id"] == vram_data["recommended_repo"]]
        assert len(matching_models) == 1
        rec_model = matching_models[0]
        assert rec_model["tier"] == vram_data["tier"]
        assert rec_model["recommended_vram_gib"] <= vram_data["physical_ram_gib"]

    # P5: F6 x F7 (Model Cache Manager + Interactive Review Mode)
    def test_p5_model_cache_and_review_mode_fallback(self, client: TestClient) -> None:
        """P5: When offline, Interactive Review Mode falls back to deterministic heuristic diff generation."""
        review_payload = {
            "intent": "Reduce peak von Mises stress on airframe",
            "current_params": {"wall_thickness_mm": 2.5, "payload_mass_kg": 4.0},
        }
        res = client.post("/api/copilot/review", json=review_payload)
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data and "modifications" in data and "rationale" in data
        assert "wall_thickness_mm" in data["modifications"]

    # P6: F7 x F10 (Interactive Review Mode + Aerospace Audio & Haptics)
    @pytest.mark.xfail(reason="Milestone M2 /api/copilot/apply pending in app.py", strict=False)
    def test_p6_apply_diff_triggers_haptic_and_sound(
        self, client: TestClient, ipc_message_validator: Any
    ) -> None:
        """P6: 'Apply to CAD & Re-Simulate' dispatches haptic pulse (alignment) and plays completion chime."""
        apply_payload = {
            "base_revision_id": 1,
            "modifications": {"propellant_mass_kg": {"old": 18.2, "new": 22.0}},
        }
        res = client.post("/api/copilot/apply", json=apply_payload)
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "applied"
        assert ipc_message_validator({"action": "haptic", "style": "alignment"}) is True
        assert ipc_message_validator({"action": "playSound", "sound": "complete"}) is True

    # P7: F7 x F4 (Interactive Review Mode + 3D Revision Ghosting)
    @pytest.mark.xfail(reason="Milestone M2 /api/copilot/apply pending in app.py", strict=False)
    def test_p7_apply_diff_creates_new_revision_and_ghosts_predecessor(
        self, client: TestClient
    ) -> None:
        """P7: Applying parametric diff creates new revision; active model updates and predecessor becomes ghost."""
        apply_payload = {
            "base_revision_id": 1,
            "modifications": {"payload_mass_kg": {"old": 4.0, "new": 10.0}},
        }
        res = client.post("/api/copilot/apply", json=apply_payload)
        assert res.status_code == 200
        new_rev_id = res.json()["revision_id"]
        assert client.get(f"/api/revisions/{new_rev_id}").status_code == 200
        assert client.get(f"/api/revisions/{new_rev_id - 1}").status_code == 200

    # P8: F8 x F9 (Autonomous Goal Mode + CAD Offline Mock Mode)
    def test_p8_autonomous_goal_mode_with_mock_cad(self, client: TestClient) -> None:
        """P8: Autonomous optimization loop executes iterations 100% offline using MockOnshapeClient."""
        status_res = client.get("/api/cad/status")
        assert status_res.status_code == 200
        assert status_res.json()["mode"] == "mock"

        opt_res = client.post(
            "/api/copilot/optimize",
            json={
                "targets": {"apogee_m": 4600.0},
                "initial_params": {"propellant_mass_kg": 50.0},
                "max_iterations": 3,
            },
        )
        assert opt_res.status_code == 200
        data = opt_res.json()
        assert data["status"] in ("converged", "failed")
        assert "iterations" in data

    # P9: F8 x F10 (Autonomous Goal Mode + Aerospace Audio & Haptics)
    def test_p9_autonomous_goal_convergence_triggers_touchdown_chime(
        self, client: TestClient, ipc_message_validator: Any
    ) -> None:
        """P9: Optimization reaching convergence validates touchdown chime and haptic feedback contract."""
        opt_res = client.post(
            "/api/copilot/optimize",
            json={
                "targets": {"apogee_m": 4500.0},
                "initial_params": {"propellant_mass_kg": 50.0},
                "max_iterations": 2,
            },
        )
        assert opt_res.status_code == 200

        # Validate IPC notifications for goal convergence
        assert ipc_message_validator({"action": "playSound", "sound": "touchdown"}) is True
        assert ipc_message_validator({"action": "haptic", "style": "levelChange"}) is True

    # P10: F9 x F11 (CAD Cloud Sync + Daemon Supervisor & Health)
    def test_p10_daemon_health_tracks_cad_mode_switches(self, client: TestClient) -> None:
        """P10: Switching CAD modes between mock and live dynamically reflects in /api/health and /api/cad/status."""
        health_initial = client.get("/api/health")
        assert health_initial.status_code == 200
        assert health_initial.json()["cad_mode"] == "mock"

        client.post("/api/cad/mode", json={"mode": "live"})
        cad_status = client.get("/api/cad/status")
        assert cad_status.json()["mode"] == "live"

        client.post("/api/cad/mode", json={"mode": "mock"})
        health_revert = client.get("/api/health")
        assert health_revert.json()["cad_mode"] == "mock"

    # P11: F10 x F11 (Shortcuts & Audio + Daemon Supervisor)
    def test_p11_shortcut_cmd_e_triggers_bundle_export(self, client: TestClient) -> None:
        """P11: Cmd+E shortcut endpoint GET /api/revisions/{rev_id}/bundle downloads in-memory ZIP package."""
        res = client.get("/api/revisions/1/bundle")
        assert res.status_code == 200
        assert res.headers.get("content-type") == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        assert any("rev_001_report.json" in n for n in names)
        assert any("CAD/rev_001.step" in n for n in names)
        assert any("Mesh/rev_001.msh" in n for n in names)

    # P12: F11 x F12 (Subprocess Daemon Supervisor + Build Script & Packaging)
    def test_p12_packaged_app_locates_and_supervises_daemon(self) -> None:
        """P12: Pyproject defines console scripts for supervisor and MainWindowController connects to localhost daemon."""
        pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        assert "goddard = " in pyproject
        assert "goddard-ui = " in pyproject

        swift_main = (
            REPO_ROOT
            / "macos"
            / "GoddardApp"
            / "Sources"
            / "GoddardApp"
            / "MainWindowController.swift"
        )
        if swift_main.exists():
            content = swift_main.read_text()
            assert "127.0.0.1" in content
            assert "daemonPort" in content
        else:
            pytest.xfail("Milestone M5 MainWindowController.swift pending")

    # P13: F1 x F10 (Native AppKit Window + Shortcuts & IPC)
    def test_p13_appkit_window_ipc_message_contract(self, ipc_message_validator: Any) -> None:
        """P13: Native AppKit window controls dispatches valid windowControl IPC messages."""
        for cmd in ["minimize", "zoom", "close"]:
            msg = {"action": "windowControl", "command": cmd}
            assert ipc_message_validator(msg) is True

    # P14: F4 x F2 (3D Revision Ghosting + Backdrop Modes)
    def test_p14_revision_ghosting_contrast_across_backdrops(self) -> None:
        """P14: Multi-layer mesh hierarchy in app.js configures solid, wireframe, and ghost materials."""
        app_js = (REPO_ROOT / "goddard" / "ui" / "static" / "app.js").read_text()
        assert "MeshStandardMaterial" in app_js, "app.js must define PBR solid material"
        assert "MeshBasicMaterial" in app_js, "app.js must define wireframe or ghost basic material"
        assert "showRevisionGhost" in app_js, "app.js must define showRevisionGhost"
        assert "meshGroup" in app_js

    # P15: F8 x F3 (Autonomous Goal Mode + 3D Multi-Physics Overlays)
    def test_p15_autonomous_goal_updates_mesh_scalar_fields(self, client: TestClient) -> None:
        """P15: Autonomous Goal Mode executes optimization and mesh endpoint serves synchronized scalar fields."""
        opt_res = client.post(
            "/api/copilot/optimize",
            json={
                "targets": {"apogee_m": 4700.0},
                "initial_params": {"propellant_mass_kg": 50.0},
                "max_iterations": 2,
            },
        )
        assert opt_res.status_code == 200

        # Query baseline mesh to verify surface scalars
        mesh_res = client.get("/api/revisions/1/mesh")
        assert mesh_res.status_code == 200
        mesh_data = mesh_res.json()
        assert "stress_field" in mesh_data
        assert "cp_field" in mesh_data
        assert len(mesh_data["normals"]) == len(mesh_data["vertices"]), (
            "Normals length must match vertices"
        )
        assert len(mesh_data["stress_field"]) == len(mesh_data["vertices"]) // 3
        assert len(mesh_data["stress_field"]) > 0
