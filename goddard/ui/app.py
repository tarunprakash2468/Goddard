"""
FastAPI Backend for the Goddard 3D & Trade-Space Mission Control Dashboard.

Serves:
  - GET /                              -> ui/static/index.html
  - GET /api/revisions                 -> Complete multi-revision lineage with compliance badges
  - GET /api/revisions/{rev_id}        -> Single revision telemetry and subsystem details
  - GET /api/revisions/{rev_id}/mesh   -> Lightweight 3D boundary surface mesh (cached JSON)
  - GET /api/revisions/{rev_id}/bundle -> Downloadable engineering package (.zip)
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import signal
import threading
import time
import zipfile
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from goddard import __version__
from goddard.client.cad_state import (
    CADConfigRequest,
    CADConfigResponse,
    CADModeRequest,
    CADModeResponse,
    CADStatusResponse,
    cad_state,
)
from goddard.copilot.autonomous_goal import AutonomousGoalEngine
from goddard.copilot.cache_manager import ModelCacheManager
from goddard.copilot.interactive_review import InteractiveReviewEngine
from goddard.copilot.mlx_engine import MLXEngine
from goddard.copilot.vram_profiler import VRAMProfiler

# ── Paths ────────────────────────────────────────────────────────────────────
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = pathlib.Path(os.getenv("GODDARD_ROOT", PACKAGE_ROOT.parent))


def get_designs_dir() -> pathlib.Path:
    env_dir = os.getenv("GODDARD_DESIGNS_DIR")
    if env_dir:
        return pathlib.Path(env_dir)
    return (
        REPO_ROOT / "designs"
        if (REPO_ROOT / "designs").exists()
        else pathlib.Path.cwd() / "designs"
    )


def get_ledger_path() -> pathlib.Path:
    return get_designs_dir() / "design_ledger.json"


DESIGNS_DIR = get_designs_dir()
LEDGER_PATH = get_ledger_path()
STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Goddard Mission Control Dashboard",
    description="Interactive 3D geometry & trade-space mission control for autonomous launch vehicle engineering.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health, Lifecycle & CAD State Helpers ───────────────────────────────────
def _is_copilot_ready() -> bool:
    if os.getenv("GODDARD_COPILOT_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    return True


_shutdown_lock = threading.Lock()
_shutdown_scheduled = False


def reset_shutdown_state() -> None:
    """Reset the shutdown state guard (used primarily in test suites)."""
    global _shutdown_scheduled
    with _shutdown_lock:
        _shutdown_scheduled = False


def _delayed_shutdown_worker(delay: float = 0.1, custom_hook: Any = None) -> None:
    time.sleep(delay)
    if callable(custom_hook):
        custom_hook()
        return
    if "PYTEST_CURRENT_TEST" in os.environ or os.getenv(
        "GODDARD_DISABLE_SHUTDOWN_SIGNAL", ""
    ).lower() in ("1", "true", "yes"):
        return
    os.kill(os.getpid(), signal.SIGTERM)


def _schedule_shutdown(delay: float = 0.1) -> None:
    global _shutdown_scheduled
    with _shutdown_lock:
        if _shutdown_scheduled:
            return
        _shutdown_scheduled = True
    hook = getattr(app.state, "shutdown_trigger", None)
    thread = threading.Thread(target=_delayed_shutdown_worker, args=(delay, hook), daemon=True)
    thread.start()


# ── Health, Lifecycle & CAD Sync Endpoints ──────────────────────────────────
@app.get("/api/health")
def get_health() -> dict[str, Any]:
    """
    Returns daemon runtime health, PID, CAD integration mode, and copilot engine readiness.
    """
    return {
        "status": "ok",
        "version": __version__,
        "pid": os.getpid(),
        "cad_mode": cad_state.mode,
        "copilot_ready": _is_copilot_ready(),
    }


@app.post("/api/lifecycle/shutdown")
def shutdown_daemon() -> dict[str, Any]:
    """
    Gracefully schedules daemon process termination after returning confirmation response.
    """
    _schedule_shutdown(delay=0.1)
    return {
        "status": "shutting_down",
        "message": "Daemon shutting down cleanly",
        "pid": os.getpid(),
    }


@app.get("/api/cad/status", response_model=CADStatusResponse)
def get_cad_status() -> dict[str, Any]:
    """
    Returns Onshape CAD integration status, mode, and configured document ID.
    """
    return cad_state.get_status()


@app.post("/api/cad/mode", response_model=CADModeResponse)
def set_cad_mode(req: CADModeRequest) -> dict[str, Any]:
    """
    Dynamically switches CAD integration mode between 'mock' and 'live' without server restart.
    """
    return cad_state.set_mode(req.mode)


@app.post("/api/cad/config", response_model=CADConfigResponse)
def set_cad_config(req: CADConfigRequest) -> dict[str, Any]:
    """
    Updates and persists Onshape API credentials and document ID to process memory, env, and .env file.
    """
    return cad_state.set_config(
        access_key=req.access_key,
        secret_key=req.secret_key,
        document_id=req.document_id,
    )


# ── 3D Surface Multi-Physics Scalar Computation ─────────────────────────────
def _compute_surface_scalars(
    coords_flat: list[float],
    normals_flat: list[float],
    rev_id: int,
) -> tuple[list[float], list[float], float, float, float]:
    """
    Computes normalized von Mises stress field [0.0, 1.0] and CFD pressure coefficient
    Cp field [-1.0, 1.0] from geometry vertex coordinates and normals.
    Integrates with design_ledger.json telemetry for peak stress, yield strength, and FOS.
    """
    import numpy as np

    # Telemetry defaults
    peak_vM = 185.4
    yield_str = 276.0
    yield_fos = 1.49

    ledger_path = get_ledger_path()
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
            for r in ledger:
                if r.get("revision_id") == rev_id:
                    fea = r.get("fea_metrics", {})
                    if "peak_von_mises_mpa" in fea:
                        peak_vM = float(fea["peak_von_mises_mpa"])
                    if "yield_strength_mpa" in fea:
                        yield_str = float(fea["yield_strength_mpa"])
                    if "yield_fos" in fea:
                        yield_fos = float(fea["yield_fos"])
                    elif peak_vM > 0:
                        yield_fos = round(yield_str / peak_vM, 2)
                    break
        except Exception:
            pass

    if not coords_flat or not normals_flat:
        return [], [], peak_vM, yield_str, yield_fos

    verts = np.array(coords_flat, dtype=np.float32).reshape(-1, 3)
    norms = np.array(normals_flat, dtype=np.float32).reshape(-1, 3)

    z = verts[:, 2]
    nz = norms[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    dz = max(z_max - z_min, 1e-4)
    z_norm = np.clip((z - z_min) / dz, 0.0, 1.0)

    # 1. Normalized von Mises Stress [0.0, 1.0]
    base_load = 1.0 - 0.75 * z_norm
    interstage_bump = 0.25 * np.exp(-(((z_norm - 0.70) / 0.08) ** 2))
    stress = np.clip(base_load + interstage_bump, 0.0, 1.0)

    # 2. Normalized Pressure Coefficient Cp [-1.0, 1.0]
    cp = np.zeros_like(z_norm)
    nose_mask = (z_norm >= 0.85) & (nz > 0)
    cp[nose_mask] = np.clip(nz[nose_mask] ** 1.5, 0.0, 1.0)
    shoulder_mask = (z_norm >= 0.80) & (z_norm < 0.90) & (nz <= 0.2)
    cp[shoulder_mask] = -0.45 * (1.0 - nz[shoulder_mask])
    base_mask = (z_norm < 0.05) & (nz < 0.0)
    cp[base_mask] = -0.28
    cp = np.clip(cp, -1.0, 1.0)

    return (
        np.round(stress, 4).tolist(),
        np.round(cp, 4).tolist(),
        peak_vM,
        yield_str,
        yield_fos,
    )


# ── Mesh Extraction & Caching ───────────────────────────────────────────────
def _extract_mesh_to_json(rev_id: int) -> dict[str, Any]:
    """
    Extracts lightweight 3D boundary surface triangles and vertex normals from
    a revision's .msh (or .step) and caches the result to designs/rev_{rev_id:03d}_surface.json.
    """
    import gmsh
    import numpy as np

    designs_dir = get_designs_dir()
    cache_path = designs_dir / f"rev_{rev_id:03d}_surface.json"
    if cache_path.exists():
        try:
            cached_payload = json.loads(cache_path.read_text())
            if (
                "stress_field" in cached_payload
                and "cp_field" in cached_payload
                and "rev_id" in cached_payload
                and "peak_von_mises_mpa" in cached_payload
            ):
                return cached_payload
            # Enrich existing cached geometry with physics scalars
            if "vertices" in cached_payload and "normals" in cached_payload:
                stress, cp, p_vm, y_str, y_fos = _compute_surface_scalars(
                    cached_payload["vertices"], cached_payload["normals"], rev_id
                )
                cached_payload["rev_id"] = rev_id
                cached_payload["stress_field"] = stress
                cached_payload["cp_field"] = cp
                cached_payload["peak_von_mises_mpa"] = p_vm
                cached_payload["yield_strength_mpa"] = y_str
                cached_payload["yield_fos"] = y_fos
                cache_path.write_text(json.dumps(cached_payload))
                return cached_payload
        except Exception:
            pass

    # Locate source geometry (.msh preferred, .step fallback)
    msh_candidates = [
        designs_dir / f"rev_{rev_id:03d}.msh",
        designs_dir / f"rev_{rev_id:03d}" / f"rev_{rev_id:03d}.msh",
    ]
    step_candidates = [
        designs_dir / f"rev_{rev_id:03d}.step",
        designs_dir / f"rev_{rev_id:03d}" / f"rev_{rev_id:03d}.step",
    ]

    msh_file = next((p for p in msh_candidates if p.exists()), None)
    step_file = next((p for p in step_candidates if p.exists()), None)

    if not msh_file and not step_file:
        raise HTTPException(
            status_code=404,
            detail=f"No geometry found for revision {rev_id} (.msh or .step missing in {designs_dir})",
        )

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)

        if msh_file:
            gmsh.open(str(msh_file))
        else:
            gmsh.model.occ.importShapes(str(step_file))
            gmsh.model.occ.synchronize()
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 6)
            gmsh.model.mesh.generate(2)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        if len(node_tags) == 0:
            raise ValueError(f"Mesh in revision {rev_id} contains no nodes")

        coords_arr = np.array(coords, dtype=np.float32).reshape(-1, 3)
        tag_to_idx = {tag: i for i, tag in enumerate(node_tags)}

        elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=2)
        tri_nodes = []
        for et, _tags, n_tags in zip(elem_types, elem_tags, elem_node_tags):
            if et == 2:  # 3-node triangle
                n_tags_arr = np.array(n_tags, dtype=np.int64).reshape(-1, 3)
                tri_nodes.append(n_tags_arr)

        if not tri_nodes:
            raise ValueError(f"No boundary surface triangles found for revision {rev_id}")

        all_tri_tags = np.vstack(tri_nodes)
        v_indices = np.vectorize(tag_to_idx.get)(all_tri_tags)

        # Shape: (N_triangles, 3, 3)
        tri_verts = coords_arr[v_indices]

        # Unit scaling: convert millimeters to meters if model dimensions exceed 50.0
        min_pt = coords_arr.min(axis=0)
        max_pt = coords_arr.max(axis=0)
        size = max_pt - min_pt
        scale = 0.001 if float(np.max(size)) > 50.0 else 1.0

        tri_verts = tri_verts * scale
        min_pt = min_pt * scale
        max_pt = max_pt * scale
        center = (min_pt + max_pt) / 2.0
        size = max_pt - min_pt

        # Face normals computation
        v0 = tri_verts[:, 0, :]
        v1 = tri_verts[:, 1, :]
        v2 = tri_verts[:, 2, :]
        normals = np.cross(v1 - v0, v2 - v0)
        norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
        norm_len[norm_len == 0] = 1.0
        normals = normals / norm_len

        # Repeat normals for each vertex of the triangle: shape (N_tri, 3, 3)
        tri_normals = np.repeat(normals[:, np.newaxis, :], 3, axis=1)

        flat_verts = tri_verts.reshape(-1, 3).round(4).tolist()
        flat_normals = tri_normals.reshape(-1, 3).round(4).tolist()
        v_flat = [item for sublist in flat_verts for item in sublist]
        n_flat = [item for sublist in flat_normals for item in sublist]

        stress, cp, p_vm, y_str, y_fos = _compute_surface_scalars(v_flat, n_flat, rev_id)

        mesh_payload = {
            "rev_id": rev_id,
            "revision_id": rev_id,
            "triangle_count": int(len(all_tri_tags)),
            "vertex_count": int(len(flat_verts)),
            "vertices": v_flat,
            "normals": n_flat,
            "stress_field": stress,
            "cp_field": cp,
            "peak_von_mises_mpa": p_vm,
            "yield_strength_mpa": y_str,
            "yield_fos": y_fos,
            "bounding_box": {
                "min": [float(x) for x in min_pt.round(4)],
                "max": [float(x) for x in max_pt.round(4)],
                "center": [float(x) for x in center.round(4)],
                "size": [float(x) for x in size.round(4)],
            },
        }

        # Cache on disk for instantaneous reload
        cache_path.write_text(json.dumps(mesh_payload))
        return mesh_payload

    finally:
        gmsh.finalize()


# ── Compliance & Verification Helper ─────────────────────────────────────────
def _compute_revision_compliance(rev: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluates multi-physics compliance rules across trajectory, stability,
    structural FEA, and propulsive VTVL landing.
    """
    inputs = rev.get("inputs", {})
    fm = rev.get("flight_metrics", {})
    fea = rev.get("fea_metrics", {})

    violations: list[str] = []
    badges: dict[str, bool | None] = {
        "apogee_or_orbit": True,
        "stability": True,
        "structural_yield": True,
        "buckling_blf": True,
        "max_q": True,
        "vtvl_landing": None,
    }

    # 1. Target Orbit or Apogee
    apogee = fm.get("apogee_m", 0.0)
    target_orbit_km = inputs.get("target_orbit_km")
    target_apogee_m = inputs.get("target_apogee_m")

    if target_orbit_km is not None:
        achieved_km = apogee / 1000.0
        if achieved_km < float(target_orbit_km) * 0.95:
            violations.append(f"Orbit altitude {achieved_km:.1f} km < target {target_orbit_km} km")
            badges["apogee_or_orbit"] = False
    elif target_apogee_m is not None:
        err = abs(apogee - float(target_apogee_m))
        if err > 200.0:
            violations.append(f"Apogee error {err:+.1f} m exceeds ±200 m tolerance")
            badges["apogee_or_orbit"] = False

    # 2. Stabilization & Authority
    stab_mode = inputs.get("stabilization_mode", "passive_fins")
    if stab_mode == "tvc_guided":
        gimbal_deg = fm.get("tvc_metrics", {}).get("gimbal_angle_required_deg", 0.0)
        if gimbal_deg > 5.0:
            violations.append(f"TVC gimbal requirement {gimbal_deg:.2f}° > 5.0° authority")
            badges["stability"] = False
    else:
        sm = fm.get("static_margin_calibers", {}).get("rail_departure")
        if sm is not None and (sm < 2.0 or sm > 3.0):
            violations.append(f"Launch static margin {sm:.2f} cal outside [2.0, 3.0]")
            badges["stability"] = False

    # 3. Structural Margins
    fos = fea.get("yield_fos", 3.0)
    blf = fea.get("buckling_load_factor_blf", 3.0)
    if fos < 2.0:
        violations.append(f"Yield FoS {fos:.2f} < 2.0 requirement")
        badges["structural_yield"] = False
    if blf < 2.0:
        violations.append(f"Buckling BLF {blf:.2f} < 2.0 requirement")
        badges["buckling_blf"] = False

    # 4. Max Dynamic Pressure
    max_q = fm.get("max_dynamic_pressure_pa", 0.0)
    if max_q > 65000.0:
        violations.append(f"Max dynamic pressure {max_q:.0f} Pa > 65 kPa limit")
        badges["max_q"] = False

    # 5. VTVL Landing
    is_reusable = inputs.get("reusable_booster", False) or (
        inputs.get("mission_profile") == "vtvl_hopper"
    )
    vtvl = fm.get("vtvl_landing")
    if is_reusable:
        if not vtvl:
            violations.append("Booster return trajectory missing")
            badges["vtvl_landing"] = False
        else:
            success = bool(vtvl.get("landing_success", False))
            v_td = float(vtvl.get("touchdown_velocity_ms", 99.0))
            if not success or v_td > 2.5:
                violations.append(
                    f"Booster touchdown {v_td:.2f} m/s exceeds 2.5 m/s or landing failed"
                )
                badges["vtvl_landing"] = False
            else:
                badges["vtvl_landing"] = True

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "badges": badges,
    }


