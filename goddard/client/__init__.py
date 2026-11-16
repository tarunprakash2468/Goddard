"""
Goddard Onshape CAD Client package.
Provides real Onshape REST client, offline MockOnshapeClient, and centralized CAD state management.
"""

from goddard.client.cad_state import (
    CADConfigRequest,
    CADConfigResponse,
    CADModeRequest,
    CADModeResponse,
    CADStateManager,
    CADStatusResponse,
    cad_state,
)
from goddard.client.client import OnshapeAPIError, OnshapeClient, get_client
from goddard.client.mock import MockOnshapeClient

__all__ = [
    "OnshapeClient",
    "MockOnshapeClient",
    "OnshapeAPIError",
    "get_client",
    "cad_state",
    "CADStateManager",
    "CADStatusResponse",
    "CADModeRequest",
    "CADModeResponse",
    "CADConfigRequest",
    "CADConfigResponse",
]
