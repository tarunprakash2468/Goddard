"""
Mission Specification Schema & Universal Interactive Requirements Gate.

Categorizes design requirements across civil sounding rockets, suborbital scientific
platforms, and commercial orbital launch vehicles:
  - Mission Profiles: sounding_suborbital, orbital_insertion, vtvl_hopper
  - Feed Architectures: pressure_fed, pump_fed, solid_grain, hybrid
  - Stabilization Modes: passive_fins, tvc_guided, grid_fins, spin_stabilized
  - Structural Materials: AL6061-T6, Al-Li-2195, SS304L, Carbon-Epoxy
  - DFM Modes: cots_stock, custom_machined, additive

Provides evaluate_spec_completeness() to gate multi-stage CAD, sizing, FEA, and trajectory
simulations, generating domain-specific clarifying questions when specs are underspecified
or physically inconsistent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

VALID_MISSION_PROFILES = {"sounding_suborbital", "orbital_insertion", "vtvl_hopper"}
VALID_STABILIZATION_MODES = {"passive_fins", "tvc_guided", "grid_fins", "spin_stabilized"}
VALID_LAUNCH_MODES = {"rail", "vertical_pad"}
VALID_FEED_ARCHITECTURES = {"pressure_fed", "pump_fed", "solid_grain", "hybrid"}
VALID_MATERIALS = {"AL6061-T6", "Al-Li-2195", "SS304L", "Carbon-Epoxy"}
VALID_DFM_MODES = {"cots_stock", "custom_machined", "additive"}

VALID_PROPULSION_TYPES = {"liquid_biprop", "solid", "hybrid"}
VALID_PROPELLANTS = {
    "liquid_biprop": ["LOX/CH4", "LOX/RP1", "LOX/LH2", "N2O4/MMH", "LOX/Ethanol"],
    "solid": ["solid_composite", "APCP", "KNDX"],
    "hybrid": ["N2O/HTPB", "N2O/Paraffin", "LOX/Paraffin"],
}


class MissionSpec(BaseModel):
    """Strongly typed universal mission requirements schema."""

    # Mission Architecture Anchors
    mission_profile: Literal["sounding_suborbital", "orbital_insertion", "vtvl_hopper"] = Field(
        "sounding_suborbital",
        description="Mission class: 'sounding_suborbital', 'orbital_insertion', or 'vtvl_hopper'.",
    )
    target_apogee_m: float | None = Field(
        None,
        description="Target apogee altitude AGL in meters (for suborbital or hopper missions).",
    )
    target_orbit_km: float | None = Field(
        None,
        description="Target circular/insertion orbit altitude in km (for orbital missions, e.g. 300, 500).",
    )
    target_inclination_deg: float | None = Field(
        28.5,
        description="Target orbital inclination in degrees (default: 28.5 deg Cape Canaveral).",
    )

    payload_mass_kg: float = Field(
        ..., ge=0.0, description="Mass of payload, science instruments, or satellite bus in kg."
    )

    stage_count: int = Field(1, ge=1, le=3, description="Number of propulsion stages (1 to 3).")

    propulsion_type: Literal["liquid_biprop", "solid", "hybrid"] = Field(
        "liquid_biprop",
        description="Propulsion architecture: 'liquid_biprop', 'solid', or 'hybrid'.",
    )
    propellant: str = Field(
        "LOX/CH4",
        description="Propellant selection (e.g. 'LOX/CH4', 'LOX/RP1', 'LOX/LH2', 'solid_composite', 'N2O/HTPB').",
    )

    feed_architecture: Literal["pressure_fed", "pump_fed", "solid_grain", "hybrid"] = Field(
        "pressure_fed",
        description="Propellant delivery: 'pressure_fed', 'pump_fed' (turbopump), 'solid_grain', or 'hybrid'.",
    )

    stabilization_mode: Literal["passive_fins", "tvc_guided", "grid_fins", "spin_stabilized"] = (
        Field(
            "passive_fins",
            description="Attitude stabilization: 'passive_fins', 'tvc_guided', 'grid_fins', or 'spin_stabilized'.",
        )
    )

    launch_mode: Literal["rail", "vertical_pad"] = Field(
        "rail",
        description="Launch mode: 'rail' (guided tower/rail) or 'vertical_pad' (hold-down clamps).",
    )

    engine_count_stage1: int = Field(
        1,
        ge=1,
        le=37,
        description="Number of rocket engines in Stage 1 cluster (e.g. 1, 3, 7, 9 Octaweb, 33 Super Heavy).",
    )

    reusable_booster: bool = Field(
        False, description="Reserve propellant margin for boostback/entry/landing burns when True."
    )

    pressurization_mode: Literal["helium", "autogenous"] = Field(
        "helium",
        description="Propellant tank pressurization mode: 'helium' (COPV) or 'autogenous' (gaseous propellant tap-off).",
    )

    structural_material: Literal["AL6061-T6", "Al-Li-2195", "SS304L", "Carbon-Epoxy"] = Field(
        "AL6061-T6", description="Primary airframe structural material."
    )

    dfm_mode: Literal["cots_stock", "custom_machined", "additive"] = Field(
        "cots_stock",
        description="Design-for-Manufacturability mode: snap to COTS sizes, custom CNC, or additive.",
    )

    # Optional Geometric & System Overrides
    body_radius_m: float | None = Field(None, description="Airframe outer radius in meters.")
    body_length_m: float | None = Field(None, description="Stage 1 airframe length in meters.")
    stage2_radius_m: float | None = Field(None, description="Stage 2 airframe radius in meters.")
    stage2_length_m: float | None = Field(None, description="Stage 2 airframe length in meters.")
    interstage_length_m: float | None = Field(
        None, description="Interstage adapter length in meters."
    )
    nose_length_m: float | None = Field(
        None, description="Nosecone or payload fairing length in meters."
    )
    tank_pressure_psi: float | None = Field(
        None, description="Regulated propellant tank pressure in psi."
    )
    chamber_pressure_psi: float | None = Field(
        None, description="Combustion chamber pressure in psi."
    )
    fin_count: int | None = Field(None, description="Number of fins (if passive_fins).")
    rail_length_m: float | None = Field(None, description="Launch rail length in meters.")
    launch_site_elevation_m: float | None = Field(
        None, description="Launch site elevation in meters."
    )

    # Stability & Safety Bounds
    target_stability_margin_min_cal: float = Field(
        2.0, description="Minimum static margin in calibers (passive fins)."
    )
    target_stability_margin_max_cal: float = Field(
        3.0, description="Maximum static margin in calibers (passive fins)."
    )
    max_tvc_gimbal_angle_deg: float = Field(
        5.0, description="Maximum TVC engine gimbal angle in degrees."
    )
    max_dynamic_pressure_pa: float = Field(
        65000.0, description="Maximum structural dynamic pressure limit in Pa."
    )

    @model_validator(mode="after")
    def validate_architecture_consistency(self) -> MissionSpec:
        # 1. Mission Profile Target Altitude
        if self.mission_profile == "orbital_insertion":
            if self.target_orbit_km is None or self.target_orbit_km <= 0:
                raise ValueError(
                    "Orbital insertion mission requires positive 'target_orbit_km' (e.g. 300, 500)."
                )
            if self.stage_count < 2:
                raise ValueError(
                    f"Orbital insertion requires 'stage_count >= 2' (single-stage-to-orbit with {self.propellant} is physically unviable)."
                )
            if self.stabilization_mode == "passive_fins":
                raise ValueError(
                    "Orbital launch vehicles operate in exo-atmospheric vacuum and require 'tvc_guided' stabilization."
                )
        else:
            if self.target_apogee_m is None and self.target_orbit_km is None:
                raise ValueError(
                    f"Mission profile '{self.mission_profile}' requires 'target_apogee_m'."
                )

        # 2. Feed Architecture Consistency
        if self.propulsion_type == "solid":
            self.feed_architecture = "solid_grain"
        elif self.propulsion_type == "hybrid":
            self.feed_architecture = "hybrid"

        # 3. Propellant Compatibility
        valid_options = VALID_PROPELLANTS.get(self.propulsion_type, [])
        if valid_options and self.propellant not in valid_options:
            matched = False
            for opt in valid_options:
                if self.propellant.strip().upper() == opt.upper():
                    self.propellant = opt
                    matched = True
                    break
            if not matched:
                raise ValueError(
                    f"Propellant '{self.propellant}' incompatible with propulsion_type '{self.propulsion_type}'. Options: {valid_options}"
                )

        # 4. Launch Mode and Stabilization Compatibility
        if self.stabilization_mode == "tvc_guided" and self.launch_mode == "rail":
            self.launch_mode = "vertical_pad"

        return self


def evaluate_spec_completeness(user_inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluates whether incoming customer requirements have sufficient definition to trigger
    multi-stage coupled sizing, parametric CAD modeling, FEA, CFD, and flight trajectory simulations.

    Returns:
      dict with status 'READY' or 'NEEDS_CLARIFICATION'
    """
    inputs = dict(user_inputs)
    missing_fields: list[str] = []
    questions: list[str] = []

    # Normalize aliases
    if inputs.get("propulsion_type") == "liquid":
        inputs["propulsion_type"] = "liquid_biprop"

    profile = inputs.get("mission_profile")
    if not profile:
        # Deduce profile if target_orbit_km or target_apogee_m present
        if inputs.get("target_orbit_km") is not None:
            profile = "orbital_insertion"
            inputs["mission_profile"] = "orbital_insertion"
        elif inputs.get("target_apogee_m") is not None:
            profile = "sounding_suborbital"
            inputs["mission_profile"] = "sounding_suborbital"
        else:
            missing_fields.append("mission_profile")
            questions.append(
                "What is your target mission profile: 'sounding_suborbital' (apogee altitude), 'orbital_insertion' (LEO/SSO), or 'vtvl_hopper'?"
            )

    # 1. Target Altitude / Orbit
    if profile == "orbital_insertion":
        orbit_km = inputs.get("target_orbit_km")
        if orbit_km is None or float(orbit_km) <= 0:
            missing_fields.append("target_orbit_km")
            questions.append(
                "What target circular orbit altitude in km (e.g. 300 km LEO, 500 km SSO)?"
            )

        # Multi-stage check for orbital
        stages = inputs.get("stage_count")
        if stages is not None and int(stages) == 1:
            missing_fields.append("stage_count")
            questions.append(
                "Single-stage-to-orbit (SSTO) is physically unviable with chemical propellants. Would you like to size a 2-stage or 3-stage orbital launch vehicle?"
            )
        elif stages is None:
            # Recommend 2 stages
            inputs["stage_count"] = 2

        # Stabilization for orbital
        stab = inputs.get("stabilization_mode")
        if stab == "passive_fins":
            missing_fields.append("stabilization_mode")
            questions.append(
                "Orbital launch vehicles fly through vacuum and cannot rely on passive aerodynamic fins. Should we configure active TVC guidance ('tvc_guided')?"
            )
        elif stab is None:
            inputs["stabilization_mode"] = "tvc_guided"
            inputs["launch_mode"] = "vertical_pad"
    else:
        apogee = inputs.get("target_apogee_m")
        if apogee is None or float(apogee) <= 0:
            missing_fields.append("target_apogee_m")
            questions.append(
                "What is your target apogee in meters AGL (e.g. 4,200 m or 120,000 m Karman line)?"
            )

    # 2. Payload Mass
    payload = inputs.get("payload_mass_kg")
    if payload is None or float(payload) < 0:
        missing_fields.append("payload_mass_kg")
        questions.append(
            "What payload mass (in kg) must the vehicle lift (e.g. 4.0 kg CubeSat or 50.0 kg microsatellite)?"
        )

    # 3. Propulsion Architecture & Propellant
    ptype = inputs.get("propulsion_type")
    if not ptype:
        missing_fields.append("propulsion_type")
        questions.append(
            "Which propulsion architecture: 'liquid_biprop' (e.g. LOX/RP1, LOX/CH4), 'solid', or 'hybrid'?"
        )

    prop = inputs.get("propellant")
    if not prop:
        missing_fields.append("propellant")
        if ptype == "liquid_biprop":
            questions.append(
                "Which propellant selection: 'LOX/RP1' (high bulk density), 'LOX/CH4' (clean burning / reusable), or 'LOX/LH2'?"
            )
        elif ptype == "hybrid":
            questions.append("Which hybrid propellant: 'N2O/HTPB' or 'N2O/Paraffin'?")
        else:
            questions.append(
                "Which propellant selection: 'LOX/CH4', 'LOX/RP1', 'solid_composite', or 'N2O/HTPB'?"
            )

    # 4. Feed Architecture for Liquid Launch Vehicles
    if ptype == "liquid_biprop" and "feed_architecture" not in inputs:
        if profile == "orbital_insertion" or (
            inputs.get("target_apogee_m") and float(inputs.get("target_apogee_m", 0)) > 50000
        ):
            # Prompt or default to pump_fed for heavy/orbital vehicles
            inputs["feed_architecture"] = "pump_fed"
        else:
            inputs["feed_architecture"] = "pressure_fed"

    if missing_fields:
        return {
            "status": "NEEDS_CLARIFICATION",
            "missing_fields": missing_fields,
            "questions": questions,
            "partial_inputs": inputs,
        }

    # Validate against Pydantic schema
    try:
        spec = MissionSpec(**inputs)
    except Exception as exc:
        return {
            "status": "NEEDS_CLARIFICATION",
            "missing_fields": ["validation_error"],
            "questions": [str(exc)],
            "partial_inputs": inputs,
        }

    # Resolve intelligent engineering defaults for free Tier 2 parameters
    resolved = spec.model_dump()

    tier2_keys = [
        "body_radius_m",
        "body_length_m",
        "stage2_radius_m",
        "stage2_length_m",
        "interstage_length_m",
        "nose_length_m",
        "tank_pressure_psi",
        "chamber_pressure_psi",
        "fin_count",
        "rail_length_m",
        "launch_site_elevation_m",
    ]
    free_vars = [k for k in tier2_keys if inputs.get(k) is None]
    locked_vars = [k for k in inputs.keys() if k not in free_vars]

    # Defaults based on mission profile and stage count
    if resolved["tank_pressure_psi"] is None:
        resolved["tank_pressure_psi"] = (
            50.0 if resolved["feed_architecture"] == "pump_fed" else 450.0
        )
    if resolved["chamber_pressure_psi"] is None:
        resolved["chamber_pressure_psi"] = (
            750.0 if resolved["feed_architecture"] == "pump_fed" else 300.0
        )

    if resolved["body_radius_m"] is None:
        if resolved["mission_profile"] == "orbital_insertion":
            resolved["body_radius_m"] = 0.60  # 1.2 m diameter micro-launcher
        elif (resolved.get("target_apogee_m") or 0) > 80000:
            resolved["body_radius_m"] = 0.10  # 0.20 m diameter suborbital booster (L/D ~ 15)
        else:
            resolved["body_radius_m"] = 0.0635  # standard 5 in sounding rocket

    if resolved["nose_length_m"] is None:
        resolved["nose_length_m"] = resolved["body_radius_m"] * 4.0

    if resolved["stage_count"] > 1:
        if resolved["stage2_radius_m"] is None:
            resolved["stage2_radius_m"] = resolved["body_radius_m"]
        if resolved["interstage_length_m"] is None:
            resolved["interstage_length_m"] = resolved["body_radius_m"] * 1.5

    if resolved["stabilization_mode"] == "tvc_guided":
        resolved["fin_count"] = 0
        resolved["launch_mode"] = "vertical_pad"
    elif resolved["fin_count"] is None:
        resolved["fin_count"] = 4

    if resolved["rail_length_m"] is None:
        resolved["rail_length_m"] = 5.2 if resolved["launch_mode"] == "rail" else 0.0
    if resolved["launch_site_elevation_m"] is None:
        resolved["launch_site_elevation_m"] = 1400.0 if resolved["launch_mode"] == "rail" else 10.0

    return {
        "status": "READY",
        "resolved_spec": resolved,
        "free_variables": free_vars,
        "locked_variables": locked_vars,
    }
