"""
Unit and integration tests for Model Context Protocol (FastMCP) server tools.
Verifies all 4 agent-facing tools operate offline and produce structured responses.
"""

from __future__ import annotations

import pathlib

import pytest

from goddard.server.goddard_mcp import (
    check_mission_constraints,
    evaluate_rocket_design,
    get_design_ledger,
    validate_mission_requirements,
)


class TestMCPServerTools:
    """Test suite for FastMCP tools exposed to AI agents."""

    def test_validate_mission_requirements_incomplete(self) -> None:
        """Verify requirements validation detects missing variables and asks clarifying questions."""
        res = validate_mission_requirements(
            {
                "payload_mass_kg": 15.0,
            }
        )
        assert isinstance(res, dict)
        assert res["status"] == "NEEDS_CLARIFICATION"
        assert "missing_fields" in res
        assert "questions" in res
        assert len(res["missing_fields"]) > 0

    def test_validate_mission_requirements_ready(self) -> None:
        """Verify complete requirements pass gating and resolve default engineering values."""
        res = validate_mission_requirements(
            {
                "mission_profile": "sounding_suborbital",
                "payload_mass_kg": 4.0,
                "target_apogee_m": 4200.0,
                "propulsion_type": "liquid_biprop",
                "propellant": "LOX/CH4",
                "feed_architecture": "pressure_fed",
                "stabilization_mode": "passive_fins",
            }
        )
        assert isinstance(res, dict)
        assert res["status"] == "READY"
        assert "resolved_spec" in res
        spec = res["resolved_spec"]
        assert spec["payload_mass_kg"] == 4.0
        assert spec["target_apogee_m"] == 4200.0
        assert spec["body_radius_m"] > 0.0

    def test_get_design_ledger(
        self, tmp_designs_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify get_design_ledger returns list of design revisions from the ledger."""
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        ledger = get_design_ledger()
        assert isinstance(ledger, list)
        assert len(ledger) >= 2

        rev1 = ledger[0]
        assert "revision_id" in rev1
        assert rev1["revision_id"] == 1
        assert "inputs" in rev1
        assert "sizing_metrics" in rev1
        assert "fea_metrics" in rev1
        assert "flight_metrics" in rev1

    def test_check_mission_constraints_nominal(
        self, tmp_designs_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify check_mission_constraints evaluates revision against performance targets."""
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = check_mission_constraints(revision_id=1)
        assert isinstance(res, dict)
        assert res["revision_id"] == 1
        assert "passed" in res
        assert "violations" in res
        assert "deltas" in res
        assert isinstance(res["violations"], list)

    def test_check_mission_constraints_invalid_id(
        self, tmp_designs_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify check_mission_constraints raises ValueError for nonexistent revision IDs."""
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        with pytest.raises(ValueError, match="not found"):
            check_mission_constraints(revision_id=9999)

    def test_evaluate_rocket_design_fast_mode(
        self, tmp_designs_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Verify evaluate_rocket_design executes complete multi-physics evaluation
        offline in fast mode without external CAD servers.
        """
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = evaluate_rocket_design(
            mission_profile="sounding_suborbital",
            payload_mass_kg=4.0,
            target_apogee_m=4200.0,
            fidelity="fast",
            design_rationale="Automated test revision",
        )

        assert isinstance(res, dict)
        assert "revision_id" in res
        assert "sizing_metrics" in res
        assert "cad_metrics" in res
        assert "fea_metrics" in res
        assert "flight_metrics" in res

        # Sizing metrics checks
        sizing = res["sizing_metrics"]
        assert sizing["total_delta_v_ms"] > 300.0

        # FEA structural margin checks
        fea = res["fea_metrics"]
        assert fea["yield_fos"] > 1.5

        # Flight telemetry checks
        flight = res["flight_metrics"]
        assert flight["apogee_m"] > 0.0