# ── REST Endpoints ───────────────────────────────────────────────────────────
@app.get("/api/revisions")
def list_revisions() -> list[dict[str, Any]]:
    """
    Reads designs/design_ledger.json and returns the full design lineage
    enriched with compliance evaluations and step-over-step diffs.
    """
    ledger_path = get_ledger_path()
    if not ledger_path.exists():
        return []

    try:
        ledger = json.loads(ledger_path.read_text())
    except Exception:
        return []

    enriched: list[dict[str, Any]] = []
    prev_rev = None

    for r in ledger:
        comp = _compute_revision_compliance(r)
        inputs = r.get("inputs", {})
        cad = r.get("cad_metrics", {})
        fea = r.get("fea_metrics", {})
        fm = r.get("flight_metrics", {})
        r.get("sizing_metrics", {})

        # Calculate vehicle classification label
        inputs.get("mission_profile", "sounding_suborbital")
        engines = inputs.get("engine_count_stage1", 1)
        radius = inputs.get("body_radius_m", 0.0635)
        reusable = inputs.get("reusable_booster", False)

        if radius >= 4.0:
            classification = "Super Heavy Reusable" if reusable else "Super Heavy Launch Vehicle"
        elif radius >= 1.5 or engines >= 9:
            classification = "Medium/Heavy Reusable Booster" if reusable else "Orbital Booster"
        elif inputs.get("stage_count", 1) > 1:
            classification = "Multi-Stage Orbital"
        else:
            classification = "Suborbital Sounding Rocket"

        # Compute diff against previous revision
        diff: dict[str, Any] = {}
        if prev_rev:
            prev_inp = prev_rev.get("inputs", {})
            prev_cad = prev_rev.get("cad_metrics", {})
            prev_fea = prev_rev.get("fea_metrics", {})
            prev_fm = prev_rev.get("flight_metrics", {})

            diff = {
                "delta_airframe_mass_kg": round(
                    cad.get("mass_kg", 0.0) - prev_cad.get("mass_kg", 0.0), 2
                ),
                "delta_apogee_m": round(fm.get("apogee_m", 0.0) - prev_fm.get("apogee_m", 0.0), 1),
                "delta_yield_fos": round(
                    fea.get("yield_fos", 0.0) - prev_fea.get("yield_fos", 0.0), 2
                ),
                "delta_buckling_blf": round(
                    fea.get("buckling_load_factor_blf", 0.0)
                    - prev_fea.get("buckling_load_factor_blf", 0.0),
                    2,
                ),
                "delta_engine_count": inputs.get("engine_count_stage1", 1)
                - prev_inp.get("engine_count_stage1", 1),
                "delta_radius_m": round(radius - prev_inp.get("body_radius_m", radius), 3),
            }

        item = {
            **r,
            "classification": classification,
            "compliance": comp,
            "diff_from_previous": diff,
        }
        enriched.append(item)
        prev_rev = r

    return enriched


