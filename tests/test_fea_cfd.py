"""
Unit and integration tests for FEA structural analysis, compressible CFD,
and scale-invariant mesh generation.
Verifies graceful fallbacks when solver binaries (ccx, SU2_CFD) are absent.
"""

from __future__ import annotations

import pathlib

from goddard.client.mock import MINIMAL_STEP_STRING
from goddard.sim.cfd_solver import CFDSolver, generate_su2_config
from goddard.sim.fea_solver import (
    FEASolver,
    evaluate_analytical_airframe_margins,
    generate_calculix_inp,
)
from goddard.sim.mesher import RocketMesher


class TestFEASolver:
    """Test suite for CalculiX FEA solver and analytical margin calculations."""

    def test_analytical_margin_evaluation(self) -> None:
        """Verify analytical von Mises stress, FoS, and NASA SP-8007 buckling calculation."""
        res = evaluate_analytical_airframe_margins(
            thrust_n=4500.0,
            max_q_drag_n=650.0,
            tank_pressure_pa=3.1e6,
            radius_m=0.0635,
            thickness_m=0.00165,
            length_m=1.75,
            structural_material="AL6061-T6",
        )

        assert res["status"] == "OK"
        assert res["solver_mode"] == "analytical_nasa_sp8007"
        assert res["yield_fos"] > 2.0
        assert res["buckling_load_factor_blf"] > 2.0
        assert res["stress_passed"] is True
        assert res["buckling_passed"] is True

    def test_fea_solver_deck_generation(self, tmp_path: pathlib.Path) -> None:
        """Verify CalculiX .inp input deck generation format and constraints."""
        inp_file = tmp_path / "test_fea.inp"
        nodes = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.0, 0.0, 0.5)]
        tets = [(1, 2, 3, 4)]
        path = generate_calculix_inp(
            inp_path=str(inp_file),
            node_coords=nodes,
            tet_elements=tets,
            base_node_ids=[1, 2, 3],
            top_node_ids=[4],
            thrust_compression_n=5000.0,
            internal_pressure_pa=3.0e6,
        )
        assert pathlib.Path(path).exists()
        content = inp_file.read_text()
        assert "*HEADING" in content
        assert "*ELEMENT, TYPE=C3D4" in content
        assert "*NSET, NSET=NBASE" in content
        assert "*CLOAD" in content

    def test_fea_solver_missing_binary_graceful_fallback(self, tmp_path: pathlib.Path) -> None:
        """Verify FEASolver returns synthetic analytical results when ccx binary is missing."""
        solver = FEASolver(ccx_bin="/nonexistent/path/to/ccx")
        dummy_msh = tmp_path / "dummy.msh"
        dummy_msh.write_text("$MeshFormat\n4.1 0 8\n$EndMeshFormat\n")

        res = solver.run(
            msh_path=str(dummy_msh),
            peak_thrust_n=4500.0,
            max_q_drag_n=650.0,
            tank_pressure_pa=3.1e6,
            recovery_snatch_n=1200.0,
            airframe_radius_m=0.0635,
            wall_thickness_m=0.00165,
            airframe_length_m=1.75,
            output_inp_path=str(tmp_path / "out.inp"),
        )

        assert res["status"] == "OK"
        assert res["solver_mode"] == "calculix_deck_verified_analytical"
        assert "yield_fos" in res
        assert "buckling_load_factor_blf" in res
        assert pathlib.Path(res["inp_path"]).exists()


