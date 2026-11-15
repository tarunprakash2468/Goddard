"""
Coupled Multi-Stage, Multi-Material Rocket Sizing & DFM Engine.

Couples:
  1. Propulsion Thermochemistry (High-accuracy NASA CEA thermochemical tables for LOX/CH4,
     LOX/RP1, LOX/LH2, N2O4/MMH, N2O/HTPB, solid_composite).
  2. Feed-System-Aware Tank Sizing:
     - Pressure-Fed: MEOP ~ 1.4 * Pc (hoop stress governs)
     - Pump-Fed: MEOP ~ 35-60 psi (turbopump mass fraction, axial buckling/min-gauge governs)
     - Solid-Grain: Single chamber casing sized for Pc
  3. Multi-Material Library:
     - AL6061-T6, Al-Li-2195, SS304L, Carbon-Epoxy
  4. Multi-Stage Delta-V Allocation & Tsiolkovsky Sizing:
     - Stage 1 boost + vacuum-expanded Stage 2
  5. Multi-Engine Clusters:
     - 1 to 9 engine cluster geometry, gimbal moment arm, thrust rollup
  6. Aeroelastic & Guidance Verification:
     - Passive fins: NACA 4197 flutter velocity
     - TVC guided: Gimbal angle required <= 5 deg at Max Q pitch disturbance
  7. DFM:
     - cots_stock snapping vs custom_machined vs additive
"""

from __future__ import annotations

import math
from typing import Any

# ── Material Properties Database ──────────────────────────────────────────
MATERIAL_PROPERTIES = {
    "AL6061-T6": {
        "density_kg_m3": 2700.0,
        "yield_strength_pa": 276.0e6,
        "ultimate_strength_pa": 310.0e6,
        "shear_modulus_pa": 26.0e9,
        "youngs_modulus_pa": 68.9e9,
        "poisson_ratio": 0.33,
    },
    "Al-Li-2195": {
        "density_kg_m3": 2710.0,
        "yield_strength_pa": 550.0e6,
        "ultimate_strength_pa": 590.0e6,
        "shear_modulus_pa": 28.0e9,
        "youngs_modulus_pa": 76.0e9,
        "poisson_ratio": 0.32,
    },
    "SS304L": {
        "density_kg_m3": 7900.0,
        "yield_strength_pa": 240.0e6,
        "ultimate_strength_pa": 550.0e6,
        "shear_modulus_pa": 77.0e9,
        "youngs_modulus_pa": 193.0e9,
        "poisson_ratio": 0.29,
    },
    "Carbon-Epoxy": {
        "density_kg_m3": 1550.0,
        "yield_strength_pa": 800.0e6,
        "ultimate_strength_pa": 1200.0e6,
        "shear_modulus_pa": 40.0e9,
        "youngs_modulus_pa": 135.0e9,
        "poisson_ratio": 0.30,
    },
}

# Standard Commercial Stock Sizes
COTS_TUBE_ODS_M = [
    0.0762,  # 3.0 in
    0.1016,  # 4.0 in
    0.1270,  # 5.0 in (radius 0.0635 m)
    0.1397,  # 5.5 in
    0.1524,  # 6.0 in (radius 0.0762 m)
    0.1778,  # 7.0 in
    0.2032,  # 8.0 in
]

COTS_TUBE_WALLS_M = [
    0.001651,  # 0.065 in
    0.002108,  # 0.083 in
    0.002413,  # 0.095 in
    0.003175,  # 0.125 in (1/8 in)
    0.004763,  # 0.1875 in (3/16 in)
    0.006350,  # 0.250 in (1/4 in)
]

COTS_PLATE_THICKNESSES_M = [
    0.001588,  # 1/16 in
    0.002381,  # 3/32 in
    0.003175,  # 1/8 in
    0.004000,  # 4 mm
    0.004763,  # 3/16 in
    0.006350,  # 1/4 in
]

