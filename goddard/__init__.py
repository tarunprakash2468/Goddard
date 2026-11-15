"""
Goddard: Autonomous CAD-to-Physics Multi-Stage Rocket Design Suite.

Integrates parametric FeatureScript CAD generation (Onshape), automated tetrahedral meshing
(Gmsh), compressible aerodynamic CFD (SU2), structural finite element analysis (CalculiX),
6-DOF trajectory simulation (RocketPy), and closed-loop propulsive landing (VTVL) into a
unified engineering workflow with FastMCP and interactive 3D UI.
"""

__version__ = "0.1.0"

from goddard.client.client import OnshapeAPIError, OnshapeClient, get_client
from goddard.client.mock import MockOnshapeClient
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
from goddard.sizing.coupled_wer import (
    COTS_TUBE_ODS_M,
    MATERIAL_PROPERTIES,
    THERMOCHEM_DATA,
    run_coupled_sizing,
    size_single_stage,
)
from goddard.sizing.mission_spec import MissionSpec, evaluate_spec_completeness

__all__ = [
    "__version__",
    "OnshapeClient",
    "MockOnshapeClient",
    "OnshapeAPIError",
    "get_client",
    "MissionSpec",
    "evaluate_spec_completeness",
    "run_coupled_sizing",
    "size_single_stage",
    "MATERIAL_PROPERTIES",
    "COTS_TUBE_ODS_M",
    "THERMOCHEM_DATA",
    "RocketMesher",
    "FEASolver",
    "CFDSolver",
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