class TestCFDSolver:
    """Test suite for SU2 compressible CFD configuration and aerodynamic sweeps."""

    def test_su2_config_generation(self, tmp_path: pathlib.Path) -> None:
        """Verify SU2 .cfg configuration generation with correct Euler solver options."""
        cfg_file = tmp_path / "test_flow.cfg"
        mesh_file = tmp_path / "flow.su2"
        cfg_path = generate_su2_config(
            cfg_path=str(cfg_file),
            mesh_path=str(mesh_file),
            mach=1.5,
            ref_area_m2=0.01267,
            ref_length_m=1.75,
            aoa_deg=2.0,
        )
        assert pathlib.Path(cfg_path).exists()
        content = cfg_file.read_text()
        assert "SOLVER= EULER" in content
        assert "MACH_NUMBER= 1.5000" in content
        assert "AOA= 2.00" in content
        assert "MARKER_EULER= ( rocket_wall )" in content
        assert "MARKER_FAR= ( farfield )" in content

    def test_analytical_aerodynamic_curves(self) -> None:
        """Verify transonic wave drag divergence and supersonic decay curve."""
        solver = CFDSolver()
        machs = [0.4, 0.85, 1.05, 1.5, 2.2]
        cd_curve, xcp_curve = solver.calculate_aerodynamics(machs)

        assert len(cd_curve) == 5
        assert len(xcp_curve) == 5
        # Transonic drag peak occurs around Mach 1.05
        assert cd_curve[2] > cd_curve[0]  # Mach 1.05 CD > Mach 0.40 CD
        assert cd_curve[2] > cd_curve[4]  # Mach 1.05 CD > Mach 2.20 CD (supersonic expansion decay)
        # Center of pressure shifts aft in supersonic regime
        assert xcp_curve[4] > xcp_curve[0]

    def test_cfd_solver_missing_binary_graceful_fallback(self, tmp_path: pathlib.Path) -> None:
        """Verify CFDSolver executes fallback analytical sweep without crashing when SU2_CFD is missing."""
        solver = CFDSolver(su2_bin="/nonexistent/path/to/SU2_CFD")
        mesh_file = tmp_path / "empty.su2"
        mesh_file.write_text("NDIME= 3\n")

        res = solver.run_mach_sweep(
            mesh_path=str(mesh_file),
            mach_numbers=[0.5, 1.1, 2.0],
            output_dir=str(tmp_path / "cfd_out"),
        )

        assert "analytical_compressible" in res["solver_mode"]
        assert len(res["cd_curve"]) == 3
        assert len(res["su2_configs_generated"]) == 3
        assert res["peak_drag_mach"] == 1.1


class TestRocketMesher:
    """Test suite for scale-invariant adaptive meshing and Gmsh 3D pipeline."""

    def test_adaptive_mesh_sizing_scale_invariance(self) -> None:
        """
        Verify adaptive mesh sizing prevents element count explosion on large
        orbital rockets (3.7m - 9.0m) while keeping fine resolution on sounding rockets.
        """
        # 1. Suborbital sounding rocket (D ~ 0.127m, L ~ 1.75m)
        bounds_sub = RocketMesher.compute_adaptive_mesh_sizing(0.127, 1.75)
        assert bounds_sub["unit_scale"] == 1.0
        assert bounds_sub["target_min"] >= 0.020  # Minimum gauge floor
        assert bounds_sub["target_max"] <= 1.000

        # 2. Medium orbital launcher (Falcon 9 class: D = 3.7m, L = 70m)
        bounds_orbital = RocketMesher.compute_adaptive_mesh_sizing(3.7, 70.0)
        assert bounds_orbital["unit_scale"] == 1.0
        assert bounds_orbital["target_min"] > bounds_sub["target_min"]
        assert (
            bounds_orbital["target_max"] <= 5.000
        )  # Strict upper bound to prevent coarse degeneration

        # 3. Super Heavy rocket (Starship class: D = 9.0m, L = 120m)
        bounds_heavy = RocketMesher.compute_adaptive_mesh_sizing(9.0, 120.0)
        assert bounds_heavy["target_min"] <= 0.150  # Upper clamp on target_min
        assert bounds_heavy["target_max"] <= 5.000

        # 4. Dimension given in millimeters (D = 127mm, L = 1750mm)
        bounds_mm = RocketMesher.compute_adaptive_mesh_sizing(127.0, 1750.0)
        assert bounds_mm["unit_scale"] == 1000.0
        assert bounds_mm["target_min"] == bounds_sub["target_min"] * 1000.0

    def test_mesh_generation_on_step(self, tmp_path: pathlib.Path) -> None:
        """Verify 3D tetrahedral meshing operates cleanly on synthetic STEP geometry."""
        step_file = tmp_path / "airframe.step"
        msh_file = tmp_path / "airframe.msh"
        step_file.write_text(MINIMAL_STEP_STRING)

        res = RocketMesher.mesh(
            step_path=str(step_file),
            output_msh_path=str(msh_file),
            mesh_size_factor=0.2,
        )

        assert res["status"] == "OK"
        assert res["volumes"] == 1
        assert res["node_count"] > 10
        assert res["tet_count"] > 10
        assert pathlib.Path(res["msh_path"]).exists()