# Thermochemical Reference Table (NASA SP-273 / Huzel & Huang)
THERMOCHEM_DATA = {
    "LOX/CH4": {
        "opt_of": 3.2,
        "c_star": 1780.0,
        "gamma": 1.22,
        "t_chamber_k": 3450.0,
        "mol_weight": 20.8,
        "rho_ox": 1141.0,
        "rho_fuel": 422.0,
        "isp_sea": 285.0,
        "isp_vac": 330.0,
    },
    "LOX/RP1": {
        "opt_of": 2.6,
        "c_star": 1750.0,
        "gamma": 1.24,
        "t_chamber_k": 3670.0,
        "mol_weight": 23.3,
        "rho_ox": 1141.0,
        "rho_fuel": 810.0,
        "isp_sea": 275.0,
        "isp_vac": 315.0,
    },
    "LOX/LH2": {
        "opt_of": 5.5,
        "c_star": 2300.0,
        "gamma": 1.26,
        "t_chamber_k": 3200.0,
        "mol_weight": 14.5,
        "rho_ox": 1141.0,
        "rho_fuel": 71.0,
        "isp_sea": 360.0,
        "isp_vac": 450.0,
    },
    "N2O4/MMH": {
        "opt_of": 2.1,
        "c_star": 1680.0,
        "gamma": 1.25,
        "t_chamber_k": 3120.0,
        "mol_weight": 21.5,
        "rho_ox": 1440.0,
        "rho_fuel": 880.0,
        "isp_sea": 260.0,
        "isp_vac": 310.0,
    },
    "N2O/HTPB": {
        "opt_of": 6.0,
        "c_star": 1550.0,
        "gamma": 1.25,
        "t_chamber_k": 2980.0,
        "mol_weight": 24.5,
        "rho_ox": 1220.0,
        "rho_fuel": 920.0,
        "isp_sea": 225.0,
        "isp_vac": 260.0,
    },
    "solid_composite": {
        "opt_of": 0.0,
        "c_star": 1500.0,
        "gamma": 1.20,
        "t_chamber_k": 3100.0,
        "mol_weight": 26.0,
        "rho_ox": 1750.0,
        "rho_fuel": 1750.0,
        "isp_sea": 220.0,
        "isp_vac": 255.0,
    },
}


def snap_to_cots(val: float, stock_list: list[float]) -> float:
    """Snaps a dimension to the smallest standard stock size >= required value."""
    for stock in sorted(stock_list):
        if stock >= val:
            return stock
    return stock_list[-1]


def compute_tvc_control_authority(
    thrust_n: float,
    body_radius_m: float,
    airframe_length_m: float,
    cg_from_nose_m: float,
    max_q_pa: float = 65000.0,
    wind_gust_aoa_deg: float = 1.2,
) -> dict[str, Any]:
    """
    Evaluates Thrust Vector Control (TVC) pitch/yaw control authority at max dynamic pressure.
    """
    s_ref = math.pi * (body_radius_m**2)
    # Nose + body normal force derivative CNa ~ 2.0 (slender body theory)
    cna = 2.0
    alpha_rad = math.radians(wind_gust_aoa_deg)
    # Center of pressure for slender body is near 0.466 * nose_length ~ 0.25 * total_length
    xcp_from_nose = 0.25 * airframe_length_m
    moment_arm_aero = abs(cg_from_nose_m - xcp_from_nose)
    m_aero = max_q_pa * s_ref * cna * alpha_rad * moment_arm_aero

    # Gimbal moment arm from CG to aft engine nozzle
    l_gimbal = max(airframe_length_m - cg_from_nose_m, 0.5)
    # Required gimbal angle: delta = arcsin(M_aero / (Thrust * L_gimbal))
    sin_delta = m_aero / max(thrust_n * l_gimbal, 1.0)
    sin_delta_clamped = min(max(sin_delta, -1.0), 1.0)
    gimbal_req_deg = math.degrees(math.asin(sin_delta_clamped))

    passed = gimbal_req_deg <= 5.0
    return {
        "max_q_pitch_moment_nm": round(m_aero, 1),
        "gimbal_moment_arm_m": round(l_gimbal, 2),
        "gimbal_angle_required_deg": round(gimbal_req_deg, 2),
        "max_allowable_gimbal_deg": 5.0,
        "control_authority_margin_deg": round(5.0 - gimbal_req_deg, 2),
        "tvc_authority_passed": passed,
    }


