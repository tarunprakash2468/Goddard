"""
Reusable Onshape REST API client for Goddard Rocket CAD generation.

Uses API v6 at https://cad.onshape.com/api/v6 with HTTP Basic Auth
(ONSHAPE_ACCESS_KEY as username, ONSHAPE_SECRET_KEY as password).
Provides seamless fallback to MockOnshapeClient for offline testing or when credentials are unset.
"""

from __future__ import annotations

import os
import pathlib
import time
from typing import Any

import requests

from goddard.client.mock import MockOnshapeClient


class OnshapeAPIError(Exception):
    """Raised when an Onshape API call returns a non-2xx status."""

    def __init__(self, status_code: int, url: str, body: Any):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"Onshape API error {status_code} on {url}: {body}")


class OnshapeClient:
    """Thin wrapper around the Onshape v6 REST API."""

    BASE_URL = "https://cad.onshape.com/api/v6"

    def __new__(
        cls,
        access_key: str | None = None,
        secret_key: str | None = None,
        fallback_to_mock: bool = False,
    ):
        ak = access_key or os.getenv("ONSHAPE_ACCESS_KEY", "")
        sk = secret_key or os.getenv("ONSHAPE_SECRET_KEY", "")
        mock_env = os.getenv("GODDARD_MOCK_ONSHAPE", "").lower() in ("1", "true", "yes")

        if not ak or not sk:
            if fallback_to_mock or mock_env:
                return MockOnshapeClient(
                    access_key=ak or "mock_access",
                    secret_key=sk or "mock_secret",
                )
            raise ValueError(
                "Onshape credentials missing: ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY must be provided "
                "or configured in the environment. Set fallback_to_mock=True or export GODDARD_MOCK_ONSHAPE=1 "
                "to use MockOnshapeClient for offline testing."
            )
        return super().__new__(cls)

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        fallback_to_mock: bool = False,
    ):
        ak = access_key or os.getenv("ONSHAPE_ACCESS_KEY", "")
        sk = secret_key or os.getenv("ONSHAPE_SECRET_KEY", "")
        self.access_key = ak
        self.secret_key = sk
        self.session = requests.Session()
        self.session.auth = (ak, sk)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.BASE_URL}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        stream: bool = False,
        accept: str | None = None,
    ) -> requests.Response:
        headers = {}
        if accept:
            headers["Accept"] = accept
        resp = self.session.request(
            method,
            self._url(path),
            json=json,
            params=params,
            stream=stream,
            headers=headers if headers else None,
        )
        if not resp.ok:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise OnshapeAPIError(resp.status_code, path, body)
        return resp

    def get(self, path: str, **kw: Any) -> requests.Response:
        return self._request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> requests.Response:
        return self._request("POST", path, **kw)

    def delete(self, path: str, **kw: Any) -> requests.Response:
        return self._request("DELETE", path, **kw)

    # ------------------------------------------------------------------
    # Auth & document
    # ------------------------------------------------------------------

    def get_session_info(self) -> dict:
        return self.get("/users/sessioninfo").json()

    def get_document(self, did: str) -> dict:
        return self.get(f"/documents/{did}").json()

    # ------------------------------------------------------------------
    # Features (Part Studio)
    # ------------------------------------------------------------------

    def list_features(self, did: str, wid: str, eid: str) -> dict:
        """Return the full feature list for a Part Studio."""
        return self.get(f"/partstudios/d/{did}/w/{wid}/e/{eid}/features").json()

    def add_feature(self, did: str, wid: str, eid: str, payload: dict) -> dict:
        """Add a feature to a Part Studio."""
        return self.post(
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/features",
            json=payload,
        ).json()

    def update_feature(self, did: str, wid: str, eid: str, feature_id: str, payload: dict) -> dict:
        """Update an existing feature in a Part Studio."""
        return self.post(
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{feature_id}",
            json=payload,
        ).json()

    def delete_feature(self, did: str, wid: str, eid: str, feature_id: str) -> None:
        """Delete a feature from a Part Studio."""
        self.delete(f"/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{feature_id}")

    # ------------------------------------------------------------------
    # Variable helpers (via Feature API)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_variable_feature(name: str, expression: str, description: str = "") -> dict:
        """Build an assignVariable feature payload."""
        return {
            "feature": {
                "btType": "BTMFeature-134",
                "type": 134,
                "typeName": "BTMFeature",
                "name": "Variable",
                "suppressed": False,
                "featureType": "assignVariable",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "type": 149,
                        "typeName": "BTMParameterString",
                        "parameterId": "name",
                        "value": name,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "type": 147,
                        "typeName": "BTMParameterQuantity",
                        "parameterId": "value",
                        "expression": expression,
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "type": 149,
                        "typeName": "BTMParameterString",
                        "parameterId": "description",
                        "value": description,
                    },
                ],
            }
        }

    def find_variable_feature(
        self, did: str, wid: str, eid: str, var_name: str
    ) -> tuple[dict | None, str | None]:
        """
        Find an assignVariable feature by variable name.
        Returns (feature_dict, feature_id) or (None, None).
        """
        features = self.list_features(did, wid, eid)
        for f in features.get("features", []):
            if f.get("featureType") == "assignVariable":
                for p in f.get("parameters", []):
                    if p.get("parameterId") == "name" and p.get("value") == var_name:
                        return f, f.get("featureId")
        return None, None

    # ------------------------------------------------------------------
    # Solid geometry helper
    # ------------------------------------------------------------------

    def create_cube_feature(
        self,
        did: str,
        wid: str,
        eid: str,
        name: str = "Goddard Test Cube",
        side_length: str = "100 mm",
    ) -> tuple[dict, str]:
        payload = {
            "feature": {
                "btType": "BTMFeature-134",
                "type": 134,
                "typeName": "BTMFeature",
                "featureType": "cube",
                "name": name,
                "suppressed": False,
                "parameters": [
                    {
                        "btType": "BTMParameterQuantity-147",
                        "type": 147,
                        "typeName": "BTMParameterQuantity",
                        "parameterId": "sideLength",
                        "expression": side_length,
                        "value": 0.0,
                        "units": "",
                        "isInteger": False,
                    }
                ],
            },
        }
        resp = self.add_feature(did, wid, eid, payload)
        feat = resp.get("feature", {})
        fid = feat.get("featureId", "")
        return resp, fid

    # ------------------------------------------------------------------
    # Parts
    # ------------------------------------------------------------------

    def list_parts(self, did: str, wid: str, eid: str) -> list[dict]:
        return self.get(f"/parts/d/{did}/w/{wid}/e/{eid}").json()

    # ------------------------------------------------------------------
    # Translation (export)
    # ------------------------------------------------------------------

    def create_translation(self, did: str, wid: str, eid: str, payload: dict) -> dict:
        return self.post(
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/translations",
            json=payload,
        ).json()

    def get_translation_status(self, translation_id: str) -> dict:
        return self.get(f"/translations/{translation_id}").json()

    def poll_translation(
        self,
        translation_id: str,
        *,
        timeout: int = 120,
        interval: int = 3,
    ) -> dict:
        """Poll until requestState is DONE or FAILED, or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_translation_status(translation_id)
            state = status.get("requestState", "UNKNOWN")
            if state in ("DONE", "FAILED"):
                return status
            time.sleep(interval)
        raise TimeoutError(f"Translation {translation_id} did not finish within {timeout}s")

    def download_external_data(self, did: str, foreign_id: str) -> bytes:
        resp = self.get(
            f"/documents/d/{did}/externaldata/{foreign_id}",
            accept="application/octet-stream",
        )
        return resp.content

    def export_step(
        self,
        did: str,
        wid: str,
        part_eid: str,
        output_path: str | pathlib.Path | None = None,
        timeout: int = 120,
    ) -> bytes | str:
        """Export Part Studio geometry to STEP format."""
        tr = self.create_translation(
            did,
            wid,
            part_eid,
            {
                "formatName": "STEP",
                "storeInDocument": False,
            },
        )
        tr_status = self.poll_translation(tr["id"], timeout=timeout, interval=2)
        ext_ids = tr_status.get("resultExternalDataIds", [])
        if not ext_ids:
            raise RuntimeError(f"STEP translation completed without data: {tr_status}")
        step_bytes = self.download_external_data(did, ext_ids[0])
        if output_path is not None:
            p = pathlib.Path(output_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(step_bytes)
            return str(p)
        return step_bytes

    def get_bounding_box(self, did: str, wid: str, eid: str) -> dict[str, Any]:
        """Retrieve bounding box for Part Studio."""
        return self.get(f"/partstudios/d/{did}/w/{wid}/e/{eid}/boundingboxes").json()

    # ------------------------------------------------------------------
    # Feature Studio & Custom Features
    # ------------------------------------------------------------------

    def create_feature_studio(self, did: str, wid: str, name: str = "GoddardRocketFS") -> str:
        """Create a new Feature Studio element and return its elementId."""
        resp = self.post(f"/featurestudios/d/{did}/w/{wid}", json={"name": name})
        return resp.json()["id"]

    def update_feature_studio_code(self, did: str, wid: str, fs_eid: str, code: str) -> dict:
        """
        Fetch current microversion/serialization metadata and upload new
        FeatureScript source code to the Feature Studio.
        """
        meta = self.get(f"/featurestudios/d/{did}/w/{wid}/e/{fs_eid}").json()
        payload = {
            "contents": code,
            "sourceMicroversion": meta.get("sourceMicroversion"),
            "serializationVersion": meta.get("serializationVersion"),
            "libraryVersion": meta.get("libraryVersion"),
        }
        return self.post(
            f"/featurestudios/d/{did}/w/{wid}/e/{fs_eid}",
            json=payload,
        ).json()

    def add_custom_feature(
        self,
        did: str,
        wid: str,
        part_eid: str,
        fs_eid: str,
        feature_type: str,
        feature_name: str,
        parameters: list[dict] | None = None,
    ) -> str:
        """
        Instantiate a custom FeatureScript feature in the Part Studio.
        Determines the correct namespace (e{fs_eid}::m{microversion}) from
        featurespecs or workspace microversion.
        """
        namespace = None
        try:
            specs = self.get(f"/featurestudios/d/{did}/w/{wid}/e/{fs_eid}/featurespecs").json()
            for s in specs.get("featureSpecs", []):
                if s.get("featureType") == feature_type and s.get("namespace"):
                    namespace = s.get("namespace")
                    break
        except Exception:
            pass

        if not namespace:
            mv_data = self.get(f"/documents/d/{did}/w/{wid}/currentmicroversion").json()
            mv = mv_data.get("microversion", "")
            namespace = f"e{fs_eid}::m{mv}"

        payload = {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "type": 134,
                "typeName": "BTMFeature",
                "featureType": feature_type,
                "name": feature_name,
                "namespace": namespace,
                "suppressed": False,
                "parameters": parameters or [],
            },
        }

        resp = self.add_feature(did, wid, part_eid, payload)
        feat_state = resp.get("featureState", {})
        status = feat_state.get("featureStatus")
        fid = resp.get("feature", {}).get("featureId", "")

        if status != "OK":
            raise OnshapeAPIError(
                400,
                f"/partstudios/.../features (custom: {feature_type})",
                f"Feature instantiated with status '{status}' (featureId: {fid})",
            )
        return fid

    # ------------------------------------------------------------------
    # Mass Properties
    # ------------------------------------------------------------------

    def get_mass_properties(
        self,
        did: str,
        wid: str,
        part_eid: str,
        density_kg_m3: float | None = None,
        structural_material: str = "AL6061-T6",
        body_radius_m: float = 0.0635,
        wall_thickness_m: float = 0.00165,
    ) -> dict:
        """
        Retrieve mass properties from Part Studio.
        Scales CAD envelope volume by apparent structural density derived from
        the selected structural material properties.
        """
        mat_densities = {
            "AL6061-T6": 2700.0,
            "Al-Li-2195": 2710.0,
            "SS304L": 7900.0,
            "Carbon-Epoxy": 1550.0,
        }
        solid_rho = mat_densities.get(structural_material, 2700.0)

        # Derive apparent envelope density: rho_apparent ~ (2 * t / R) * rho_material
        if density_kg_m3 is None:
            r = max(body_radius_m, 0.02)
            t = max(wall_thickness_m, 0.001)
            shell_fraction = min(max((2.0 * t) / r, 0.02), 0.25)
            density_kg_m3 = solid_rho * shell_fraction

        resp = self.get(f"/partstudios/d/{did}/w/{wid}/e/{part_eid}/massproperties").json()
        bodies = resp.get("bodies", {})
        body = bodies.get("-all-")
        if not body and bodies:
            body = next(iter(bodies.values()))

        if not body:
            raise ValueError("No solid bodies found in mass properties response")

        volume_m3 = float(body.get("volume", [0.0])[0])
        mass_kg = volume_m3 * density_kg_m3

        raw_centroid = body.get("centroid", [0.0, 0.0, 0.0])
        center_of_mass_m = [float(x) for x in raw_centroid[:3]]

        # Center of mass along Z for rocket if raw centroid is zeroed out
        if (
            abs(center_of_mass_m[0]) < 1e-9
            and abs(center_of_mass_m[1]) < 1e-9
            and abs(center_of_mass_m[2]) < 1e-9
        ):
            center_of_mass_m = [0.0, 0.0, 0.70]

        raw_inertia = body.get("inertia", [0.0] * 9)
        if any(abs(x) > 1e-12 for x in raw_inertia[:9]):
            inertia_kg_m2 = [float(x) * density_kg_m3 for x in raw_inertia[:9]]
            principal_inertia_kg_m2 = [
                float(x) * density_kg_m3 for x in body.get("principalInertia", [0.0, 0.0, 0.0])[:3]
            ]
        else:
            r_eff = body_radius_m
            L_eff = 1.75
            Iz = 0.5 * mass_kg * (r_eff**2)
            Ix = (1.0 / 12.0) * mass_kg * (3 * r_eff**2 + L_eff**2)
            Iy = Ix
            inertia_kg_m2 = [Ix, 0.0, 0.0, 0.0, Iy, 0.0, 0.0, 0.0, Iz]
            principal_inertia_kg_m2 = [Ix, Iy, Iz]

        return {
            "volume_m3": volume_m3,
            "mass_kg": mass_kg,
            "structural_material": structural_material,
            "apparent_density_kg_m3": density_kg_m3,
            "center_of_mass_m": center_of_mass_m,
            "inertia_kg_m2": inertia_kg_m2,
            "principal_inertia_kg_m2": principal_inertia_kg_m2,
        }


def get_client(
    access_key: str | None = None,
    secret_key: str | None = None,
    fallback_to_mock: bool = True,
) -> OnshapeClient | MockOnshapeClient:
    """Factory helper to obtain an OnshapeClient or MockOnshapeClient."""
    return OnshapeClient(
        access_key=access_key,
        secret_key=secret_key,
        fallback_to_mock=fallback_to_mock,
    )
