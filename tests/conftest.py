"""
Pytest configuration and shared offline fixtures for Goddard test suite.
Ensures zero external network dependencies and air-gapped repeatability.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

# Ensure project root is in sys.path so 'goddard' package is directly importable
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Force offline mode for all tests
os.environ["GODDARD_OFFLINE_MODE"] = "true"

from goddard.client.mock import MockOnshapeClient  # noqa: E402
from goddard.sizing.mission_spec import MissionSpec  # noqa: E402


@pytest.fixture
def mock_onshape_client() -> MockOnshapeClient:
    """Fixture providing an offline MockOnshapeClient instance."""
    return MockOnshapeClient(
        access_key="mock_access_key",
        secret_key="mock_secret_key",
        base_url="https://mock.onshape.test",
    )


@pytest.fixture
def sounding_mission_spec() -> MissionSpec:
    """Standard Class I single-stage civil sounding rocket MissionSpec."""
    return MissionSpec(
        mission_profile="sounding_suborbital",
        payload_mass_kg=4.0,
        target_apogee_m=4200.0,
        stage_count=1,
        propulsion_type="liquid_biprop",
        propellant="LOX/CH4",
        feed_architecture="pressure_fed",
        stabilization_mode="passive_fins",
        dfm_mode="cots_stock",
        body_radius_m=0.0635,
        body_length_m=1.75,
        structural_material="AL6061-T6",
        engine_count_stage1=1,
    )


@pytest.fixture
def orbital_mission_spec() -> MissionSpec:
    """Class II two-stage Falcon 9 class orbital MissionSpec with reusable booster."""
    return MissionSpec(
        mission_profile="orbital_insertion",
        payload_mass_kg=15000.0,
        target_orbit_km=400.0,
        target_inclination_deg=28.5,
        stage_count=2,
        propulsion_type="liquid_biprop",
        propellant="LOX/RP1",
        feed_architecture="pump_fed",
        stabilization_mode="tvc_guided",
        launch_mode="vertical_pad",
        engine_count_stage1=9,
        reusable_booster=True,
        structural_material="Al-Li-2195",
        dfm_mode="custom_machined",
        body_radius_m=1.85,
        body_length_m=42.0,
        stage2_radius_m=1.85,
        stage2_length_m=12.0,
        interstage_length_m=3.0,
        nose_length_m=6.5,
    )


@pytest.fixture
def heavy_reusable_spec() -> MissionSpec:
    """Class III Super Heavy / Starship class MissionSpec with 33 engines."""
    return MissionSpec(
        mission_profile="orbital_insertion",
        payload_mass_kg=100000.0,
        target_orbit_km=500.0,
        target_inclination_deg=28.5,
        stage_count=2,
        propulsion_type="liquid_biprop",
        propellant="LOX/CH4",
        feed_architecture="pump_fed",
        stabilization_mode="tvc_guided",
        launch_mode="vertical_pad",
        engine_count_stage1=33,
        reusable_booster=True,
        structural_material="SS304L",
        dfm_mode="custom_machined",
        body_radius_m=4.5,
        body_length_m=70.0,
        stage2_radius_m=4.5,
        stage2_length_m=50.0,
        interstage_length_m=4.0,
        nose_length_m=9.0,
        pressurization_mode="autogenous",
    )


@pytest.fixture
def tmp_designs_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Fixture providing a temporary directory with a seed design_ledger.json."""
    designs_dir = tmp_path / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)

    seed_ledger = [
        {
            "revision_id": 1,
            "timestamp": "2026-11-15T19:00:00.000000+00:00",
            "fidelity": "fast",
            "rationale": "Seed baseline sounding rocket for unit testing.",
            "inputs": {
                "mission_profile": "sounding_suborbital",
                "stage_count": 1,
                "stabilization_mode": "passive_fins",
                "launch_mode": "rail",
                "feed_architecture": "pressure_fed",
                "propulsion_type": "liquid_biprop",
                "propellant": "LOX/CH4",
                "structural_material": "AL6061-T6",
                "dfm_mode": "cots_stock",
                "engine_count_stage1": 1,
                "reusable_booster": False,
                "payload_mass_kg": 4.0,
                "target_apogee_m": 4200.0,
                "body_radius_m": 0.0635,
                "body_length_m": 1.75,
                "has_fins": True,
                "fin_count": 4,
            },
            "sizing_metrics": {
                "mission_profile": "sounding_suborbital",
                "total_delta_v_ms": 387.6,
                "total_wet_mass_kg": 6.63,
                "total_dry_mass_kg": 8.63,
                "total_propellant_mass_kg": 2.0,
                "wall_thickness_mm": 1.65,
            },
            "cad_metrics": {
                "mass_kg": 4.63,
                "volume_m3": 0.001715,
                "center_of_mass_m": [0.0, 0.0, 0.875],
            },
            "fea_metrics": {
                "peak_von_mises_mpa": 13.8,
                "yield_fos": 20.0,
                "buckling_load_factor_blf": 35.0,
                "stress_passed": True,
                "buckling_passed": True,
            },
            "flight_metrics": {
                "apogee_m": 4210.5,
                "max_mach": 1.15,
                "max_q_pa": 48200.0,
                "flight_time_s": 58.2,
                "rail_exit_velocity_ms": 28.5,
                "static_margin_calibers": {
                    "rail_departure": 2.45,
                    "burnout": 3.12,
                },
            },
        },
        {
            "revision_id": 2,
            "timestamp": "2026-11-15T19:05:00.000000+00:00",
            "fidelity": "fast",
            "rationale": "Seed baseline Falcon 9 class reusable orbital launcher.",
            "inputs": {
                "mission_profile": "orbital_insertion",
                "stage_count": 2,
                "stabilization_mode": "tvc_guided",
                "launch_mode": "vertical_pad",
                "feed_architecture": "pump_fed",
                "propulsion_type": "liquid_biprop",
                "propellant": "LOX/RP1",
                "structural_material": "Al-Li-2195",
                "dfm_mode": "custom_machined",
                "engine_count_stage1": 9,
                "reusable_booster": True,
                "payload_mass_kg": 15000.0,
                "target_orbit_km": 400.0,
                "body_radius_m": 1.85,
                "body_length_m": 42.0,
                "stage2_radius_m": 1.85,
                "stage2_length_m": 12.0,
                "interstage_length_m": 3.0,
                "nose_length_m": 6.5,
                "has_fins": False,
                "fin_count": 0,
            },
            "sizing_metrics": {
                "mission_profile": "orbital_insertion",
                "total_delta_v_ms": 9200.0,
                "total_wet_mass_kg": 542625.0,
                "total_dry_mass_kg": 43300.0,
                "total_propellant_mass_kg": 667078.0,
            },
            "cad_metrics": {
                "mass_kg": 24677.0,
                "volume_m3": 450.0,
                "center_of_mass_m": [0.0, 0.0, 21.0],
            },
            "fea_metrics": {
                "peak_von_mises_mpa": 185.0,
                "yield_fos": 2.97,
                "buckling_load_factor_blf": 3.42,
                "stress_passed": True,
                "buckling_passed": True,
            },
            "flight_metrics": {
                "apogee_m": 400000.0,
                "max_mach": 7.5,
                "max_q_pa": 38000.0,
                "flight_time_s": 520.0,
                "tvc_metrics": {
                    "gimbal_angle_required_deg": 0.16,
                    "max_allowable_gimbal_deg": 5.0,
                    "tvc_authority_passed": True,
                },
            },
            "vtvl_landing": {
                "landing_success": True,
                "touchdown_velocity_ms": 1.8,
                "propellant_remaining_kg": 6370.0,
            },
        },
    ]

    ledger_file = designs_dir / "design_ledger.json"
    ledger_file.write_text(json.dumps(seed_ledger, indent=2))
    return designs_dir
