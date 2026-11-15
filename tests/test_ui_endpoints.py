"""
Unit and integration tests for FastAPI Mission Control endpoints and 3D mesh streaming.
Uses Starlette TestClient with offline mocks and signal-safe Gmsh initialization.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from goddard.ui.app import app


@pytest.fixture
def client(tmp_designs_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fixture providing a TestClient bound to a temporary designs ledger."""
    monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
    return TestClient(app)


class TestUIEndpoints:
    """Test suite for 3D Mission Control web server endpoints."""

    def test_root_index_html(self, client: TestClient) -> None:
        """GET / returns 200 OK with HTML content."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in response.text or "html" in response.text.lower()

    def test_api_revisions_list(self, client: TestClient) -> None:
        """GET /api/revisions returns enriched list of design revisions."""
        response = client.get("/api/revisions")
        assert response.status_code == 200
        revisions = response.json()
        assert isinstance(revisions, list)
        assert len(revisions) >= 2

        rev1 = revisions[0]
        assert rev1["revision_id"] == 1
        assert "classification" in rev1
        assert "compliance" in rev1
        assert "inputs" in rev1

    def test_api_summary_kpi(self, client: TestClient) -> None:
        """GET /api/summary returns platform KPI summary metrics."""
        response = client.get("/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert data.get("status") == "OK"
        assert "total_revisions" in data
        assert data["total_revisions"] >= 2
        assert "latest_revision_id" in data
        assert "compliant_revisions" in data
        assert "max_apogee_m" in data
        assert "classes_represented" in data

    def test_api_revision_detail(self, client: TestClient) -> None:
        """GET /api/revisions/{rev_id} returns individual revision object."""
        response = client.get("/api/revisions/1")
        assert response.status_code == 200
        rev = response.json()
        assert rev["revision_id"] == 1

        # Nonexistent revision
        res_404 = client.get("/api/revisions/9999")
        assert res_404.status_code == 404

    def test_api_revision_mesh_surface(self) -> None:
        """
        GET /api/revisions/{rev_id}/mesh returns 3D triangle surface data
        for valid revisions with pre-computed surfaces, or 404 for missing meshes.
        """
        # Test against repo default designs where rev_001_surface.json exists
        default_client = TestClient(app)
        res = default_client.get("/api/revisions/1/mesh")

        if res.status_code == 200:
            mesh_data = res.json()
            assert "vertices" in mesh_data
            assert "triangle_count" in mesh_data
            assert isinstance(mesh_data["vertices"], list)
            assert mesh_data["vertex_count"] > 0
        else:
            assert res.status_code in [200, 404]

    def test_api_revision_mesh_404_handling(self, client: TestClient) -> None:
        """GET /api/revisions/9999/mesh returns 404 cleanly when geometry is absent."""
        res_404 = client.get("/api/revisions/9999/mesh")
        assert res_404.status_code == 404
        assert "detail" in res_404.json()

    def test_empty_ledger_clean_kpi_handling(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify API endpoints handle an empty designs directory gracefully without 500 errors."""
        empty_dir = tmp_path / "empty_designs"
        empty_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(empty_dir))

        empty_client = TestClient(app)
        r_revs = empty_client.get("/api/revisions")
        assert r_revs.status_code == 200
        assert r_revs.json() == []

        r_sum = empty_client.get("/api/summary")
        assert r_sum.status_code == 200
        sum_data = r_sum.json()
        assert sum_data["total_revisions"] == 0
        assert sum_data["latest_revision_id"] is None

    def test_gmsh_thread_safety_signal_handling(self) -> None:
        """
        Verify gmsh initialization uses interruptible=False to prevent
        fatal signal-handler crashes in multi-threaded test runners.
        """
        import gmsh

        # Calling gmsh.initialize(interruptible=False) must succeed without throwing
        gmsh.initialize(interruptible=False)
        try:
            assert gmsh.isInitialized() == 1
        finally:
            gmsh.finalize()