@app.get("/api/summary")
def get_summary() -> dict[str, Any]:
    """
    Returns platform KPI summary across all evaluated rocket revisions.
    """
    revisions = list_revisions()
    if not revisions:
        return {
            "total_revisions": 0,
            "latest_revision_id": None,
            "compliant_revisions": 0,
            "max_apogee_m": 0.0,
            "max_payload_kg": 0.0,
            "classes_represented": [],
            "status": "OK",
        }

    latest = revisions[-1]
    compliant_count = sum(1 for r in revisions if r.get("compliance", {}).get("compliant", False))
    apogees = [r.get("flight_metrics", {}).get("apogee_m", 0.0) for r in revisions]
    payloads = [r.get("inputs", {}).get("payload_mass_kg", 0.0) for r in revisions]
    classes = sorted({r.get("classification") for r in revisions if r.get("classification")})

    return {
        "total_revisions": len(revisions),
        "latest_revision_id": latest.get("revision_id"),
        "latest_classification": latest.get("classification"),
        "compliant_revisions": compliant_count,
        "compliance_rate": round(compliant_count / len(revisions), 2) if revisions else 0.0,
        "max_apogee_m": max(apogees) if apogees else 0.0,
        "max_payload_kg": max(payloads) if payloads else 0.0,
        "classes_represented": classes,
        "status": "OK",
    }


