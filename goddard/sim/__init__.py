"""
Goddard Multiphysics Simulation Suite.
Includes Gmsh 3D/CFD meshing, RocketPy 6-DOF flight dynamics, CalculiX structural FEA,
SU2 compressible CFD, and VTVL booster landing simulation.
"""

from goddard.sim.cfd_solver import CFDSolver, generate_su2_config, run_cfd_mach_sweep
from goddard.sim.fea_solver import (
    FEASolver,
    evaluate_analytical_airframe_margins,
    generate_calculix_inp,
    run_structural_fea,
)
from goddard.sim.flight_sim import run_sounding_rocket_sim
from goddard.sim.mesher import RocketMesher, build_cfd_farfield_mesh, mesh_step_file
from goddard.sim.vtvl_landing import PropulsiveLandingSim, simulate_booster_landing

__all__ = [
    "FEASolver",
    "CFDSolver",
    "RocketMesher",
    "PropulsiveLandingSim",
    "mesh_step_file",
    "build_cfd_farfield_mesh",
    "run_sounding_rocket_sim",
    "run_structural_fea",
    "evaluate_analytical_airframe_margins",
    "generate_calculix_inp",
    "run_cfd_mach_sweep",
    "generate_su2_config",
    "simulate_booster_landing",
]
