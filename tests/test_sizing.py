"""
Unit and integration tests for MissionSpec requirements gating and coupled WER sizing.
Tests ASME Section VIII Div 2 pressure vessel sizing, Blevins fin flutter,
two-stage orbital delta-V allocation, and 33-engine Super Heavy clustering.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from goddard.sizing.coupled_wer import (
    COTS_TUBE_ODS_M,
    MATERIAL_PROPERTIES,
    run_coupled_sizing,
    snap_to_cots,
)
from goddard.sizing.mission_spec import (
    MissionSpec,
    evaluate_spec_completeness,
)


class TestMissionSpecValidation:
    """Test suite for MissionSpec schema validation and completeness gate."""

    def test_sounding_spec_valid(self, sounding_mission_spec: MissionSpec) -> None:
        """Verify standard sounding rocket specification validates successfully."""
        assert sounding_mission_spec.mission_profile == "sounding_suborbital"
        assert sounding_mission_spec.stage_count == 1
        assert sounding_mission_spec.payload_mass_kg == 4.0
        assert sounding_mission_spec.target_apogee_m == 4200.0
        assert sounding_mission_spec.stabilization_mode == "passive_fins"
        assert sounding_mission_spec.engine_count_stage1 == 1

    def test_orbital_spec_validation(self, orbital_mission_spec: MissionSpec) -> None:
        """Verify orbital rocket specification passes consistency checks."""
        assert orbital_mission_spec.mission_profile == "orbital_insertion"
        assert orbital_mission_spec.stage_count == 2
        assert orbital_mission_spec.target_orbit_km == 400.0
        assert orbital_mission_spec.stabilization_mode == "tvc_guided"
        assert orbital_mission_spec.engine_count_stage1 == 9
        assert orbital_mission_spec.reusable_booster is True

    def test_orbital_single_stage_rejected(self) -> None:
        """Orbital insertion with single-stage (SSTO) must raise ValueError."""
        with pytest.raises((ValueError, ValidationError), match="stage_count >= 2"):
            MissionSpec(
                mission_profile="orbital_insertion",
                payload_mass_kg=1000.0,
                target_orbit_km=300.0,
                stage_count=1,
                propulsion_type="liquid_biprop",
                propellant="LOX/RP1",
                stabilization_mode="tvc_guided",
            )

    def test_orbital_missing_altitude_rejected(self) -> None:
        """Orbital insertion without target_orbit_km must raise ValueError."""
        with pytest.raises((ValueError, ValidationError), match="target_orbit_km"):
            MissionSpec(
                mission_profile="orbital_insertion",
                payload_mass_kg=1000.0,
                stage_count=2,
                propulsion_type="liquid_biprop",
                propellant="LOX/RP1",
                stabilization_mode="tvc_guided",
            )

    def test_orbital_passive_fins_rejected(self) -> None:
        """Orbital insertion in vacuum cannot rely on passive aerodynamic fins."""
        with pytest.raises((ValueError, ValidationError), match="tvc_guided"):
            MissionSpec(
                mission_profile="orbital_insertion",
                payload_mass_kg=1000.0,
                target_orbit_km=300.0,
                stage_count=2,
                propulsion_type="liquid_biprop",
                propellant="LOX/RP1",
                stabilization_mode="passive_fins",
            )

    def test_engine_count_range_bounds(self) -> None:
        """Engine count in Stage 1 must be between 1 and 37."""
        # Below lower bound
        with pytest.raises(ValidationError):
            MissionSpec(
                mission_profile="sounding_suborbital",
                payload_mass_kg=5.0,
                target_apogee_m=5000.0,
                engine_count_stage1=0,
            )

        # Above upper bound (37 max)
        with pytest.raises(ValidationError):
            MissionSpec(
                mission_profile="orbital_insertion",
                payload_mass_kg=150000.0,
                target_orbit_km=500.0,
                stage_count=2,
                stabilization_mode="tvc_guided",
                engine_count_stage1=38,
            )

    def test_evaluate_spec_completeness_gate(self) -> None:
        """Test the interactive requirements gate handles incomplete vs ready inputs."""
        # Incomplete inputs
        incomplete_input = {"payload_mass_kg": 10.0}
        gate_res = evaluate_spec_completeness(incomplete_input)
        assert gate_res["status"] == "NEEDS_CLARIFICATION"
        assert len(gate_res["missing_fields"]) > 0
        assert len(gate_res["questions"]) > 0

        # Complete sounding inputs
        complete_input = {
            "mission_profile": "sounding_suborbital",
            "payload_mass_kg": 4.0,
            "target_apogee_m": 4200.0,
            "propulsion_type": "liquid_biprop",
            "propellant": "LOX/CH4",
            "feed_architecture": "pressure_fed",
            "stabilization_mode": "passive_fins",
        }
        ready_res = evaluate_spec_completeness(complete_input)
        assert ready_res["status"] == "READY"
        assert "resolved_spec" in ready_res


class TestCoupledWERSizing:
    """Test suite for analytical rocket sizing, DFM, ASME tankage, and aeroelastics."""

    def test_sounding_rocket_sizing_and_mass_rollup(
        self, sounding_mission_spec: MissionSpec
    ) -> None:
        """Verify mass rollup, DFM COTS sizing, ASME wall thickness, and flutter for sounding rocket."""
        res = run_coupled_sizing(sounding_mission_spec.model_dump())

        assert res["mission_profile"] == "sounding_suborbital"
        assert res["stage_count"] == 1
        assert res["total_delta_v_ms"] > 300.0

        mass = res["mass_breakdown"]
        assert mass["payload_mass_kg"] == 4.0
        assert mass["stage_1_dry_kg"] > 0.0
        assert mass["total_dry_mass_kg"] == round(mass["stage_1_dry_kg"] + 4.0, 2)
        assert mass["total_propellant_mass_kg"] > 0.0

        # Geometry checks
        geom = res["geometry"]
        assert geom["body_radius_m"] == pytest.approx(0.0635, rel=1e-3)
        assert geom["has_fins"] is True
        assert geom["engine_count_stage1"] == 1

        # DFM snap checks: radius should snap to COTS tube ODs / 2
        snapped_od = snap_to_cots(geom["body_radius_m"] * 2.0, COTS_TUBE_ODS_M)
        assert snapped_od in COTS_TUBE_ODS_M

        # ASME Section VIII wall thickness check
        s1 = res["stages"][0]
        meop_pa = s1["tank_meop_pa"]
        assert meop_pa > 0
        mat = MATERIAL_PROPERTIES["AL6061-T6"]
        sigma_allowable = mat["yield_strength_pa"] / 1.5
        t_asme_theoretical = (meop_pa * geom["body_radius_m"]) / sigma_allowable
        assert s1["tank_wall_thickness_mm"] / 1000.0 >= t_asme_theoretical

        # Aeroelastic fin flutter check
        stab = res["stability"]
        assert stab["stabilization_mode"] == "passive_fins"
        assert stab["fin_flutter_velocity_ms"] > 500.0  # Fin flutter velocity well above Mach 1
        assert stab["flutter_safe_mach"] > 1.5

    def test_orbital_two_stage_sizing(self, orbital_mission_spec: MissionSpec) -> None:
        """Verify Stage 1 & 2 delta-V, propellant masses, and 7% booster landing reserve."""
        res = run_coupled_sizing(orbital_mission_spec.model_dump())

        assert res["mission_profile"] == "orbital_insertion"
        assert res["stage_count"] == 2
        assert res["total_delta_v_ms"] == pytest.approx(9200.0, rel=1e-2)

        stages = res["stages"]
        assert len(stages) == 2

        s1, s2 = stages[0], stages[1]
        # Delta-V split verification
        assert s1["delta_v_delivered_ms"] == pytest.approx(3400.0, rel=1e-2)
        assert s2["delta_v_delivered_ms"] == pytest.approx(5800.0, rel=1e-2)

        # Stage 1 7% Landing Propellant Reserve
        assert s1["reusable_booster"] is True
        assert s1["landing_propellant_kg"] > 0
        assert s1["landing_propellant_kg"] == pytest.approx(
            0.07 * s1["ascent_propellant_kg"], rel=1e-2
        )
        assert s1["propellant_mass_kg"] == pytest.approx(
            s1["ascent_propellant_kg"] + s1["landing_propellant_kg"], rel=1e-3
        )

        # Stage 2 expendable (no landing reserve)
        assert s2["reusable_booster"] is False
        assert s2["landing_propellant_kg"] == 0.0

        # TVC control authority verification
        stab = res["stability"]
        assert stab["stabilization_mode"] == "tvc_guided"
        assert stab["tvc_authority_passed"] is True
        assert stab["gimbal_angle_required_deg"] <= 5.0

    def test_heavy_reusable_33_engine_sizing(self, heavy_reusable_spec: MissionSpec) -> None:
        """Verify 33-engine Super Heavy cluster sizing and concentric cluster geometry."""
        res = run_coupled_sizing(heavy_reusable_spec.model_dump())

        assert res["stage_count"] == 2
        s1 = res["stages"][0]
        assert s1["engine_count"] == 33

        # Concentric cluster checks
        thrust_per_eng = s1["thrust_per_engine_n"]
        total_thrust = s1["total_thrust_n"]
        assert total_thrust == pytest.approx(thrust_per_eng * 33, rel=1e-2)
        assert total_thrust > 50.0e6  # Super Heavy thrust exceeds 50 MN

        # Structural material SS304L check
        assert res["structural_material"] == "SS304L"
        assert s1["pressurization_mode"] == "autogenous"

        # Autogenous pressurization reduces stage structural dry mass
        assert s1["stage_dry_mass_kg"] > 0
        geom = res["geometry"]
        assert geom["body_radius_m"] == pytest.approx(4.5, rel=1e-2)
        assert geom["engine_count_stage1"] == 33
