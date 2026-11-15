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
import zipfile
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
            return json.loads(cache_path.read_text())
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

        mesh_payload = {
            "revision_id": rev_id,
            "triangle_count": int(len(all_tri_tags)),
            "vertex_count": int(len(flat_verts)),
            "vertices": [item for sublist in flat_verts for item in sublist],
            "normals": [item for sublist in flat_normals for item in sublist],
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


@app.get("/api/revisions/{rev_id}/bundle")
def get_revision_bundle(rev_id: int):
    """
    Packages CAD .step, mesh .msh, FEA .inp decks, CFD .cfg decks, and
    the JSON engineering report into an in-memory ZIP package for download.
    """
    designs_dir = get_designs_dir()
    rev_dir = designs_dir / f"rev_{rev_id:03d}"
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Report JSON
        report_file = rev_dir / "report.json"
        if report_file.exists():
            zf.write(report_file, arcname=f"rev_{rev_id:03d}_report.json")
        else:
            # Fallback to ledger entry
            revs = list_revisions()
            matching = [r for r in revs if r.get("revision_id") == rev_id]
            if matching:
                zf.writestr(f"rev_{rev_id:03d}_report.json", json.dumps(matching[0], indent=2))

        # 2. STEP CAD File
        step_candidates = [
            rev_dir / f"rev_{rev_id:03d}.step",
            designs_dir / f"rev_{rev_id:03d}.step",
        ]
        step_file = next((p for p in step_candidates if p.exists()), None)
        if step_file:
            zf.write(step_file, arcname=f"CAD/rev_{rev_id:03d}.step")

        # 3. Gmsh Mesh File
        msh_candidates = [
            rev_dir / f"rev_{rev_id:03d}.msh",
            designs_dir / f"rev_{rev_id:03d}.msh",
        ]
        msh_file = next((p for p in msh_candidates if p.exists()), None)
        if msh_file:
            zf.write(msh_file, arcname=f"Mesh/rev_{rev_id:03d}.msh")

        # 4. CalculiX FEA Decks
        fea_dir = rev_dir / "calculix"
        if fea_dir.exists():
            for f in fea_dir.glob("*.inp"):
                zf.write(f, arcname=f"FEA/{f.name}")

        # 5. SU2 CFD Decks
        cfd_dir = rev_dir / "cfd"
        if cfd_dir.exists():
            for f in cfd_dir.glob("*.cfg"):
                zf.write(f, arcname=f"CFD/{f.name}")
        su2_mesh = rev_dir / f"rev_{rev_id:03d}_cfd.su2"
        if su2_mesh.exists():
            zf.write(su2_mesh, arcname=f"CFD/{su2_mesh.name}")

    zip_buffer.seek(0)
    filename = f"Goddard_Rev_{rev_id:03d}_Engineering_Package.zip"
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
