"""
STEP-to-Mesh validator using the Gmsh Python API.

Imports an Onshape-exported .step file via OpenCASCADE, generates a 3D
tetrahedral mesh, computes quality diagnostics, and exports to .msh.
"""

from __future__ import annotations

import pathlib
from typing import Any


def mesh_step_file(
    step_path: str,
    output_msh_path: str,
    mesh_size_factor: float = 0.2,
) -> dict[str, Any]:
    """
    Import a STEP file, generate a 3D tetrahedral mesh, and export.

    Parameters
    ----------
    step_path : str
        Path to the input .step file.
    output_msh_path : str
        Path for the output .msh file.
    mesh_size_factor : float
        Fraction of the bounding-box diagonal used as the target mesh size.

    Returns
    -------
    dict with keys:
        status, volumes, surfaces, curves, points,
        bounding_box_m, dimensions_m,
        node_count, tet_count, min_quality, mean_quality,
        msh_path
    """
    import gmsh

    result: dict[str, Any] = {"status": "FAIL", "msh_path": None}

    step_path = str(pathlib.Path(step_path).resolve())
    output_msh_path = str(pathlib.Path(output_msh_path).resolve())

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)  # headless / quiet

        # ── Import STEP via OpenCASCADE ──────────────────────────────
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        # ── Entity counts ────────────────────────────────────────────
        volumes = gmsh.model.getEntities(dim=3)
        surfaces = gmsh.model.getEntities(dim=2)
        curves = gmsh.model.getEntities(dim=1)
        points = gmsh.model.getEntities(dim=0)

        result["volumes"] = len(volumes)
        result["surfaces"] = len(surfaces)
        result["curves"] = len(curves)
        result["points"] = len(points)

        # ── Bounding box ─────────────────────────────────────────────
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        result["bounding_box_m"] = {
            "xmin": xmin,
            "ymin": ymin,
            "zmin": zmin,
            "xmax": xmax,
            "ymax": ymax,
            "zmax": zmax,
        }
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        result["dimensions_m"] = {"dx": dx, "dy": dy, "dz": dz}

        d_ref = max(dx, dy)
        l_ref = max(dz, 0.1)

        # Scale-invariant adaptive sizing:
        # Prevents memory/runtime blowups on large orbital rockets (3.7m - 9.0m)
        # while keeping fine resolution on smaller sounding rockets (< 15,000 tets in fast mode).
        is_mm = d_ref > 50.0
        unit_scale = 1000.0 if is_mm else 1.0

        target_min = min(
            max(0.020 * unit_scale, (d_ref / unit_scale) * 0.015 * unit_scale), 0.150 * unit_scale
        )
        target_max = min(
            max(1.000 * unit_scale, (l_ref / unit_scale) * 0.035 * unit_scale), 5.0 * unit_scale
        )

        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 5)
        gmsh.option.setNumber("Mesh.MeshSizeMin", target_min)
        gmsh.option.setNumber("Mesh.MeshSizeMax", target_max)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_min)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_max)

        # ── Generate 3D tetrahedral mesh ─────────────────────────────
        gmsh.model.mesh.generate(3)

        # ── Node & element counts ────────────────────────────────────
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        result["node_count"] = len(node_tags)

        # Count only tetrahedra (element type 4)
        tet_count = 0
        for vol_dim, vol_tag in volumes:
            elem_types, elem_tags, _ = gmsh.model.mesh.getElements(vol_dim, vol_tag)
            for et, tags in zip(elem_types, elem_tags):
                if et == 4:  # 4-node tetrahedron
                    tet_count += len(tags)
        result["tet_count"] = tet_count

        # ── Mesh quality (minSICN / scaled Jacobian) ─────────────────
        try:
            qualities = gmsh.model.mesh.getElementQualities(
                list(range(1, tet_count + 1)), "minSICN"
            )
            if qualities:
                result["min_quality"] = float(min(qualities))
                result["mean_quality"] = float(sum(qualities) / len(qualities))
            else:
                result["min_quality"] = 0.0
                result["mean_quality"] = 0.0
        except Exception:
            # Fallback: get all element qualities without specifying tags
            try:
                all_elem_types, all_elem_tags, _ = gmsh.model.mesh.getElements()
                tet_tags = []
                for et, tags in zip(all_elem_types, all_elem_tags):
                    if et == 4:
                        tet_tags.extend(tags)
                if tet_tags:
                    qualities = gmsh.model.mesh.getElementQualities(tet_tags, "minSICN")
                    result["min_quality"] = float(min(qualities))
                    result["mean_quality"] = float(sum(qualities) / len(qualities))
                else:
                    result["min_quality"] = 0.0
                    result["mean_quality"] = 0.0
            except Exception:
                result["min_quality"] = 0.0
                result["mean_quality"] = 0.0

        # ── Export ───────────────────────────────────────────────────
        gmsh.write(output_msh_path)
        result["msh_path"] = output_msh_path
        result["status"] = "OK"

    finally:
        gmsh.finalize()

    return result


