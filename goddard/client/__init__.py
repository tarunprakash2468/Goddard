"""
Goddard Onshape CAD Client package.
Provides real Onshape REST client and offline MockOnshapeClient.
"""

from goddard.client.client import OnshapeAPIError, OnshapeClient, get_client
from goddard.client.mock import MockOnshapeClient

__all__ = [
    "OnshapeClient",
    "MockOnshapeClient",
    "OnshapeAPIError",
    "get_client",
]