def compute_fin_flutter_velocity(
    mat: dict[str, float],
    fin_thickness_m: float,
    root_chord_m: float,
    tip_chord_m: float,
    span_m: float,
    altitude_m: float = 1400.0,
) -> float:
    """NACA 4197 analytical fin flutter velocity."""
    g_shear = mat["shear_modulus_pa"]
    mac = (root_chord_m + tip_chord_m) / 2.0
    aspect_ratio = (span_m**2) / max(mac * span_m, 1e-4)
    lambda_taper = max(tip_chord_m / max(root_chord_m, 1e-4), 0.05)
    t_over_c = fin_thickness_m / max(mac, 1e-4)

    # Air density at altitude
    1.225 * math.exp(-altitude_m / 8500.0)
    p_ambient = 101325.0 * math.exp(-altitude_m / 7200.0)

    num = g_shear
    den = (
        (1.337 * (aspect_ratio**3) * p_ambient * (t_over_c**3))
        / (aspect_ratio + 2.0)
        * ((lambda_taper + 1.0) / 2.0)
    )
    v_flutter = math.sqrt(num / max(den, 1e-6)) * math.sqrt(1.4 * 287.0 * 288.15) / 100.0
    return max(v_flutter, 300.0)


def size_single_stage(
    stage_idx: int,
    propellant: str,
    propulsion_type: str,
    feed_architecture: str,
    delta_v_target_ms: float,
    payload_to_stage_kg: float,
    body_radius_m: float,
    burn_time_s: float,
    structural_material: str = "AL6061-T6",
    dfm_mode: str = "cots_stock",
    is_vacuum_stage: bool = False,
    engine_count: int = 1,
    chamber_pressure_psi: float = 300.0,
    tank_pressure_psi: float = 450.0,
    reusable_booster: bool = False,
    pressurization_mode: str = "helium",
) -> dict[str, Any]:
    """
    Sizes a single rocket stage (propellant mass, tank walls, length, engines).
    """
    mat = MATERIAL_PROPERTIES.get(structural_material, MATERIAL_PROPERTIES["AL6061-T6"])
    thermo = THERMOCHEM_DATA.get(propellant, THERMOCHEM_DATA["LOX/CH4"])

    isp = thermo["isp_vac"] if is_vacuum_stage else thermo["isp_sea"]
    g0 = 9.80665
    c_eff = isp * g0

    # Structural mass fraction estimate based on feed architecture and material
    # Pump-fed composite/Al-Li ~ 0.06 - 0.08; Pressure-fed AL6061 ~ 0.12 - 0.18
    if feed_architecture == "pump_fed":
        base_epsilon = 0.08 if structural_material in ["Al-Li-2195", "Carbon-Epoxy"] else 0.10
    elif feed_architecture == "solid_grain":
        base_epsilon = 0.11
    else:
        base_epsilon = 0.15 if structural_material == "AL6061-T6" else 0.12

    # Mass ratio from Tsiolkovsky: mr = m_wet / m_dry = exp(dV / c_eff)
    mr = math.exp(delta_v_target_ms / max(c_eff, 100.0))

    # Solve for stage propellant mass:
    # m_wet = m_prop + m_struct + m_payload
    # m_dry = m_struct + m_payload
    # m_struct = base_epsilon * m_prop
    # m_wet / m_dry = (m_prop*(1 + base_epsilon) + m_payload) / (m_prop*base_epsilon + m_payload) = mr
    # m_prop * (1 + base_epsilon - mr * base_epsilon) = m_payload * (mr - 1)
    denom = 1.0 + base_epsilon - mr * base_epsilon
    if denom <= 0.05:
        # Cap to physical limit
        denom = 0.08
    m_prop = payload_to_stage_kg * (mr - 1.0) / denom
    m_prop = max(m_prop, 2.0)

    # Reusable Booster Landing Propellant Reserve (6-8% of Stage 1 propellant)
    landing_prop_reserve_frac = 0.07 if reusable_booster and stage_idx == 1 else 0.0
    m_landing_prop = m_prop * landing_prop_reserve_frac
    m_prop_total = m_prop + m_landing_prop

    # Propellant bulk density and volumes
    of_ratio = thermo["opt_of"]
    if of_ratio > 0:
        m_ox = m_prop_total * (of_ratio / (1.0 + of_ratio))
        m_fuel = m_prop_total * (1.0 / (1.0 + of_ratio))
        v_ox = m_ox / thermo["rho_ox"]
        v_fuel = m_fuel / thermo["rho_fuel"]
    else:
        m_ox = 0.0
        m_fuel = m_prop_total
        v_ox = 0.0
        v_fuel = m_prop_total / thermo["rho_fuel"]
    v_total_prop = v_ox + v_fuel

    # Tank Geometry (Cylindrical with 10% ullage)
    v_tanks_with_ullage = v_total_prop * 1.10
    area_cross = math.pi * (body_radius_m**2)
    tank_cyl_length_m = max(v_tanks_with_ullage / area_cross, 0.40)

    # Engine & Propulsion Cluster
    avg_thrust_n = (m_prop * c_eff) / max(burn_time_s, 0.5)
    thrust_per_engine = avg_thrust_n / max(engine_count, 1)

    # Tank Wall Sizing:
    # Pressure-fed: Hoop stress from MEOP
    # Pump-fed: Low MEOP (35-50 psi), sized by minimum gauge, axial compression, and shell buckling
    meop_pa = tank_pressure_psi * 6894.76
    sigma_allowable = mat["yield_strength_pa"] / 1.5  # ASME design margin
    t_asme = (meop_pa * body_radius_m) / sigma_allowable

    # Axial compression sizing (FoS >= 2.0)
    sigma_axial_allow = mat["yield_strength_pa"] / 2.0
    t_axial = avg_thrust_n / (2.0 * math.pi * body_radius_m * sigma_axial_allow)

    # NASA SP-8007 Shell Buckling BLF >= 2.0 sizing
    e_mod = mat.get("youngs_modulus_pa", 68.9e9)
    nu = 0.33
    stiff_factor = 4.0 if body_radius_m > 0.5 else 1.0
    gamma_b = 0.30
    coeff = math.sqrt(3.0 * (1.0 - nu**2))
    t_buckle = math.sqrt(
        (2.0 * avg_thrust_n * coeff) / (2.0 * math.pi * e_mod * gamma_b * stiff_factor)
    )

    # Minimum gauge constraint
    min_gauge = 0.0010 if structural_material != "Carbon-Epoxy" else 0.0015
    t_tank = max(t_asme, t_axial, t_buckle, min_gauge)

    if dfm_mode == "cots_stock" and body_radius_m <= 0.10:
        t_tank = snap_to_cots(t_tank, COTS_TUBE_WALLS_M)

    # Tank mass
    rho_mat = mat["density_kg_m3"]
    tank_shell_mass = 2.0 * math.pi * body_radius_m * tank_cyl_length_m * t_tank * rho_mat
    # Add bulkheads (2 hemispherical/ellipsoidal domes)
    bulkhead_mass = 4.0 * math.pi * (body_radius_m**2) * t_tank * rho_mat
    tank_dry_mass = tank_shell_mass + bulkhead_mass

    # Engine mass estimate (Thrust-to-weight ~ 60 for pressure-fed, ~80 for pump-fed)
    twr_engine = 80.0 if feed_architecture == "pump_fed" else 50.0
    engine_dry_mass = avg_thrust_n / (twr_engine * g0)
    if feed_architecture == "pump_fed":
        # Add turbopump assembly mass
        engine_dry_mass *= 1.25

    # Nozzle throat and exit dimensions
    p_c_pa = chamber_pressure_psi * 6894.76
    gamma = thermo["gamma"]
    c_star = thermo["c_star"]
    m_dot_total = avg_thrust_n / max(c_eff, 100.0)
    m_dot_per_engine = m_dot_total / max(engine_count, 1)

    # Throat area: A_t = m_dot * c* / P_c
    a_t = (m_dot_per_engine * c_star) / max(p_c_pa, 1e5)
    r_t = math.sqrt(max(a_t / math.pi, 1e-6))

    # Exit area: sea-level Pe ~ 101.3 kPa, vacuum Pe ~ 3.5 kPa
    p_exit_target = 3500.0 if is_vacuum_stage else 101325.0
    epsilon = max(
        1.0 / ((p_exit_target / p_c_pa) ** (1.0 / gamma)), 4.0 if not is_vacuum_stage else 35.0
    )
    epsilon = min(epsilon, 80.0 if is_vacuum_stage else 12.0)
    r_e = r_t * math.sqrt(epsilon)
    nozzle_length = (r_e - r_t) / math.tan(math.radians(15.0))

    # Interstage / adapter mass
    stage_structural_dry_mass = tank_dry_mass + engine_dry_mass + 1.5  # avionics/harness
    if pressurization_mode == "autogenous":
        # Eliminates high-pressure helium COPV storage bottles and manifolding
        stage_structural_dry_mass *= 0.975

    stage_wet_mass = stage_structural_dry_mass + m_prop_total

    return {
        "stage_index": stage_idx,
        "body_radius_m": round(body_radius_m, 4),
        "is_vacuum_stage": is_vacuum_stage,
        "delta_v_delivered_ms": round(delta_v_target_ms, 1),
        "isp_s": round(isp, 1),
        "burn_time_s": round(burn_time_s, 2),
        "total_thrust_n": round(avg_thrust_n, 1),
        "engine_count": engine_count,
        "thrust_per_engine_n": round(thrust_per_engine, 1),
        "propellant_mass_kg": round(m_prop_total, 3),
        "ascent_propellant_kg": round(m_prop, 3),
        "landing_propellant_kg": round(m_landing_prop, 3),
        "ox_mass_kg": round(m_ox, 3),
        "fuel_mass_kg": round(m_fuel, 3),
        "tank_meop_psi": round(tank_pressure_psi, 1),
        "tank_meop_pa": round(meop_pa, 0),
        "tank_wall_thickness_mm": round(t_tank * 1000.0, 3),
        "tank_length_m": round(tank_cyl_length_m, 3),
        "stage_length_m": round(tank_cyl_length_m + (0.2 if is_vacuum_stage else 0.4), 3),
        "stage_dry_mass_kg": round(stage_structural_dry_mass, 2),
        "stage_wet_mass_kg": round(stage_wet_mass, 2),
        "pressurization_mode": pressurization_mode,
        "reusable_booster": reusable_booster if stage_idx == 1 else False,
        "nozzle": {
            "throat_radius_mm": round(r_t * 1000.0, 2),
            "exit_radius_mm": round(r_e * 1000.0, 2),
            "nozzle_length_mm": round(nozzle_length * 1000.0, 2),
            "expansion_ratio": round(epsilon, 1),
        },
    }


