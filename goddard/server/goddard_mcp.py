"""
Universal FastMCP Server for the Goddard Autonomous Rocket Design Suite.

Exposes tools for:
  - Universal mission requirements gate (validate_mission_requirements)
  - Multi-stage, multi-material, TVC-guided CAD-to-Physics evaluation (evaluate_rocket_design)
  - Architecture-aware constraint verification (check_mission_constraints)
  - Design lineage ledger retrieval (get_design_ledger)
"""

from __future__ import annotations

import datetime
import json
import math
import os
import pathlib
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from goddard.client.client import OnshapeClient
from goddard.client.mock import MockOnshapeClient
from goddard.sim.cfd_solver import run_cfd_mach_sweep
from goddard.sim.fea_solver import evaluate_analytical_airframe_margins, run_structural_fea
from goddard.sim.flight_sim import run_sounding_rocket_sim
from goddard.sim.mesher import build_cfd_farfield_mesh, mesh_step_file
from goddard.sim.vtvl_landing import simulate_booster_landing
from goddard.sizing.coupled_wer import run_coupled_sizing
from goddard.sizing.mission_spec import evaluate_spec_completeness

# ── Paths & Environment ───────────────────────────────────────────────────
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = pathlib.Path(os.getenv("GODDARD_ROOT", PACKAGE_ROOT.parent))

if (REPO_ROOT / ".env").exists():
    load_dotenv(REPO_ROOT / ".env")
elif (pathlib.Path.cwd() / ".env").exists():
    load_dotenv(pathlib.Path.cwd() / ".env")
else:
    load_dotenv()

DESIGNS_DIR = pathlib.Path(
    os.getenv(
        "GODDARD_DESIGNS_DIR",
        REPO_ROOT / "designs"
        if (REPO_ROOT / "designs").exists()
        else pathlib.Path.cwd() / "designs",
    )
)
DESIGNS_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = DESIGNS_DIR / "design_ledger.json"
CAD_FS_PATH = pathlib.Path(
    os.getenv(
        "GODDARD_CAD_FS",
        REPO_ROOT / "cad" / "goddard_rocket.fs"
        if (REPO_ROOT / "cad" / "goddard_rocket.fs").exists()
        else pathlib.Path.cwd() / "cad" / "goddard_rocket.fs",
    )
)

ACCESS_KEY = os.getenv("ONSHAPE_ACCESS_KEY", "")
SECRET_KEY = os.getenv("ONSHAPE_SECRET_KEY", "")
DID = os.getenv("ONSHAPE_DID", "")
WID = os.getenv("ONSHAPE_WID", "")
PART_EID = os.getenv("ONSHAPE_EID", "")

FS_NAME = "GoddardRocketFS"
FEATURE_TYPE = "goddardRocketAirframe"
FEATURE_NAME = "Goddard Rocket Candidate"

# ── Initialize MCP Server ─────────────────────────────────────────────────
mcp = FastMCP("goddard-rocket-server")


def _read_ledger() -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    try:
        with open(LEDGER_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _write_ledger(ledger: list[dict[str, Any]]) -> None:
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2)