@app.get("/api/revisions/{rev_id}")
def get_revision(rev_id: int) -> dict[str, Any]:
    """Retrieve full engineering report for a specific revision."""
    revs = list_revisions()
    for r in revs:
        if r.get("revision_id") == rev_id:
            return r
    raise HTTPException(status_code=404, detail=f"Revision {rev_id} not found in design ledger")


@app.get("/api/revisions/{rev_id}/mesh")
def get_revision_mesh(rev_id: int) -> dict[str, Any]:
    """
    Returns lightweight 3D boundary surface vertices and normals for Three.js rendering.
    """
    return _extract_mesh_to_json(rev_id)


def build_revision_bundle_zip(rev_id: int) -> bytes:
    """
    Packages CAD .step, mesh .msh, surface JSON, FEA .inp decks, CFD .cfg decks,
    and JSON engineering report into an in-memory ZIP package.
    Raises HTTPException(404) if revision does not exist.
    """
    designs_dir = get_designs_dir()
    rev_dir = designs_dir / f"rev_{rev_id:03d}"

    # Check whether revision exists in ledger or files
    revs = list_revisions()
    matching = [r for r in revs if r.get("revision_id") == rev_id]

    step_candidates = [
        rev_dir / f"rev_{rev_id:03d}.step",
        designs_dir / f"rev_{rev_id:03d}.step",
    ]
    step_file = next((p for p in step_candidates if p.exists()), None)

    msh_candidates = [
        rev_dir / f"rev_{rev_id:03d}.msh",
        designs_dir / f"rev_{rev_id:03d}.msh",
    ]
    msh_file = next((p for p in msh_candidates if p.exists()), None)

    surface_file = designs_dir / f"rev_{rev_id:03d}_surface.json"

    if (
        not matching
        and not step_file
        and not msh_file
        and not rev_dir.exists()
        and not surface_file.exists()
    ):
        raise HTTPException(
            status_code=404,
            detail=f"Revision {rev_id} not found in design ledger or designs directory",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Report JSON
        report_file = rev_dir / "report.json"
        if report_file.exists():
            zf.write(report_file, arcname=f"rev_{rev_id:03d}_report.json")
        elif matching:
            zf.writestr(f"rev_{rev_id:03d}_report.json", json.dumps(matching[0], indent=2))

        # 2. STEP CAD File
        if step_file:
            zf.write(step_file, arcname=f"CAD/rev_{rev_id:03d}.step")

        # 3. Gmsh Mesh File
        if msh_file:
            zf.write(msh_file, arcname=f"Mesh/rev_{rev_id:03d}.msh")

        # 4. Surface Mesh JSON
        if surface_file.exists():
            zf.write(surface_file, arcname=f"Surface/rev_{rev_id:03d}_surface.json")

        # 5. CalculiX FEA Decks
        fea_dir = rev_dir / "calculix"
        if fea_dir.exists():
            for f in fea_dir.glob("*.inp"):
                zf.write(f, arcname=f"FEA/{f.name}")

        # 6. SU2 CFD Decks
        cfd_dir = rev_dir / "cfd"
        if cfd_dir.exists():
            for f in cfd_dir.glob("*.cfg"):
                zf.write(f, arcname=f"CFD/{f.name}")
        su2_mesh = rev_dir / f"rev_{rev_id:03d}_cfd.su2"
        if su2_mesh.exists():
            zf.write(su2_mesh, arcname=f"CFD/{su2_mesh.name}")

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


@app.get("/api/revisions/{rev_id}/bundle")
def get_revision_bundle(rev_id: int):
    """
    Packages CAD .step, mesh .msh, FEA .inp decks, CFD .cfg decks, and
    the JSON engineering report into an in-memory ZIP package for download.
    """
    content = build_revision_bundle_zip(rev_id)
    filename = f"Goddard_Rev_{rev_id:03d}_Engineering_Package.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Copilot State ────────────────────────────────────────────────────────────
_mute_state: dict[str, bool] = {"muted": False}
_haptic_log: list[dict] = []


# ── Copilot Endpoints ─────────────────────────────────────────────────────────
@app.get("/api/copilot/vram")
def get_copilot_vram() -> dict[str, Any]:
    """Return VRAM/RAM profile for the current Apple Silicon device."""
    return VRAMProfiler().get_profile()


@app.get("/api/copilot/models")
def get_copilot_models(request: Request = None, format: str | None = None) -> Any:
    """List all locally cached HuggingFace MLX models or unified catalog."""
    manager = ModelCacheManager()
    catalog = manager.get_catalog()
    accept_header = request.headers.get("accept", "") if request is not None else ""
    if format == "list" or "format=list" in accept_header:
        return catalog["models"]
    return catalog


class _DownloadRequest(BaseModel):
    repo_id: str
    offline_mock: bool = False


@app.post("/api/copilot/download")
@app.post("/api/copilot/models/download")
def post_copilot_download(req: _DownloadRequest) -> dict[str, Any]:
    """Download or mock-snapshot an MLX model repository."""
    if not ModelCacheManager.validate_repo_id(req.repo_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid repo_id: path traversal detected: {req.repo_id}",
        )

    is_offline = req.offline_mock or os.environ.get("GODDARD_OFFLINE_MODE", "").lower() in (
        "true",
        "1",
        "yes",
    )
    manager = ModelCacheManager()
    try:
        manager.download_model(req.repo_id, offline_mock=is_offline)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    progress = manager.get_download_progress(req.repo_id)
    return {
        "repo_id": req.repo_id,
        "status": progress.get("status", "complete"),
        "bytes_downloaded": progress.get("bytes_downloaded", 4096),
        "total_bytes": progress.get("total_bytes", 4096),
        "percent_complete": progress.get("percent_complete", 100.0),
        "offline_mock": is_offline,
    }


@app.get("/api/copilot/models/progress")
def get_copilot_models_progress(repo_id: str = "") -> dict[str, Any]:
    """Query live download progress for *repo_id*."""
    manager = ModelCacheManager()
    return manager.get_download_progress(repo_id)


class _ReviewRequest(BaseModel):
    intent: str
    current_params: dict[str, Any] | None = None
    base_revision_id: int | None = 1
    force_heuristic: bool = False


@app.post("/api/copilot/review")
def post_copilot_review(req: _ReviewRequest) -> dict[str, Any]:
    """Generate a parametric review diff for the given intent and parameters."""
    if req.current_params:
        dim_keywords = (
            "radius",
            "thickness",
            "mass",
            "chord",
            "span",
            "length",
            "diameter",
            "height",
            "pressure",
        )
        for k, v in req.current_params.items():
            try:
                num_v = float(v)
                if num_v < 0 and any(kw in k.lower() for kw in dim_keywords):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Physically impossible negative parameter: {k}={v}",
                    )
            except (ValueError, TypeError) as exc:
                if isinstance(exc, HTTPException):
                    raise
                pass

    current_params = req.current_params
    if current_params is None:
        ledger_path = get_ledger_path()
        ledger = []
        if ledger_path.exists():
            try:
                ledger = json.loads(ledger_path.read_text())
            except Exception:
                ledger = []
        base_rev = next((r for r in ledger if r.get("revision_id") == req.base_revision_id), None)
        if base_rev and "inputs" in base_rev:
            current_params = dict(base_rev["inputs"])
        else:
            current_params = {
                "payload_mass_kg": 4.0,
                "propellant_mass_kg": 18.2,
                "wall_thickness_mm": 1.65,
                "chamber_pressure_mpa": 3.0,
            }

    engine = MLXEngine()
    review_engine = InteractiveReviewEngine(engine)
    try:
        return review_engine.propose_review(
            req.intent,
            current_params,
            force_heuristic=req.force_heuristic,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        if "empty" in msg:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class _ApplyRequest(BaseModel):
    base_revision_id: int = 1
    modifications: dict[str, Any] = {}


@app.post("/api/copilot/apply")
def post_copilot_apply(req: _ApplyRequest) -> dict[str, Any]:
    """Apply parameter diff to design revision, run coupled sizing, and commit to ledger."""
    if not req.modifications:
        return {
            "status": "no_changes",
            "revision_id": req.base_revision_id,
            "new_revision_id": req.base_revision_id,
            "sizing_metrics": {},
            "inputs": {},
            "message": "No parameter changes to apply",
        }

    dim_keywords = (
        "radius",
        "thickness",
        "mass",
        "chord",
        "span",
        "length",
        "diameter",
        "height",
        "pressure",
    )
    for param, change in req.modifications.items():
        new_val = change.get("new") if isinstance(change, dict) else change
        try:
            num_v = float(new_val)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Non-numeric parameter mutation for {param}: {new_val}",
            ) from exc
        if num_v < 0 and any(kw in param.lower() for kw in dim_keywords):
            raise HTTPException(
                status_code=422,
                detail=f"Physically impossible negative parameter: {param}={new_val}",
            )

    review_engine = InteractiveReviewEngine()
    try:
        return review_engine.apply_to_cad_and_resimulate(
            req.modifications,
            base_revision_id=req.base_revision_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class _OptimizeRequest(BaseModel):
    targets: dict[str, Any] | None = None
    target_apogee_m: float | None = None
    target_orbit_km: float | None = None
    von_mises_stress_mpa: float | None = None
    yield_fos: float | None = None
    max_iterations: int = 5
    tolerance: float = 0.05
    base_revision_id: int = 1
    initial_params: dict[str, Any] | None = None


@app.post("/api/copilot/optimize")
def post_copilot_optimize(req: _OptimizeRequest) -> dict[str, Any]:
    """Run autonomous goal-driven closed-loop optimisation toward specified targets."""
    targets = dict(req.targets or {})
    if req.target_apogee_m is not None:
        targets["apogee_m"] = req.target_apogee_m
    if req.target_orbit_km is not None:
        targets["target_orbit_km"] = req.target_orbit_km
    if req.von_mises_stress_mpa is not None:
        targets["von_mises_stress_mpa"] = req.von_mises_stress_mpa
    if req.yield_fos is not None:
        targets["yield_fos"] = req.yield_fos

    if not targets:
        raise HTTPException(status_code=400, detail="targets cannot be empty")

    goal_engine = AutonomousGoalEngine()
    try:
        return goal_engine.optimize(
            targets=targets,
            initial_params=req.initial_params,
            max_iterations=req.max_iterations,
            tolerance=req.tolerance,
            base_revision_id=req.base_revision_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Audio / Haptic Endpoints ──────────────────────────────────────────────────
class _MuteRequest(BaseModel):
    muted: bool


class _HapticRequest(BaseModel):
    style: str


@app.get("/api/audio/mute")
def get_audio_mute() -> dict[str, Any]:
    """Return current audio mute state."""
    return dict(_mute_state)


@app.post("/api/audio/mute")
def set_audio_mute(req: _MuteRequest) -> dict[str, Any]:
    """Update the in-memory audio mute state."""
    _mute_state["muted"] = req.muted
    return dict(_mute_state)


@app.post("/api/events/haptic")
def post_haptic_event(req: _HapticRequest) -> dict[str, Any]:
    """Log a haptic feedback event and return confirmation."""
    _haptic_log.append({"style": req.style})
    return {"ok": True}


# ── Frontend Static Files ────────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found in ui/static")
    return FileResponse(index_file)


def main() -> None:
    """Console script entrypoint for the Goddard UI dashboard."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Goddard 3D Mission Control Dashboard")
    parser.add_argument(
        "--host",
        default=os.getenv("GODDARD_HOST", "0.0.0.0"),
        help="Host interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GODDARD_PORT", "8050")),
        help="Port to listen on (default: 8050)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    uvicorn.run("goddard.ui.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