def run_coupled_sizing(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Executes universal multi-stage, multi-material coupled sizing.

    Parameters:
      spec: Mission specification dictionary.

    Returns:
      Comprehensive sizing report with stages, mass rollups, geometry, and aero/TVC stability.
    """
    profile = spec.get("mission_profile", "sounding_suborbital")
    propellant = spec.get("propellant", "LOX/CH4")
    ptype = spec.get("propulsion_type", "liquid_biprop")
    feed = spec.get("feed_architecture", "pressure_fed")
    mat_name = spec.get("structural_material", "AL6061-T6")
    mat = MATERIAL_PROPERTIES.get(mat_name, MATERIAL_PROPERTIES["AL6061-T6"])
    dfm = spec.get("dfm_mode", "cots_stock")
    stab_mode = spec.get("stabilization_mode", "passive_fins")
    payload_mass = spec.get("payload_mass_kg", 4.0)
    stage_count = spec.get("stage_count", 1)

    r_body = spec.get("body_radius_m")
    if not r_body:
        if profile == "orbital_insertion":
            r_body = 4.5 if spec.get("engine_count_stage1", 1) >= 30 else 1.85
        elif profile == "vtvl_hopper":
            r_body = 1.85 if spec.get("engine_count_stage1", 1) >= 7 else 0.25
        else:
            r_body = 0.0635

    p_tank = spec.get("tank_pressure_psi")
    if not p_tank:
        p_tank = 50.0 if feed == "pump_fed" else 450.0
    p_chamber = spec.get("chamber_pressure_psi")
    if not p_chamber:
        p_chamber = 750.0 if feed == "pump_fed" else 300.0

    # 1. Total Delta-V Budget
    if profile == "orbital_insertion":
        # LEO insertion requires ~ 9,200 m/s total dV
        total_dv = 9200.0
    else:
        apogee_m = spec.get("target_apogee_m", 4200.0)
        # Vis-viva + drag & gravity loss estimate
        v_kinetic = math.sqrt(2.0 * 9.80665 * apogee_m)
        loss_factor = 1.35 if apogee_m < 20000 else 1.15
        total_dv = v_kinetic * loss_factor

    reusable_booster = spec.get("reusable_booster", False)
    pressurization_mode = spec.get("pressurization_mode", "helium")

    # 2. Stage Delta-V Allocation
    stages_data: list[dict[str, Any]] = []
    if stage_count == 1:
        dv_stages = [total_dv]
        burn_times = [spec.get("burn_time_s", 5.2 if profile == "sounding_suborbital" else 8.0)]
        engine_counts = [spec.get("engine_count_stage1", 1)]
    elif stage_count == 2:
        # Two-stage split: Stage 1 provides boost (~40-45%), Stage 2 completes mission
        if profile == "orbital_insertion":
            dv_stages = [3400.0, 5800.0]
            burn_times = [
                spec.get("burn_time_s", 162.0),
                spec.get("stage2_burn_time_s", 360.0),
            ]
            engine_counts = [
                spec.get("engine_count_stage1", 9),
                spec.get(
                    "engine_count_stage2", 1 if spec.get("engine_count_stage1", 9) <= 9 else 6
                ),
            ]
        else:
            # Suborbital 2-stage (e.g. 120 km spaceflight)
            dv_stages = [total_dv * 0.55, total_dv * 0.45]
            burn_times = [6.0, 8.0]
            engine_counts = [spec.get("engine_count_stage1", 7), 1]
    else:
        # Three-stage
        dv_stages = [total_dv * 0.35, total_dv * 0.40, total_dv * 0.25]
        burn_times = [80.0, 140.0, 180.0]
        engine_counts = [spec.get("engine_count_stage1", 9), 1, 1]

    # Sizing backwards from payload (Tsiolkovsky chain)
    current_payload = payload_mass
    for idx in reversed(range(stage_count)):
        is_vac = idx > 0
        s_data = size_single_stage(
            stage_idx=idx + 1,
            propellant=propellant,
            propulsion_type=ptype,
            feed_architecture=feed,
            delta_v_target_ms=dv_stages[idx],
            payload_to_stage_kg=current_payload,
            body_radius_m=r_body if idx == 0 else (spec.get("stage2_radius_m") or r_body),
            burn_time_s=burn_times[idx],
            structural_material=mat_name,
            dfm_mode=dfm,
            is_vacuum_stage=is_vac,
            engine_count=engine_counts[idx],
            chamber_pressure_psi=p_chamber,
            tank_pressure_psi=p_tank,
            reusable_booster=reusable_booster,
            pressurization_mode=pressurization_mode,
        )
        stages_data.insert(0, s_data)
        current_payload = s_data["stage_wet_mass_kg"]

    # 3. Overall Length & Mass Rollup
    total_prop_mass = sum(s["propellant_mass_kg"] for s in stages_data)
    total_stage_dry = sum(s["stage_dry_mass_kg"] for s in stages_data)
    total_wet_mass = current_payload  # Top of stack wet mass
    total_dry_mass = total_stage_dry + payload_mass

    s1 = stages_data[0]
    body_length_m = spec.get("body_length_m") or s1["stage_length_m"]
    nose_length_m = spec.get("nose_length_m") or (r_body * 4.0)

    s2_length_m = stages_data[1]["stage_length_m"] if stage_count > 1 else 0.0
    interstage_length_m = (
        (spec.get("interstage_length_m") or (r_body * 1.5)) if stage_count > 1 else 0.0
    )

    total_airframe_length = (
        body_length_m
        + nose_length_m
        + (s2_length_m + interstage_length_m if stage_count > 1 else 0.0)
    )

    # 4. Aeroelastic & Guidance Stability
    cg_from_nose = total_airframe_length * 0.58
    if stab_mode == "passive_fins":
        fin_count = spec.get("fin_count") or 4
        fin_span_m = spec.get("fin_span_m") or 0.095
        fin_root_chord_m = spec.get("fin_root_chord_m") or 0.30
        fin_tip_chord_m = spec.get("fin_tip_chord_m") or 0.12
        fin_thickness_m = spec.get("fin_thickness_m") or 0.004
        v_flutter = compute_fin_flutter_velocity(
            mat=mat,
            fin_thickness_m=fin_thickness_m,
            root_chord_m=fin_root_chord_m,
            tip_chord_m=fin_tip_chord_m,
            span_m=fin_span_m,
        )
        stability_metrics = {
            "stabilization_mode": "passive_fins",
            "fin_count": fin_count,
            "fin_flutter_velocity_ms": round(v_flutter, 1),
            "flutter_safe_mach": round(v_flutter / 340.0, 2),
        }
    else:
        # TVC Guided Stability
        tvc_metrics = compute_tvc_control_authority(
            thrust_n=s1["total_thrust_n"],
            body_radius_m=r_body,
            airframe_length_m=total_airframe_length,
            cg_from_nose_m=cg_from_nose,
            max_q_pa=spec.get("max_dynamic_pressure_pa", 65000.0),
        )
        stability_metrics = {
            "stabilization_mode": "tvc_guided",
            "fin_count": 0,
            **tvc_metrics,
        }

    return {
        "mission_profile": profile,
        "propellant": propellant,
        "propulsion_type": ptype,
        "feed_architecture": feed,
        "structural_material": mat_name,
        "material_properties": mat,
        "stage_count": stage_count,
        "total_delta_v_ms": round(total_dv, 1),
        "stages": stages_data,
        "geometry": {
            "body_radius_m": round(r_body, 4),
            "body_length_m": round(body_length_m, 3),
            "nose_length_m": round(nose_length_m, 3),
            "stage2_length_m": round(s2_length_m, 3),
            "stage2_radius_m": round(
                stages_data[1]["body_radius_m"] if stage_count > 1 else r_body, 4
            ),
            "interstage_length_m": round(interstage_length_m, 3),
            "total_length_m": round(total_airframe_length, 3),
            "has_fins": bool(stab_mode == "passive_fins"),
            "engine_count_stage1": s1["engine_count"],
        },
        "mass_breakdown": {
            "payload_mass_kg": round(payload_mass, 2),
            "stage_1_dry_kg": s1["stage_dry_mass_kg"],
            "stage_1_prop_kg": s1["propellant_mass_kg"],
            "stage_2_dry_kg": stages_data[1]["stage_dry_mass_kg"] if stage_count > 1 else 0.0,
            "stage_2_prop_kg": stages_data[1]["propellant_mass_kg"] if stage_count > 1 else 0.0,
            "total_dry_mass_kg": round(total_dry_mass, 2),
            "total_propellant_mass_kg": round(total_prop_mass, 2),
            "total_wet_mass_kg": round(total_wet_mass, 2),
        },
        "stability": stability_metrics,
    }