def build_cfd_farfield_mesh(
    step_path: str,
    output_su2_path: str,
    domain_scale: float = 3.0,
) -> dict[str, Any]:
    """
    Generate an external aerodynamic flow domain around the rocket STEP geometry,
    tag physical boundaries (rocket_wall, farfield, fluid), and export in .su2 format.

    Parameters
    ----------
    step_path : str
        Path to input rocket .step geometry.
    output_su2_path : str
        Path for the exported .su2 CFD mesh.
    domain_scale : float
        Multiplicative factor for the external domain dimensions relative to rocket bounding box.

    Returns
    -------
    dict with keys: status, su2_path, nodes, elements, rocket_wall_faces, farfield_faces
    """
    import gmsh

    step_path = str(pathlib.Path(step_path).resolve())
    output_su2_path = str(pathlib.Path(output_su2_path).resolve())
    result: dict[str, Any] = {"status": "FAIL", "su2_path": None}

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)

        # 1. Import rocket body via OpenCASCADE
        shapes = gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin

        # 2. Add external aerodynamic domain bounding box
        pad_x = dx * (domain_scale * 0.5)
        pad_y = dy * (domain_scale * 0.5)
        pad_z_up = dz * 0.8
        pad_z_down = dz * 0.4

        box = gmsh.model.occ.addBox(
            xmin - pad_x,
            ymin - pad_y,
            zmin - pad_z_down,
            dx + 2.0 * pad_x,
            dy + 2.0 * pad_y,
            dz + pad_z_up + pad_z_down,
        )
        gmsh.model.occ.synchronize()

        # 3. Boolean subtraction of rocket from fluid domain
        fluid_vols, _ = gmsh.model.occ.cut([(3, box)], shapes)
        gmsh.model.occ.synchronize()

        # 4. Classify boundary surfaces
        box_xmin = xmin - pad_x
        box_xmax = xmax + pad_x
        box_ymin = ymin - pad_y
        box_ymax = ymax + pad_y
        box_zmin = zmin - pad_z_down
        box_zmax = zmax + pad_z_up

        box_surfs = []
        wall_surfs = []
        for dim, s in gmsh.model.getEntities(2):
            s_xmin, s_ymin, s_zmin, s_xmax, s_ymax, s_zmax = gmsh.model.getBoundingBox(dim, s)
            tol = 1e-3
            is_farfield = (
                abs(s_xmin - box_xmin) < tol
                or abs(s_xmax - box_xmax) < tol
                or abs(s_ymin - box_ymin) < tol
                or abs(s_ymax - box_ymax) < tol
                or abs(s_zmin - box_zmin) < tol
                or abs(s_zmax - box_zmax) < tol
            )
            if is_farfield:
                box_surfs.append(s)
            else:
                wall_surfs.append(s)

        # 5. Tag SU2 physical boundary markers
        gmsh.model.addPhysicalGroup(2, wall_surfs, name="rocket_wall")
        gmsh.model.addPhysicalGroup(2, box_surfs, name="farfield")
        if fluid_vols:
            gmsh.model.addPhysicalGroup(3, [fluid_vols[0][1]], name="fluid")

        # 6. Sizing & Meshing (Scale-invariant)
        d_ref = max(dx, dy)
        l_ref = max(dz, 0.1)
        cfd_min = max(0.005, d_ref * 0.05)
        cfd_max = max(0.1, l_ref * 0.15)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 15)
        gmsh.option.setNumber("Mesh.MeshSizeMin", cfd_min)
        gmsh.option.setNumber("Mesh.MeshSizeMax", cfd_max)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", cfd_min)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", cfd_max)
        gmsh.model.mesh.generate(3)

        # 7. Write SU2 mesh
        gmsh.write(output_su2_path)

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        elem_types, elem_tags, _ = gmsh.model.mesh.getElements(3)
        total_tets = sum(len(tags) for tags in elem_tags)

        result["status"] = "OK"
        result["su2_path"] = output_su2_path
        result["node_count"] = len(node_tags)
        result["tet_count"] = total_tets
        result["rocket_wall_faces"] = len(wall_surfs)
        result["farfield_faces"] = len(box_surfs)

    finally:
        gmsh.finalize()

    return result


class RocketMesher:
    """Scale-invariant 3D tetrahedral and CFD farfield mesher."""

    @staticmethod
    def compute_adaptive_mesh_sizing(d_ref: float, l_ref: float) -> dict[str, float]:
        """
        Computes scale-invariant adaptive mesh sizing parameters.
        Prevents element explosion on large launch vehicles while retaining fidelity
        on subscale sounding rockets.
        """
        is_mm = d_ref > 50.0
        unit_scale = 1000.0 if is_mm else 1.0
        target_min = min(
            max(0.020 * unit_scale, (d_ref / unit_scale) * 0.015 * unit_scale), 0.150 * unit_scale
        )
        target_max = min(
            max(1.000 * unit_scale, (l_ref / unit_scale) * 0.035 * unit_scale), 5.0 * unit_scale
        )
        cfd_min = max(0.005 * unit_scale, (d_ref / unit_scale) * 0.05 * unit_scale)
        cfd_max = max(0.1 * unit_scale, (l_ref / unit_scale) * 0.15 * unit_scale)

        return {
            "target_min": float(target_min),
            "target_max": float(target_max),
            "cfd_min": float(cfd_min),
            "cfd_max": float(cfd_max),
            "unit_scale": unit_scale,
        }

    @staticmethod
    def mesh(
        step_path: str,
        output_msh_path: str,
        mesh_size_factor: float = 0.2,
    ) -> dict[str, Any]:
        return mesh_step_file(step_path, output_msh_path, mesh_size_factor)

    @staticmethod
    def mesh_cfd_farfield(
        step_path: str,
        output_su2_path: str,
        box_scale: float = 5.0,
    ) -> dict[str, Any]:
        return build_cfd_farfield_mesh(step_path, output_su2_path, box_scale)
