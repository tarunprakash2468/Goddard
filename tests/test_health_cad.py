"""
Comprehensive Unit & Regression Tests for:
- Daemon Health and Lifecycle Shutdown API
- CAD Cloud Sync & Offline Mock Mode Integration
- MockOnshapeClient Parity & Conftest Compatibility
- 3D Mesh Surface Scalar Extraction (Interface Contract 2)
- Design Bundle ZIP Export Endpoint & CLI Subcommand
100% Offline Test Isolation.
"""

from __future__ import annotations

import io
import os
import pathlib
import time
import unittest.mock
import zipfile

import pytest
from starlette.testclient import TestClient

from goddard import __version__
from goddard.client.cad_state import CADStateManager, cad_state
from goddard.client.mock import MockOnshapeClient
from goddard.ui.app import (
    _compute_surface_scalars,
    app,
    build_revision_bundle_zip,
    reset_shutdown_state,
)


@pytest.fixture(autouse=True)
def clean_shutdown_state() -> None:
    reset_shutdown_state()
    yield
    reset_shutdown_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── 1. Daemon Health & Lifecycle Tests ─────────────────────────────────────────


class TestDaemonHealth:
    """Verifies GET /api/health meets Interface Contract 1."""

    def test_health_nominal(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__
        assert data["version"] == "0.1.0"
        assert data["pid"] == os.getpid()
        assert data["cad_mode"] in ("mock", "live")
        assert data["copilot_ready"] is True

    def test_health_cad_mode_reflection(self, client: TestClient) -> None:
        orig_mode = cad_state.mode
        try:
            cad_state.set_mode("live")
            res_live = client.get("/api/health")
            assert res_live.status_code == 200
            assert res_live.json()["cad_mode"] == "live"

            cad_state.set_mode("mock")
            res_mock = client.get("/api/health")
            assert res_mock.status_code == 200
            assert res_mock.json()["cad_mode"] == "mock"
        finally:
            cad_state.set_mode(orig_mode)

    def test_health_copilot_disabled_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GODDARD_COPILOT_DISABLED", "1")
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["copilot_ready"] is False


class TestDaemonLifecycle:
    """Verifies POST /api/lifecycle/shutdown and process termination safeguards."""

    def test_shutdown_endpoint_response(self, client: TestClient) -> None:
        response = client.post("/api/lifecycle/shutdown")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shutting_down"
        assert "Daemon shutting down cleanly" in data["message"]

    def test_shutdown_triggers_custom_hook(self, client: TestClient) -> None:
        hook_called: list[bool] = []
        app.state.shutdown_trigger = lambda: hook_called.append(True)
        try:
            res = client.post("/api/lifecycle/shutdown")
            assert res.status_code == 200
            time.sleep(0.15)
            assert len(hook_called) == 1
            assert hook_called[0] is True
        finally:
            app.state.shutdown_trigger = None

    def test_shutdown_safe_in_test_client(self, client: TestClient) -> None:
        # Multiple invocations under pytest do not kill the test runner
        for _ in range(3):
            res = client.post("/api/lifecycle/shutdown")
            assert res.status_code == 200

    def test_shutdown_endpoint_idempotency(self, client: TestClient) -> None:
        hook_calls: list[int] = []
        app.state.shutdown_trigger = lambda: hook_calls.append(1)
        try:
            for _ in range(5):
                res = client.post("/api/lifecycle/shutdown")
                assert res.status_code == 200
                assert res.json()["status"] == "shutting_down"
            time.sleep(0.2)
            assert len(hook_calls) == 1
        finally:
            app.state.shutdown_trigger = None


# ── 2. CAD Cloud Sync & Mode Tests ───────────────────────────────────────────


class TestCADStateAndEndpoints:
    """Verifies GET /api/cad/status, POST /api/cad/mode, and POST /api/cad/config."""

    def test_cad_status_default_mock(self, client: TestClient) -> None:
        orig_mode = cad_state.mode
        try:
            cad_state.set_mode("mock")
            res = client.get("/api/cad/status")
            assert res.status_code == 200
            data = res.json()
            assert data["mode"] == "mock"
            assert data["connected"] is False
            assert "document_id" in data
            assert isinstance(data["access_key_configured"], bool)
        finally:
            cad_state.set_mode(orig_mode)

    def test_cad_mode_switch_to_live_offline(self, client: TestClient) -> None:
        orig_mode = cad_state.mode
        try:
            res = client.post("/api/cad/mode", json={"mode": "live"})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["mode"] == "live"
            # In offline test environment, connected must be False without crashing
            assert data["connected"] is False
        finally:
            cad_state.set_mode(orig_mode)

    def test_cad_mode_switch_to_mock(self, client: TestClient) -> None:
        orig_mode = cad_state.mode
        try:
            res = client.post("/api/cad/mode", json={"mode": "mock"})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["mode"] == "mock"
            assert data["connected"] is False
        finally:
            cad_state.set_mode(orig_mode)

    def test_cad_mode_invalid_body_rejected(self, client: TestClient) -> None:
        res = client.post("/api/cad/mode", json={"mode": "invalid_mode"})
        assert res.status_code == 422

    def test_cad_config_update_and_persistence(
        self, client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("EXISTING_KEY=123\n", encoding="utf-8")
        monkeypatch.setenv("GODDARD_ENV_FILE", str(env_file))

        orig_env = {
            k: os.environ.get(k)
            for k in [
                "ONSHAPE_ACCESS_KEY",
                "ONSHAPE_SECRET_KEY",
                "ONSHAPE_DOCUMENT_ID",
                "ONSHAPE_DID",
            ]
        }

        try:
            payload = {
                "access_key": "test_ak_key_999",
                "secret_key": "test_sk_key_888",
                "document_id": "test_doc_777",
            }
            res = client.post("/api/cad/config", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["configured"] is True
            assert data["document_id"] == "test_doc_777"

            # Verify environment variable synchronization
            assert os.environ["ONSHAPE_ACCESS_KEY"] == "test_ak_key_999"
            assert os.environ["ONSHAPE_SECRET_KEY"] == "test_sk_key_888"
            assert os.environ["ONSHAPE_DOCUMENT_ID"] == "test_doc_777"
            assert os.environ["ONSHAPE_DID"] == "test_doc_777"

            # Verify file persistence
            content = env_file.read_text(encoding="utf-8")
            assert "EXISTING_KEY=123" in content
            assert "ONSHAPE_ACCESS_KEY=test_ak_key_999" in content
            assert "ONSHAPE_DOCUMENT_ID=test_doc_777" in content

            # Verify GET /api/cad/status reflects new config
            status_res = client.get("/api/cad/status")
            assert status_res.status_code == 200
            status_data = status_res.json()
            assert status_data["document_id"] == "test_doc_777"
            assert status_data["access_key_configured"] is True
        finally:
            for k, v in orig_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            cad_state._load_from_env()

    def test_cad_config_invalid_body(self, client: TestClient) -> None:
        res = client.post("/api/cad/config", json={})
        assert res.status_code == 422

    def test_cad_config_null_bytes_rejected(self, client: TestClient) -> None:
        res = client.post(
            "/api/cad/config",
            json={"access_key": "bad\x00key", "secret_key": "sec", "document_id": "doc"},
        )
        assert res.status_code == 422

    def test_cad_config_newlines_rejected(self, client: TestClient) -> None:
        res_newline = client.post(
            "/api/cad/config",
            json={"access_key": "key\ninjected=true", "secret_key": "sec", "document_id": "doc"},
        )
        assert res_newline.status_code == 422

        res_cr = client.post(
            "/api/cad/config",
            json={"access_key": "valid_key", "secret_key": "sec\rinjected", "document_id": "doc"},
        )
        assert res_cr.status_code == 422

    def test_cad_state_placeholder_credentials_default_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "your_access_key_here")
        monkeypatch.setenv("ONSHAPE_SECRET_KEY", "your_secret_key_here")
        monkeypatch.delenv("GODDARD_OFFLINE_MODE", raising=False)
        monkeypatch.delenv("GODDARD_MOCK_ONSHAPE", raising=False)

        mgr = CADStateManager()
        assert mgr.mode == "mock"
        assert mgr.access_key_configured is False

        with unittest.mock.patch("requests.get") as mock_get:
            connected = mgr.check_connection()
            assert connected is False
            assert not mock_get.called, "Outbound request attempted with placeholder keys!"

        mgr.mode = "live"
        with unittest.mock.patch("requests.get") as mock_get:
            connected = mgr.check_connection()
            assert connected is False
            assert not mock_get.called, (
                "Outbound request attempted in live mode with placeholder keys!"
            )

    def test_cad_state_manager_offline_check_connection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = CADStateManager()
        manager.mode = "live"
        manager.access_key = "dummy_ak"
        manager.secret_key = "dummy_sk"
        monkeypatch.setenv("GODDARD_OFFLINE_MODE", "true")
        assert manager.check_connection() is False


# ── 3. MockOnshapeClient Parity & Compatibility Tests ─────────────────────────


class TestMockOnshapeClient:
    """Verifies MockOnshapeClient feature parity and fixture compatibility."""

    def test_mock_client_conftest_fixture_compatibility(self) -> None:
        client = MockOnshapeClient(
            access_key="mock_ak",
            secret_key="mock_sk",
            base_url="https://mock.onshape.test",
            extra_param="ignored",
        )
        assert client.access_key == "mock_ak"
        assert client.secret_key == "mock_sk"
        assert client.base_url == "https://mock.onshape.test"

    def test_mock_client_session_info(self) -> None:
        client = MockOnshapeClient()
        info = client.get_session_info()
        assert isinstance(info, dict)
        assert info.get("id") == "mock_user"

    def test_mock_client_get_document(self) -> None:
        client = MockOnshapeClient()
        doc = client.get_document("doc_xyz_123")
        assert isinstance(doc, dict)
        assert doc.get("id") == "doc_xyz_123"
        assert "Mock Rocket Document" in doc.get("name", "")

    def test_mock_client_export_step_offline(self) -> None:
        client = MockOnshapeClient()
        step_bytes = client.export_step("did", "wid", "eid")
        assert isinstance(step_bytes, bytes)
        assert step_bytes.startswith(b"ISO-10303-21;")

    def test_mock_client_mass_properties(self) -> None:
        client = MockOnshapeClient()
        mp = client.get_mass_properties("did", "wid", "eid")
        assert mp["volume_m3"] > 0
        assert mp["mass_kg"] > 0
        assert len(mp["center_of_mass_m"]) == 3

    def test_mock_client_get_bounding_box_eid_keyword(self) -> None:
        client = MockOnshapeClient()
        bb_eid = client.get_bounding_box(did="doc1", wid="w1", eid="element1")
        assert "xmin" in bb_eid
        assert "dimensions_m" in bb_eid
        assert bb_eid["dimensions_m"]["dx"] > 0

        bb_part_eid = client.get_bounding_box(did="doc1", wid="w1", part_eid="element2")
        assert "xmin" in bb_part_eid

        bb_kwargs = client.get_bounding_box(
            did="doc1", wid="w1", eid="element3", arbitrary_extra=True
        )
        assert "xmin" in bb_kwargs

    def test_cad_state_manager_get_client_mock_and_live(self) -> None:
        manager = CADStateManager()
        manager.mode = "mock"
        c_mock = manager.get_client()
        assert isinstance(c_mock, MockOnshapeClient)


# ── 4. 3D Surface Multi-Physics Scalars Tests ─────────────────────────────────


class TestMeshSurfaceScalars:
    """Verifies 3D mesh surface scalar extraction matching Interface Contract 2."""

    def test_mesh_scalar_contract_structure(self, client: TestClient) -> None:
        res = client.get("/api/revisions/1/mesh")
        assert res.status_code == 200
        data = res.json()

        # Interface Contract 2 required keys
        required_keys = [
            "rev_id",
            "vertices",
            "normals",
            "stress_field",
            "cp_field",
            "peak_von_mises_mpa",
            "yield_strength_mpa",
            "yield_fos",
            "triangle_count",
        ]
        for key in required_keys:
            assert key in data, f"Key '{key}' missing from mesh payload"

        assert data["rev_id"] == 1
        v_count = data["vertex_count"]
        assert len(data["vertices"]) == v_count * 3
        assert len(data["normals"]) == v_count * 3
        assert len(data["stress_field"]) == v_count
        assert len(data["cp_field"]) == v_count
        assert data["triangle_count"] == v_count // 3

    def test_mesh_scalar_bounds_and_physics(self, client: TestClient) -> None:
        res = client.get("/api/revisions/1/mesh")
        assert res.status_code == 200
        data = res.json()

        stress = data["stress_field"]
        cp = data["cp_field"]

        # Validate normalized bounds
        assert all(0.0 <= s <= 1.0 for s in stress), "Stress field outside [0.0, 1.0]"
        assert all(-1.0 <= c <= 1.0 for c in cp), "Cp field outside [-1.0, 1.0]"

        # Peak stress near airframe base should reach 1.0
        assert max(stress) == pytest.approx(1.0, abs=0.01)
        # Stagnation point at nose tip should reach 1.0
        assert max(cp) == pytest.approx(1.0, abs=0.01)

        # Telemetry consistency
        assert data["peak_von_mises_mpa"] > 0
        assert data["yield_strength_mpa"] > 0
        assert data["yield_fos"] > 0

    def test_mesh_missing_revision_404(self, client: TestClient) -> None:
        res = client.get("/api/revisions/9999/mesh")
        assert res.status_code == 404

    def test_compute_surface_scalars_empty_input(self) -> None:
        stress, cp, p_vm, y_str, y_fos = _compute_surface_scalars([], [], 1)
        assert stress == []
        assert cp == []
        assert p_vm > 0
        assert y_str > 0
        assert y_fos > 0


# ── 5. Design Bundle ZIP Export Endpoint & CLI Tests ──────────────────────────


class TestBundleExport:
    """Verifies bundle packaging and CLI export subcommand."""

    def test_bundle_export_zip_endpoint(self, client: TestClient) -> None:
        res = client.get("/api/revisions/1/bundle")
        assert res.status_code == 200
        assert "application/zip" in res.headers.get("content-type", "")

        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()

        assert "rev_001_report.json" in names
        assert any("rev_001.step" in n for n in names)
        assert any("rev_001.msh" in n for n in names)
        assert any("rev_001_surface.json" in n for n in names)

    def test_bundle_export_missing_revision_404(self, client: TestClient) -> None:
        res = client.get("/api/revisions/9999/bundle")
        assert res.status_code == 404

    def test_build_revision_bundle_zip_helper_direct(self) -> None:
        content = build_revision_bundle_zip(1)
        assert isinstance(content, bytes)
        assert len(content) > 1000
        zf = zipfile.ZipFile(io.BytesIO(content))
        assert "rev_001_report.json" in zf.namelist()

    def test_cli_export_command(self, tmp_path: pathlib.Path) -> None:
        from goddard.cli import _cmd_export, create_parser

        out_zip = tmp_path / "test_bundle.zip"
        parser = create_parser()
        args = parser.parse_args(["export", "--design-id", "rev_001", "-o", str(out_zip)])
        code = _cmd_export(args)
        assert code == 0
        assert out_zip.exists()
        assert out_zip.stat().st_size > 1000

        zf = zipfile.ZipFile(out_zip)
        assert "rev_001_report.json" in zf.namelist()

    def test_cli_export_integer_rev_id(self, tmp_path: pathlib.Path) -> None:
        from goddard.cli import _cmd_export, create_parser

        out_zip = tmp_path / "test_int_bundle.zip"
        parser = create_parser()
        args = parser.parse_args(["export", "-r", "1", "-o", str(out_zip)])
        code = _cmd_export(args)
        assert code == 0
        assert out_zip.exists()

    def test_cli_export_invalid_revision(self) -> None:
        from goddard.cli import _cmd_export, create_parser

        parser = create_parser()
        args = parser.parse_args(["export", "--design-id", "9999"])
        code = _cmd_export(args)
        assert code != 0

    def test_cli_export_malformed_revision_id(self) -> None:
        from goddard.cli import _cmd_export, create_parser

        parser = create_parser()
        args = parser.parse_args(["export", "--design-id", "not_a_number"])
        code = _cmd_export(args)
        assert code != 0
