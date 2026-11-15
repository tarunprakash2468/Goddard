"""
Unit and integration tests for VTVL booster propulsive landing simulation.
Verifies the 4-phase descent profile, touchdown velocity limits, and propellant margins.
"""

from __future__ import annotations

from goddard.sim.vtvl_landing import PropulsiveLandingSim


class TestPropulsiveLandingSim:
    """Test suite for propulsive return and vertical touchdown simulation."""

    def test_nominal_four_phase_descent(self) -> None:
        """
        Verify complete 4-phase descent simulation:
        1. Boostback / Apogee Coast
        2. Supersonic Entry Burn
        3. Aerodynamic Grid-Fin Glide
        4. Terminal Landing Burn (Hoverslam)
        """
        res = PropulsiveLandingSim.simulate(
            stage1_dry_mass_kg=25000.0,
            landing_propellant_kg=29000.0,
            engine_isp_s=282.0,
            max_thrust_n=7607000.0,
            engine_count=9,
            separation_altitude_m=65000.0,
            separation_velocity_ms=1600.0,
            rocket_radius_m=1.85,
        )

        assert res["landing_success"] is True

        # Phase validation
        phases = [p["phase"] for p in res["trajectory_phases"]]
        assert "boostback" in phases
        assert "entry_burn" in phases
        assert "aerodynamic_glide" in phases
        assert "landing_burn" in phases

        # Durations and burn sanity
        assert res["entry_burn_duration_s"] > 0.0
        assert res["landing_burn_duration_s"] > 0.0
        assert res["peak_altitude_m"] >= 65000.0

    def test_touchdown_constraints(self) -> None:
        """
        Verify touchdown velocity v_td <= 2.5 m/s and landing mass > dry mass
        (positive propellant reserve margin).
        """
        res = PropulsiveLandingSim.simulate(
            stage1_dry_mass_kg=25000.0,
            landing_propellant_kg=29000.0,
            engine_isp_s=282.0,
            max_thrust_n=7607000.0,
            engine_count=9,
            separation_altitude_m=65000.0,
            separation_velocity_ms=1600.0,
            rocket_radius_m=1.85,
        )

        # Constraint 1: Landing velocity v <= 2.5 m/s
        assert res["touchdown_velocity_ms"] <= 2.5
        assert res["touchdown_velocity_passed"] is True

        # Constraint 2: Landing mass > dry mass (propellant margin positive)
        assert res["landing_mass_kg"] > res["dry_mass_kg"]
        assert res["propellant_remaining_kg"] > 0.0
        assert res["propellant_margin_positive"] is True

    def test_super_heavy_propulsive_landing(self) -> None:
        """Verify 33-engine Super Heavy class propulsive return and landing."""
        res = PropulsiveLandingSim.simulate(
            stage1_dry_mass_kg=250000.0,
            landing_propellant_kg=240000.0,
            engine_isp_s=327.0,
            max_thrust_n=72000000.0,
            engine_count=33,
            separation_altitude_m=70000.0,
            separation_velocity_ms=1550.0,
            rocket_radius_m=4.5,
        )

        assert res["landing_success"] is True
        assert res["touchdown_velocity_ms"] <= 2.5
        assert res["landing_mass_kg"] > res["dry_mass_kg"]
        assert res["propellant_remaining_kg"] > 0.0

    def test_insufficient_landing_fuel_edge_case(self) -> None:
        """Verify detection of fuel exhaustion during descent burn."""
        # Provide only 50 kg of fuel for a 25-ton booster
        res = PropulsiveLandingSim.simulate(
            stage1_dry_mass_kg=25000.0,
            landing_propellant_kg=50.0,
            engine_isp_s=282.0,
            max_thrust_n=7607000.0,
            engine_count=9,
            separation_altitude_m=65000.0,
            separation_velocity_ms=1600.0,
            rocket_radius_m=1.85,
        )

        # Must flag landing failure due to propellant exhaustion
        assert res["landing_success"] is False
        assert res["propellant_remaining_kg"] == 0.0
        assert res["propellant_margin_positive"] is False

    def test_zero_propellant_ballistic_impact(self) -> None:
        """Verify 0 kg propellant returns landing failure."""
        res = PropulsiveLandingSim.simulate(
            stage1_dry_mass_kg=25000.0,
            landing_propellant_kg=0.0,
            engine_isp_s=282.0,
            max_thrust_n=7607000.0,
            engine_count=9,
            separation_altitude_m=65000.0,
            separation_velocity_ms=1600.0,
            rocket_radius_m=1.85,
        )

        assert res["landing_success"] is False
        assert res["propellant_remaining_kg"] == 0.0
        assert res["propellant_margin_positive"] is False