def _ensure_client() -> OnshapeClient | MockOnshapeClient:
    ak = os.getenv("ONSHAPE_ACCESS_KEY", ACCESS_KEY)
    sk = os.getenv("ONSHAPE_SECRET_KEY", SECRET_KEY)
    mock_flag = os.getenv("GODDARD_MOCK_ONSHAPE", "").lower() in ("1", "true", "yes")
    offline_mode = os.getenv("GODDARD_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
    if not ak or not sk or not DID or not WID or not PART_EID:
        if mock_flag or offline_mode or not ak or not sk:
            return MockOnshapeClient()
        raise ValueError(
            "Onshape credentials or document IDs missing. Set GODDARD_MOCK_ONSHAPE=1 to use MockOnshapeClient."
        )
    return OnshapeClient(ak, sk)


@mcp.tool()
def validate_mission_requirements(user_inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Validate customer mission requirements across civil sounding rockets,
    suborbital scientific vehicles, and orbital launch vehicles.

    Returns:
      status='NEEDS_CLARIFICATION' with domain questions if underspecified, or
      status='READY' with resolved defaults and free optimization variables.
    """
    return evaluate_spec_completeness(user_inputs)


@mcp.tool()
def evaluate_rocket_design(
    mission_profile: str = "sounding_suborbital",
    target_apogee_m: float = 4200.0,
    target_orbit_km: float | None = None,
    stage_count: int = 1,
    stabilization_mode: str = "passive_fins",
    launch_mode: str = "rail",
    feed_architecture: str = "pressure_fed",
    propulsion_type: str = "liquid_biprop",
    propellant: str = "LOX/CH4",
    structural_material: str = "AL6061-T6",
    dfm_mode: str = "cots_stock",
    engine_count_stage1: int = 1,
    reusable_booster: bool = False,
    pressurization_mode: str = "helium",
    payload_mass_kg: float = 4.0,
    nozzle_exit_radius_m: float = 0.025,
    nozzle_length_m: float = 0.050,
    body_radius_m: float = 0.0635,
    body_length_m: float = 1.2,
    stage2_radius_m: float = 0.0635,
    stage2_length_m: float = 0.8,
    interstage_length_m: float = 0.15,
    nose_length_m: float = 0.55,
    fin_count: int = 4,
    fin_root_chord_m: float = 0.30,
    fin_tip_chord_m: float = 0.12,
    fin_span_m: float = 0.14,
    fin_thickness_m: float = 0.004,
    total_impulse_ns: float = 6500.0,
    burn_time_s: float = 3.5,
    ballast_mass_kg: float = 10.18,
    fidelity: str = "fast",
    coupled_spec: dict[str, Any] | None = None,
    design_rationale: str = "",
) -> dict[str, Any]:
    """
    Execute universal CAD-to-Physics evaluation for single or multi-stage launch vehicles.

    Fidelity Tiers:
      - 'fast': Coupled Sizing -> Onshape CAD & Mass -> Gmsh Mesh -> Analytical FEA -> Flight Sim (~5-10s)
      - 'full': Fast loop + Gmsh External CFD (.su2) + CalculiX FEA (.inp) + SU2 Mach Sweep (.cfg) + Dynamic Drag Ingestion (~30-45s)
    """
    client = _ensure_client()
    ledger = _read_ledger()
    rev_id = len(ledger) + 1
    rev_dir = DESIGNS_DIR / f"rev_{rev_id:03d}"
    rev_dir.mkdir(parents=True, exist_ok=True)

    # 1. Multi-Stage Coupled Sizing & DFM
    if coupled_spec:
        sizing_results = run_coupled_sizing(coupled_spec)
        geom = sizing_results.get("geometry", {})
        body_radius_m = geom.get("body_radius_m", body_radius_m)
        body_length_m = geom.get("body_length_m", body_length_m)
        nose_length_m = geom.get("nose_length_m", nose_length_m)
        stage2_length_m = geom.get("stage2_length_m", stage2_length_m)
        interstage_length_m = geom.get("interstage_length_m", interstage_length_m)
        stage_count = sizing_results.get("stage_count", stage_count)
        stabilization_mode = sizing_results.get("stability", {}).get(
            "stabilization_mode", stabilization_mode
        )
        reusable_booster = coupled_spec.get("reusable_booster", reusable_booster)
        pressurization_mode = coupled_spec.get("pressurization_mode", pressurization_mode)
        payload_mass_kg = coupled_spec.get("payload_mass_kg", payload_mass_kg)
    else:
        sizing_results = run_coupled_sizing(
            {
                "mission_profile": mission_profile,
                "target_apogee_m": target_apogee_m,
                "target_orbit_km": target_orbit_km,
                "stage_count": stage_count,
                "stabilization_mode": stabilization_mode,
                "launch_mode": launch_mode,
                "feed_architecture": feed_architecture,
                "propulsion_type": propulsion_type,
                "propellant": propellant,
                "structural_material": structural_material,
                "dfm_mode": dfm_mode,
                "engine_count_stage1": engine_count_stage1,
                "reusable_booster": reusable_booster,
                "pressurization_mode": pressurization_mode,
                "payload_mass_kg": payload_mass_kg,
                "body_radius_m": body_radius_m,
                "body_length_m": body_length_m,
                "nose_length_m": nose_length_m,
                "fin_span_m": fin_span_m,
                "fin_root_chord_m": fin_root_chord_m,
                "fin_tip_chord_m": fin_tip_chord_m,
                "fin_thickness_m": fin_thickness_m,
                "burn_time_s": burn_time_s,
            }
        )

    # Update nozzle dimensions from Stage 1 sizing if available
    if "stages" in sizing_results and len(sizing_results["stages"]) > 0:
        s1_noz = sizing_results["stages"][0].get("nozzle", {})
        if s1_noz.get("exit_radius_mm"):
            nozzle_exit_radius_m = s1_noz["exit_radius_mm"] / 1000.0
        if s1_noz.get("nozzle_length_mm"):
            nozzle_length_m = s1_noz["nozzle_length_mm"] / 1000.0

    # 2. Ensure Feature Studio has latest FeatureScript
    elements = client.get(f"/documents/d/{DID}/w/{WID}/elements").json()
    fs_eid = None
    for el in elements:
        if el.get("name") == FS_NAME and el.get("elementType") == "FEATURESTUDIO":
            fs_eid = el["id"]
            break

    if not fs_eid:
        fs_eid = client.create_feature_studio(DID, WID, name=FS_NAME)

    if CAD_FS_PATH.exists():
        with open(CAD_FS_PATH) as f:
            fs_code = f.read()
    else:
        fs_code = "// Goddard Rocket FeatureScript"
    client.update_feature_studio_code(DID, WID, fs_eid, fs_code)

    # 3. Clean prior candidate features in Part Studio
    feat_list = client.list_features(DID, WID, PART_EID)
    for feat in feat_list.get("features", []):
        if feat.get("featureType") == FEATURE_TYPE or feat.get("name") == FEATURE_NAME:
            try:
                client.delete_feature(DID, WID, PART_EID, feat["featureId"])
            except Exception:
                pass

    # 4. Instantiate Candidate Feature in Onshape
    has_fins = bool(stabilization_mode != "tvc_guided" and fin_count > 0)
    params = [
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "bodyRadius",
            "expression": f"{body_radius_m * 1000.0:.3f} mm",
            "value": body_radius_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "bodyLength",
            "expression": f"{body_length_m:.4f} m",
            "value": body_length_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "noseLength",
            "expression": f"{nose_length_m:.4f} m",
            "value": nose_length_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "stageCount",
            "expression": str(stage_count),
            "value": float(stage_count),
            "units": "",
            "isInteger": True,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "stage2Length",
            "expression": f"{stage2_length_m:.4f} m",
            "value": stage2_length_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "stage2Radius",
            "expression": f"{stage2_radius_m * 1000.0:.3f} mm",
            "value": stage2_radius_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "interstageLength",
            "expression": f"{interstage_length_m:.4f} m",
            "value": interstage_length_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterBoolean-144",
            "type": 144,
            "typeName": "BTMParameterBoolean",
            "parameterId": "hasFins",
            "value": has_fins,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "finCount",
            "expression": str(fin_count if has_fins else 0),
            "value": float(fin_count if has_fins else 0),
            "units": "",
            "isInteger": True,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "finRootChord",
            "expression": f"{fin_root_chord_m:.4f} m",
            "value": fin_root_chord_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "finTipChord",
            "expression": f"{fin_tip_chord_m:.4f} m",
            "value": fin_tip_chord_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "finSpan",
            "expression": f"{fin_span_m if has_fins else 0.001:.4f} m",
            "value": fin_span_m if has_fins else 0.001,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "finThickness",
            "expression": f"{fin_thickness_m * 1000.0:.3f} mm",
            "value": fin_thickness_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "engineCount",
            "expression": str(engine_count_stage1),
            "value": float(engine_count_stage1),
            "units": "",
            "isInteger": True,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "nozzleExitRadius",
            "expression": f"{nozzle_exit_radius_m * 1000.0:.3f} mm",
            "value": nozzle_exit_radius_m,
            "units": "meter",
            "isInteger": False,
        },
        {
            "btType": "BTMParameterQuantity-147",
            "type": 147,
            "typeName": "BTMParameterQuantity",
            "parameterId": "nozzleLength",
            "expression": f"{nozzle_length_m * 1000.0:.3f} mm",
            "value": nozzle_length_m,
            "units": "meter",
            "isInteger": False,
        },
    ]

    client.add_custom_feature(
        DID,
        WID,
        PART_EID,
        fs_eid,
        feature_type=FEATURE_TYPE,
        feature_name=FEATURE_NAME,
        parameters=params,
    )

    # 5. Extract CAD Mass Properties using structural material density
    mp = client.get_mass_properties(
        DID,
        WID,
        PART_EID,
        structural_material=structural_material,
        body_radius_m=body_radius_m,
    )
    airframe_mass_kg = mp["mass_kg"]
    pi = mp["principal_inertia_kg_m2"]
    com = mp["center_of_mass_m"]

    # 6. Export STEP file
    step_filename = f"rev_{rev_id:03d}.step"
    step_path = rev_dir / step_filename
    root_step_path = DESIGNS_DIR / step_filename

    tr = client.create_translation(
        DID,
        WID,
        PART_EID,
        {
            "formatName": "STEP",
            "storeInDocument": False,
        },
    )
    tr_status = client.poll_translation(tr["id"], timeout=120, interval=2)
    ext_ids = tr_status.get("resultExternalDataIds", [])
    if not ext_ids:
        raise RuntimeError(f"STEP translation completed without data: {tr_status}")
    step_bytes = client.download_external_data(DID, ext_ids[0])
    step_path.write_bytes(step_bytes)
    root_step_path.write_bytes(step_bytes)

    # 7. 3D Tetrahedral Meshing (Gmsh)
    msh_filename = f"rev_{rev_id:03d}.msh"
    msh_path = rev_dir / msh_filename
    root_msh_path = DESIGNS_DIR / msh_filename
    mesh_metrics = mesh_step_file(str(step_path), str(msh_path), mesh_size_factor=0.03)
    if msh_path.exists():
        root_msh_path.write_bytes(msh_path.read_bytes())

    # 8. Tiered FEA, CFD & Flight Sim Execution
    cd_table = None
    cfd_metrics: dict[str, Any] = {}
    fea_metrics: dict[str, Any] = {}
    cots_wall_m = 0.001651

    total_airframe_len = (
        body_length_m
        + nose_length_m
        + (stage2_length_m + interstage_length_m if stage_count > 1 else 0.0)
    )

    t_wall = cots_wall_m
    if "stages" in sizing_results and len(sizing_results["stages"]) > 0:
        s1_t_mm = sizing_results["stages"][0].get("tank_wall_thickness_mm")
        if s1_t_mm:
            t_wall = s1_t_mm / 1000.0

    s1_data = sizing_results.get("stages", [{}])[0] if sizing_results.get("stages") else {}
    s1_burn = s1_data.get("burn_time_s", burn_time_s)
    s1_impulse = s1_data.get("total_thrust_n", total_impulse_ns / max(s1_burn, 0.1)) * s1_burn

    if stage_count > 1 and len(sizing_results.get("stages", [])) > 1:
        s2_data = sizing_results["stages"][1]
        s2_burn = s2_data.get("burn_time_s", burn_time_s * 1.25)
        s2_impulse = (
            s2_data.get("total_thrust_n", total_impulse_ns * 0.75 / max(s2_burn, 0.1)) * s2_burn
        )
        s2_dry_mass = s2_data.get("stage_dry_mass_kg", (airframe_mass_kg + ballast_mass_kg) * 0.45)
    else:
        s2_burn = burn_time_s * 1.25
        s2_impulse = total_impulse_ns * 0.75
        s2_dry_mass = (airframe_mass_kg + ballast_mass_kg) * 0.45

    if fidelity.lower() == "full":
        # A. CFD External Mesh (.su2)
        su2_filename = f"rev_{rev_id:03d}_cfd.su2"
        su2_path = rev_dir / su2_filename
        build_cfd_farfield_mesh(
            step_path=str(step_path),
            output_su2_path=str(su2_path),
            domain_scale=3.0,
        )

        # B. CalculiX Structural FEA (.inp + execution)
        fea_dir = rev_dir / "calculix"
        fea_dir.mkdir(exist_ok=True)
        fea_metrics = run_structural_fea(
            msh_path=str(msh_path),
            peak_thrust_n=s1_impulse / max(s1_burn, 0.1),
            max_q_drag_n=650.0 if body_radius_m < 0.2 else 50000.0,
            tank_pressure_pa=3.1e6 if feed_architecture == "pressure_fed" else 0.35e6,
            airframe_radius_m=body_radius_m,
            wall_thickness_m=t_wall,
            airframe_length_m=total_airframe_len,
            output_inp_path=str(fea_dir / "airframe_fea.inp"),
        )

        # C. Compressible CFD Mach Sweep (.cfg + execution)
        cfd_dir = rev_dir / "cfd"
        cfd_dir.mkdir(exist_ok=True)
        ref_area = math.pi * (body_radius_m**2)
        cfd_metrics = run_cfd_mach_sweep(
            su2_mesh_path=str(su2_path),
            mach_numbers=[0.4, 0.85, 1.05, 1.5, 2.2],
            ref_area_m2=ref_area,
            output_dir=str(cfd_dir),
            airframe_length_m=total_airframe_len,
            airframe_radius_m=body_radius_m,
        )
        cd_table = list(zip(cfd_metrics["mach_numbers"], cfd_metrics["cd_curve"]))

    else:
        # Fast mode: analytical structural margins
        peak_thrust_n = s1_impulse / max(s1_burn, 0.1)
        fea_metrics = evaluate_analytical_airframe_margins(
            thrust_n=peak_thrust_n,
            max_q_drag_n=600.0 if body_radius_m < 0.2 else 50000.0,
            tank_pressure_pa=3.1e6 if feed_architecture == "pressure_fed" else 0.35e6,
            radius_m=body_radius_m,
            thickness_m=t_wall,
            length_m=total_airframe_len,
            structural_material=structural_material,
            material_properties=sizing_results.get("material_properties"),
        )
        cfd_metrics = {
            "status": "SKIPPED_FAST_MODE",
            "solver_mode": "baseline_subsonic",
            "note": "Use fidelity='full' to trigger Gmsh CFD farfield mesh, CalculiX .inp FEA, and SU2 Mach sweep.",
        }

    # 9. Multi-Stage 6-DOF Trajectory
    total_dry_mass = airframe_mass_kg + ballast_mass_kg
    flight_cfg = {
        "mission_profile": mission_profile,
        "target_orbit_km": target_orbit_km,
        "stage_count": stage_count,
        "stabilization_mode": stabilization_mode,
        "launch_mode": launch_mode,
        "payload_mass_kg": payload_mass_kg,
        "rocket_radius_m": body_radius_m,
        "rocket_dry_mass_kg": s1_data.get("stage_dry_mass_kg", total_dry_mass)
        if stage_count > 1
        else total_dry_mass,
        "nose_length_m": nose_length_m,
        "airframe_length_m": total_airframe_len,
        "fin_count": fin_count if has_fins else 0,
        "fin_root_chord_m": fin_root_chord_m,
        "fin_tip_chord_m": fin_tip_chord_m,
        "fin_span_m": fin_span_m,
        "total_impulse_ns": s1_impulse,
        "burn_time_s": s1_burn,
        "stage2_impulse_ns": s2_impulse,
        "stage2_burn_time_s": s2_burn,
        "stage2_dry_mass_kg": s2_dry_mass,
        "inertia": (pi[0] + 5.0, pi[1] + 5.0, pi[2] + 0.025),
        "center_of_mass_without_motor": com[2] - 0.70,
        "cd_table": cd_table,
    }
    flight_metrics = run_sounding_rocket_sim(flight_cfg)

    # 10. Booster Propulsive VTVL Landing Simulation
    if reusable_booster or mission_profile == "vtvl_hopper":
        st1_dry = s1_data.get("stage_dry_mass_kg", total_dry_mass)
        landing_prop = s1_data.get(
            "landing_propellant_kg", s1_data.get("propellant_mass_kg", 5000.0) * 0.07
        )
        isp_s = s1_data.get("isp_s", 285.0)
        t_tot = s1_data.get("total_thrust_n", s1_impulse / max(s1_burn, 1.0))
        n_eng = s1_data.get("engine_count", engine_count_stage1)

        st_events = flight_metrics.get("stage_events", [])
        if st_events:
            sep_alt = min(st_events[0].get("burnout_altitude_m", 75000.0), 85000.0)
            st_vz = st_events[0].get("burnout_vz_ms")
            sep_vel = min(st_vz if st_vz is not None else 450.0, 500.0)
        else:
            sep_alt = 75000.0
            sep_vel = 450.0

        vtvl_res = simulate_booster_landing(
            stage1_dry_mass_kg=st1_dry,
            landing_propellant_kg=landing_prop,
            engine_isp_s=isp_s,
            max_thrust_n=t_tot,
            engine_count=n_eng,
            separation_altitude_m=sep_alt,
            separation_velocity_ms=sep_vel,
            rocket_radius_m=body_radius_m,
        )
        flight_metrics["vtvl_landing"] = vtvl_res

    # 11. Record Design Lineage
    record = {
        "revision_id": rev_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fidelity": fidelity,
        "rationale": design_rationale,
        "inputs": {
            "mission_profile": mission_profile,
            "stage_count": stage_count,
            "stabilization_mode": stabilization_mode,
            "launch_mode": launch_mode,
            "feed_architecture": feed_architecture,
            "propulsion_type": propulsion_type,
            "propellant": propellant,
            "structural_material": structural_material,
            "dfm_mode": dfm_mode,
            "engine_count_stage1": engine_count_stage1,
            "reusable_booster": reusable_booster,
            "pressurization_mode": pressurization_mode,
            "payload_mass_kg": payload_mass_kg,
            "target_orbit_km": target_orbit_km,
            "body_radius_m": body_radius_m,
            "body_length_m": body_length_m,
            "stage2_length_m": stage2_length_m,
            "stage2_radius_m": stage2_radius_m,
            "interstage_length_m": interstage_length_m,
            "nose_length_m": nose_length_m,
            "has_fins": has_fins,
            "fin_count": fin_count if has_fins else 0,
            "fin_root_chord_m": fin_root_chord_m,
            "fin_tip_chord_m": fin_tip_chord_m,
            "fin_span_m": fin_span_m,
            "fin_thickness_m": fin_thickness_m,
            "total_impulse_ns": total_impulse_ns,
            "burn_time_s": burn_time_s,
            "ballast_mass_kg": ballast_mass_kg,
        },
        "sizing_metrics": sizing_results,
        "cad_metrics": mp,
        "mesh_metrics": mesh_metrics,
        "fea_metrics": fea_metrics,
        "cfd_metrics": cfd_metrics,
        "flight_metrics": flight_metrics,
        "artifacts": {
            "step_path": str(step_path),
            "msh_path": str(msh_path),
            "rev_dir": str(rev_dir),
        },
    }

    (rev_dir / "report.json").write_text(json.dumps(record, indent=2))
    ledger.append(record)
    _write_ledger(ledger)
    return record


@mcp.tool()
def get_design_ledger() -> list[dict[str, Any]]:
    """
    Retrieve the full history of evaluated rocket design revisions from the design ledger.
    """
    return _read_ledger()


@mcp.tool()
def check_mission_constraints(
    revision_id: int,
    target_apogee_m: float | None = None,
    target_orbit_km: float | None = None,
    apogee_tolerance_m: float = 200.0,
    min_static_margin_cal: float = 2.0,
    max_static_margin_cal: float = 3.0,
    min_rail_exit_velocity_ms: float = 18.0,
    min_structural_fos: float = 2.0,
    min_buckling_blf: float = 2.0,
    max_q_pa: float = 65000.0,
    max_tvc_gimbal_deg: float = 5.0,
) -> dict[str, Any]:
    """
    Check a logged design revision against architecture-specific mission constraints.

    Branches dynamically by stabilization_mode:
      - 'passive_fins': checks aerodynamic static margin & rail-exit velocity
      - 'tvc_guided': checks active gimbal control authority (required angle <= 5 deg)
      - 'multi-stage': checks stage separation & burnout events
    """
    ledger = _read_ledger()
    target_rev = None
    for item in ledger:
        if item.get("revision_id") == revision_id:
            target_rev = item
            break

    if not target_rev:
        raise ValueError(f"Revision {revision_id} not found in design ledger")

    inputs = target_rev.get("inputs", {})
    fm = target_rev.get("flight_metrics", {})
    fea = target_rev.get("fea_metrics", {})

    stab_mode = inputs.get("stabilization_mode", "passive_fins")
    is_tvc = stab_mode == "tvc_guided"
    is_multi_stage = inputs.get("stage_count", 1) > 1

    apogee = fm.get("apogee_m", 0.0)
    max_q = fm.get("max_dynamic_pressure_pa", 0.0)
    fos = fea.get("yield_fos", 3.0)
    blf = fea.get("buckling_load_factor_blf", 3.0)

    violations = []

    # 1. Target Altitude / Orbit / Apogee
    eff_orbit_km = target_orbit_km if target_orbit_km is not None else inputs.get("target_orbit_km")
    if eff_orbit_km is not None:
        orbit_alt_km = apogee / 1000.0
        if orbit_alt_km < eff_orbit_km * 0.95:
            violations.append(
                f"Achieved orbital altitude {orbit_alt_km:.1f} km is below target orbit {eff_orbit_km:.1f} km"
            )
        apogee_err = (orbit_alt_km - eff_orbit_km) * 1000.0
    elif target_apogee_m is not None:
        apogee_err = apogee - target_apogee_m
        if abs(apogee_err) > apogee_tolerance_m:
            violations.append(
                f"Apogee {apogee:.1f} m violates target {target_apogee_m:.1f} ± {apogee_tolerance_m:.1f} m (error: {apogee_err:+.1f} m)"
            )
    else:
        apogee_err = 0.0

    # 2. Stabilization & Safety Checks
    if is_tvc:
        tvc_info = fm.get("tvc_metrics", {})
        gimbal_req = tvc_info.get("gimbal_angle_required_deg", 0.0)
        if gimbal_req > max_tvc_gimbal_deg:
            violations.append(
                f"Required TVC gimbal angle {gimbal_req:.2f}° exceeds maximum allowable authority ({max_tvc_gimbal_deg:.1f}°)"
            )
    else:
        sm = fm.get("static_margin_calibers", {}).get("rail_departure")
        if sm is not None:
            if sm < min_static_margin_cal:
                violations.append(
                    f"Launch static margin {sm:.2f} cal is under-stable (min: {min_static_margin_cal:.2f} cal)"
                )
            elif sm > max_static_margin_cal:
                violations.append(
                    f"Launch static margin {sm:.2f} cal is over-stable (max: {max_static_margin_cal:.2f} cal)"
                )

        v_rail = fm.get("rail_exit_velocity_ms", 0.0)
        if inputs.get("launch_mode") == "rail" and v_rail < min_rail_exit_velocity_ms:
            violations.append(
                f"Rail exit velocity {v_rail:.1f} m/s is below safety threshold ({min_rail_exit_velocity_ms:.1f} m/s)"
            )

    # 3. Multi-Stage Separation Verification
    if is_multi_stage:
        stage_events = fm.get("stage_events", [])
        if len(stage_events) < inputs.get("stage_count", 2):
            violations.append(
                f"Multi-stage flight failed to execute all stage separation events (recorded {len(stage_events)} events)"
            )

    # 4. Structural Safety Margins
    if fos < min_structural_fos:
        violations.append(
            f"Structural Factor of Safety {fos:.2f} violates minimum requirement ({min_structural_fos:.2f})"
        )
    if blf < min_buckling_blf:
        violations.append(
            f"Buckling Load Factor {blf:.2f} violates minimum requirement ({min_buckling_blf:.2f})"
        )

    # 5. Max Dynamic Pressure
    if max_q > max_q_pa:
        violations.append(
            f"Max dynamic pressure {max_q:.0f} Pa exceeds limit {max_q_pa:.0f} Pa (excess: {max_q - max_q_pa:+.0f} Pa)"
        )

    # 6. Reusable Booster Propulsive VTVL Landing Check
    is_reusable = inputs.get("reusable_booster", False) or (
        inputs.get("mission_profile") == "vtvl_hopper"
    )
    vtvl = fm.get("vtvl_landing")
    if is_reusable:
        if not vtvl:
            violations.append(
                "Reusable booster mission did not generate VTVL landing trajectory data"
            )
        else:
            if not vtvl.get("landing_success", False):
                violations.append(
                    f"Booster VTVL landing failed (touchdown velocity {vtvl.get('touchdown_velocity_ms')} m/s, prop remaining {vtvl.get('propellant_remaining_kg')} kg)"
                )
            elif vtvl.get("touchdown_velocity_ms", 999.0) > 2.5:
                violations.append(
                    f"Booster touchdown velocity {vtvl.get('touchdown_velocity_ms')} m/s exceeds max allowable (2.5 m/s)"
                )

    return {
        "revision_id": revision_id,
        "passed": len(violations) == 0,
        "violations": violations,
        "deltas": {
            "apogee_error_m": round(apogee_err, 2),
            "stabilization_mode": stab_mode,
            "tvc_gimbal_req_deg": fm.get("tvc_metrics", {}).get("gimbal_angle_required_deg")
            if is_tvc
            else None,
            "launch_static_margin_cal": fm.get("static_margin_calibers", {}).get("rail_departure")
            if not is_tvc
            else None,
            "rail_exit_velocity_ms": fm.get("rail_exit_velocity_ms") if not is_tvc else None,
            "structural_fos": round(fos, 2),
            "buckling_blf": round(blf, 2),
            "max_dynamic_pressure_pa": round(max_q, 1),
            "stage_events_recorded": len(fm.get("stage_events", [])),
            "vtvl_landing_success": vtvl.get("landing_success") if is_reusable and vtvl else None,
            "vtvl_touchdown_velocity_ms": vtvl.get("touchdown_velocity_ms")
            if is_reusable and vtvl
            else None,
        },
    }


def main() -> None:
    """Entrypoint to run the Goddard FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
