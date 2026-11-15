"""
Goddard Sizing & Requirements Engine.
Universal multi-stage rocket sizing, thermochemistry, and requirements gate.
"""

from goddard.sizing.coupled_wer import (
    COTS_PLATE_THICKNESSES_M,
    COTS_TUBE_ODS_M,
    COTS_TUBE_WALLS_M,
    MATERIAL_PROPERTIES,
    THERMOCHEM_DATA,
    compute_fin_flutter_velocity,
    compute_tvc_control_authority,
    run_coupled_sizing,
    size_single_stage,
    snap_to_cots,
)
from goddard.sizing.mission_spec import (
    VALID_DFM_MODES,
    VALID_FEED_ARCHITECTURES,
    VALID_LAUNCH_MODES,
    VALID_MATERIALS,
    VALID_MISSION_PROFILES,
    VALID_STABILIZATION_MODES,
    MissionSpec,
    evaluate_spec_completeness,
)

__all__ = [
    "MissionSpec",
    "evaluate_spec_completeness",
    "run_coupled_sizing",
    "size_single_stage",
    "snap_to_cots",
    "compute_fin_flutter_velocity",
    "compute_tvc_control_authority",
    "MATERIAL_PROPERTIES",
    "COTS_TUBE_ODS_M",
    "COTS_TUBE_WALLS_M",
    "COTS_PLATE_THICKNESSES_M",
    "THERMOCHEM_DATA",
    "VALID_MISSION_PROFILES",
    "VALID_STABILIZATION_MODES",
    "VALID_LAUNCH_MODES",
    "VALID_FEED_ARCHITECTURES",
    "VALID_MATERIALS",
    "VALID_DFM_MODES",
]
