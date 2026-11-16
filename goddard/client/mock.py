"""
Deterministic Mock Onshape Client for offline testing, CI/CD, and disconnected development.
Provides realistic geometric, structural, and translation responses without network access.
"""

from __future__ import annotations

import json
import math
import pathlib
from typing import Any

# Minimal valid AP214 STEP cylinder representation generated via OpenCASCADE.
# Gmsh can import and mesh this model directly without external CAD servers.
MINIMAL_STEP_STRING = """ISO-10303-21;
HEADER;
FILE_NAME('Open CASCADE Shape Model','2026-11-15T18:17:04',('Author'),(
    'Open CASCADE'),'Open CASCADE STEP processor 7.8','Open CASCADE 7.8'
  ,'Unknown');
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = APPLICATION_PROTOCOL_DEFINITION('international standard',
  'automotive_design',2000,#2);
#2 = APPLICATION_CONTEXT(
  'core data for automotive mechanical design processes');
#3 = SHAPE_DEFINITION_REPRESENTATION(#4,#10);
#4 = PRODUCT_DEFINITION_SHAPE('','',#5);
#5 = PRODUCT_DEFINITION('design','',#6,#9);
#6 = PRODUCT_DEFINITION_FORMATION('','',#7);
#7 = PRODUCT('Open CASCADE STEP translator 7.8 1',
  'Open CASCADE STEP translator 7.8 1','',(#8));
#8 = PRODUCT_CONTEXT('',#2,'mechanical');
#9 = PRODUCT_DEFINITION_CONTEXT('part definition',#2,'design');
#10 = ADVANCED_BREP_SHAPE_REPRESENTATION('',(#11,#15),#113);
#11 = AXIS2_PLACEMENT_3D('',#12,#13,#14);
#12 = CARTESIAN_POINT('',(0.,0.,0.));
#13 = DIRECTION('',(0.,0.,1.));
#14 = DIRECTION('',(1.,0.,-0.));
#15 = MANIFOLD_SOLID_BREP('',#16);
#16 = CLOSED_SHELL('',(#17,#105,#109));
#17 = ADVANCED_FACE('',(#18),#31,.T.);
#18 = FACE_BOUND('',#19,.T.);
#19 = EDGE_LOOP('',(#20,#54,#77,#104));
#20 = ORIENTED_EDGE('',*,*,#21,.F.);
#21 = EDGE_CURVE('',#22,#22,#24,.T.);
#22 = VERTEX_POINT('',#23);
#23 = CARTESIAN_POINT('',(0.1,-2.449293598295E-17,1.));
#24 = SURFACE_CURVE('',#25,(#30,#42),.PCURVE_S1.);
#25 = CIRCLE('',#26,0.1);
#26 = AXIS2_PLACEMENT_3D('',#27,#28,#29);
#27 = CARTESIAN_POINT('',(0.,0.,1.));
#28 = DIRECTION('',(0.,0.,1.));
#29 = DIRECTION('',(1.,0.,-0.));
#30 = PCURVE('',#31,#36);
#31 = CYLINDRICAL_SURFACE('',#32,0.1);
#32 = AXIS2_PLACEMENT_3D('',#33,#34,#35);
#33 = CARTESIAN_POINT('',(0.,0.,0.));
#34 = DIRECTION('',(0.,0.,1.));
#35 = DIRECTION('',(1.,0.,-0.));
#36 = DEFINITIONAL_REPRESENTATION('',(#37),#41);
#37 = LINE('',#38,#39);
#38 = CARTESIAN_POINT('',(0.,1.));
#39 = VECTOR('',#40,1.);
#40 = DIRECTION('',(1.,0.));
#41 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#42 = PCURVE('',#43,#48);
#43 = PLANE('',#44);
#44 = AXIS2_PLACEMENT_3D('',#45,#46,#47);
#45 = CARTESIAN_POINT('',(0.,0.,1.));
#46 = DIRECTION('',(0.,0.,1.));
#47 = DIRECTION('',(1.,0.,-0.));
#48 = DEFINITIONAL_REPRESENTATION('',(#49),#53);
#49 = CIRCLE('',#50,0.1);
#50 = AXIS2_PLACEMENT_2D('',#51,#52);
#51 = CARTESIAN_POINT('',(0.,0.));
#52 = DIRECTION('',(1.,0.));
#53 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#54 = ORIENTED_EDGE('',*,*,#55,.F.);
#55 = EDGE_CURVE('',#56,#22,#58,.T.);
#56 = VERTEX_POINT('',#57);
#57 = CARTESIAN_POINT('',(0.1,-2.449293598295E-17,0.));
#58 = SEAM_CURVE('',#59,(#63,#70),.PCURVE_S1.);
#59 = LINE('',#60,#61);
#60 = CARTESIAN_POINT('',(0.1,-2.449293598295E-17,0.));
#61 = VECTOR('',#62,1.);
#62 = DIRECTION('',(0.,0.,1.));
#63 = PCURVE('',#31,#64);
#64 = DEFINITIONAL_REPRESENTATION('',(#65),#69);
#65 = LINE('',#66,#67);
#66 = CARTESIAN_POINT('',(6.28318530718,-0.));
#67 = VECTOR('',#68,1.);
#68 = DIRECTION('',(0.,1.));
#69 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#70 = PCURVE('',#31,#71);
#71 = DEFINITIONAL_REPRESENTATION('',(#72),#76);
#72 = LINE('',#73,#74);
#73 = CARTESIAN_POINT('',(0.,-0.));
#74 = VECTOR('',#75,1.);
#75 = DIRECTION('',(0.,1.));
#76 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#77 = ORIENTED_EDGE('',*,*,#78,.T.);
#78 = EDGE_CURVE('',#56,#56,#79,.T.);
#79 = SURFACE_CURVE('',#80,(#85,#92),.PCURVE_S1.);
#80 = CIRCLE('',#81,0.1);
#81 = AXIS2_PLACEMENT_3D('',#82,#83,#84);
#82 = CARTESIAN_POINT('',(0.,0.,0.));
#83 = DIRECTION('',(0.,0.,1.));
#84 = DIRECTION('',(1.,0.,-0.));
#85 = PCURVE('',#31,#86);
#86 = DEFINITIONAL_REPRESENTATION('',(#87),#91);
#87 = LINE('',#88,#89);
#88 = CARTESIAN_POINT('',(0.,0.));
#89 = VECTOR('',#90,1.);
#90 = DIRECTION('',(1.,0.));
#91 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#92 = PCURVE('',#93,#98);
#93 = PLANE('',#94);
#94 = AXIS2_PLACEMENT_3D('',#95,#96,#97);
#95 = CARTESIAN_POINT('',(0.,0.,0.));
#96 = DIRECTION('',(0.,0.,1.));
#97 = DIRECTION('',(1.,0.,-0.));
#98 = DEFINITIONAL_REPRESENTATION('',(#99),#103);
#99 = CIRCLE('',#100,0.1);
#100 = AXIS2_PLACEMENT_2D('',#101,#102);
#101 = CARTESIAN_POINT('',(0.,0.));
#102 = DIRECTION('',(1.,0.));
#103 = ( GEOMETRIC_REPRESENTATION_CONTEXT(2) 
PARAMETRIC_REPRESENTATION_CONTEXT() REPRESENTATION_CONTEXT('2D SPACE',''
  ) );
#104 = ORIENTED_EDGE('',*,*,#55,.T.);
#105 = ADVANCED_FACE('',(#106),#43,.T.);
#106 = FACE_BOUND('',#107,.T.);
#107 = EDGE_LOOP('',(#108));
#108 = ORIENTED_EDGE('',*,*,#21,.T.);
#109 = ADVANCED_FACE('',(#110),#93,.F.);
#110 = FACE_BOUND('',#111,.T.);
#111 = EDGE_LOOP('',(#112));
#112 = ORIENTED_EDGE('',*,*,#78,.F.);
#113 = ( GEOMETRIC_REPRESENTATION_CONTEXT(3) 
GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#117)) GLOBAL_UNIT_ASSIGNED_CONTEXT
((#114,#115,#116)) REPRESENTATION_CONTEXT('Context #1',
  '3D Context with UNIT and UNCERTAINTY') );
#114 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );
#115 = ( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) );
#116 = ( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() );
#117 = UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#114,
  'distance_accuracy_value','confusion accuracy');
#118 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#7));
ENDSEC;
END-ISO-10303-21;
"""


class MockResponse:
    """Mimics a requests.Response object for mock REST interactions."""

    def __init__(self, data: Any, status_code: int = 200, content: bytes | None = None):
        self._data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.content = (
            content
            if content is not None
            else (
                json.dumps(data).encode("utf-8")
                if isinstance(data, (dict, list))
                else str(data).encode("utf-8")
            )
        )
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if isinstance(self._data, (dict, list)):
            return self._data
        return json.loads(self.text)


class MockOnshapeClient:
    """
    Deterministic Mock of OnshapeClient.
    Provides identical API methods and realistic outputs without requiring network access.
    """

    BASE_URL = "https://mock.cad.onshape.com/api/v6"

    def __init__(
        self,
        access_key: str = "mock_access",
        secret_key: str = "mock_secret",
        base_url: str = "https://mock.cad.onshape.com/api/v6",
        *args: Any,
        **kwargs: Any,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url
        self._created_features: list[dict[str, Any]] = []
        self._feature_studios: dict[str, str] = {"mock_fs_eid_001": "GoddardRocketFS"}

    # ── High-Level Parity Methods ────────────────────────────────────────────

    def get_session_info(self) -> dict[str, Any]:
        """Return mock session info for method parity with OnshapeClient."""
        return self.get("/users/sessioninfo").json()

    def get_document(self, did: str) -> dict[str, Any]:
        """Return mock document metadata for method parity with OnshapeClient."""
        return {"id": did, "name": "Mock Rocket Document"}

    # ── Low-Level Mock REST Interface ────────────────────────────────────────

    def get(self, path: str, **kw: Any) -> MockResponse:
        if "/elements" in path:
            return MockResponse(
                [
                    {
                        "id": "mock_fs_eid_001",
                        "name": "GoddardRocketFS",
                        "elementType": "FEATURESTUDIO",
                    }
                ]
            )
        if "/documents" in path:
            did = (
                path.split("/documents/")[-1].split("/")[0] if "/documents/" in path else "mock_doc"
            )
            return MockResponse({"id": did, "name": "Mock Rocket Document"})
        if "/sessioninfo" in path:
            return MockResponse({"id": "mock_user", "name": "Mock User", "state": 1})
        if "/featurespecs" in path:
            return MockResponse({"featureSpecs": []})
        if "/currentmicroversion" in path:
            return MockResponse({"microversion": "mock_microversion_001"})
        if "/features" in path:
            return MockResponse({"features": self._created_features})
        if "/massproperties" in path:
            mp = self.get_mass_properties("d", "w", "e")
            return MockResponse(
                {
                    "bodies": {
                        "-all-": {
                            "volume": [mp["volume_m3"]],
                            "centroid": mp["center_of_mass_m"],
                            "inertia": mp["inertia_kg_m2"],
                            "principalInertia": mp["principal_inertia_kg_m2"],
                        }
                    }
                }
            )
        return MockResponse({})

    def post(self, path: str, **kw: Any) -> MockResponse:
        body = kw.get("json", {})
        if "/translations" in path:
            return MockResponse({"id": "mock_translation_001"})
        if "/featurestudios" in path:
            name = body.get("name", "GoddardRocketFS")
            fs_id = f"mock_fs_{len(self._feature_studios) + 1:03d}"
            self._feature_studios[fs_id] = name
            return MockResponse({"id": fs_id})
        if "/features" in path:
            fid = f"mock_feat_{len(self._created_features) + 1:03d}"
            feat_record = {
                "featureId": fid,
                "featureType": body.get("feature", {}).get("featureType", "custom"),
                "name": body.get("feature", {}).get("name", "Custom Feature"),
                "parameters": body.get("feature", {}).get("parameters", []),
            }
            self._created_features.append(feat_record)
            return MockResponse(
                {
                    "feature": feat_record,
                    "featureState": {"featureStatus": "OK"},
                }
            )
        return MockResponse({"status": "OK", "id": "mock_post_id"})

    def delete(self, path: str, **kw: Any) -> MockResponse:
        return MockResponse({"status": "OK"})

    # ── Feature Studio & Custom Features ─────────────────────────────────────

    def create_feature_studio(
        self, did: str = "", wid: str = "", name: str = "GoddardRocketFS"
    ) -> str:
        fs_id = f"mock_fs_{len(self._feature_studios) + 1:03d}"
        self._feature_studios[fs_id] = name
        return fs_id

    def update_feature_studio_code(
        self, did: str = "", wid: str = "", fs_eid: str = "", code: str = ""
    ) -> dict[str, Any]:
        return {
            "status": "OK",
            "elementId": fs_eid,
            "bytes_received": len(code),
            "message": "Mock FeatureStudio code successfully updated",
        }

    def list_features(self, did: str = "", wid: str = "", eid: str = "") -> dict[str, Any]:
        return {"features": list(self._created_features)}

    def delete_feature(
        self, did: str = "", wid: str = "", eid: str = "", feature_id: str = ""
    ) -> None:
        self._created_features = [
            f for f in self._created_features if f.get("featureId") != feature_id
        ]

    def add_custom_feature(
        self,
        did: str = "",
        wid: str = "",
        part_eid: str = "",
        fs_eid: str = "",
        feature_type: str = "goddardRocketAirframe",
        feature_name: str = "Goddard Rocket Candidate",
        parameters: list[dict] | None = None,
    ) -> str:
        fid = f"mock_feat_{len(self._created_features) + 1:03d}"
        self._created_features.append(
            {
                "featureId": fid,
                "featureType": feature_type,
                "name": feature_name,
                "parameters": parameters or [],
            }
        )
        return fid

    # ── Mass Properties & Bounding Box ───────────────────────────────────────

    def get_mass_properties(
        self,
        did: str = "",
        wid: str = "",
        part_eid: str = "",
        density_kg_m3: float | None = None,
        structural_material: str = "AL6061-T6",
        body_radius_m: float = 0.0635,
        wall_thickness_m: float = 0.00165,
    ) -> dict[str, Any]:
        """
        Deterministic, realistic mass properties based on rocket dimensions & materials.
        """
        mat_densities = {
            "AL6061-T6": 2700.0,
            "Al-Li-2195": 2710.0,
            "SS304L": 7900.0,
            "Carbon-Epoxy": 1550.0,
        }
        solid_rho = mat_densities.get(structural_material, 2700.0)

        if density_kg_m3 is None:
            r = max(body_radius_m, 0.02)
            t = max(wall_thickness_m, 0.001)
            shell_fraction = min(max((2.0 * t) / r, 0.02), 0.25)
            density_kg_m3 = solid_rho * shell_fraction

        # Realistic approximate cylindrical shell + nosecone volume
        length_eff = 1.75
        volume_m3 = round(math.pi * (body_radius_m**2) * length_eff, 6)
        mass_kg = round(volume_m3 * density_kg_m3, 3)

        # Realistic rocket center of mass along Z
        center_of_mass_m = [0.0, 0.0, round(length_eff * 0.40, 3)]

        # Moments of inertia
        iz = 0.5 * mass_kg * (body_radius_m**2)
        ix = (1.0 / 12.0) * mass_kg * (3.0 * body_radius_m**2 + length_eff**2)
        iy = ix

        inertia_kg_m2 = [
            round(ix, 5),
            0.0,
            0.0,
            0.0,
            round(iy, 5),
            0.0,
            0.0,
            0.0,
            round(iz, 5),
        ]
        principal_inertia_kg_m2 = [round(ix, 5), round(iy, 5), round(iz, 5)]

        return {
            "volume_m3": volume_m3,
            "mass_kg": mass_kg,
            "structural_material": structural_material,
            "apparent_density_kg_m3": round(density_kg_m3, 3),
            "center_of_mass_m": center_of_mass_m,
            "inertia_kg_m2": inertia_kg_m2,
            "principal_inertia_kg_m2": principal_inertia_kg_m2,
        }

    def get_bounding_box(
        self,
        did: str = "",
        wid: str = "",
        part_eid: str = "",
        eid: str = "",
        body_radius_m: float = 0.0635,
        length_m: float = 1.75,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Deterministic bounding box metrics."""
        eid = eid or part_eid
        _ = (did, wid, eid, kwargs)
        return {
            "xmin": -body_radius_m,
            "xmax": body_radius_m,
            "ymin": -body_radius_m,
            "ymax": body_radius_m,
            "zmin": 0.0,
            "zmax": length_m,
            "dimensions_m": {
                "dx": round(2.0 * body_radius_m, 4),
                "dy": round(2.0 * body_radius_m, 4),
                "dz": round(length_m, 4),
            },
        }

    # ── Translations & STEP Export ───────────────────────────────────────────

    def create_translation(
        self, did: str = "", wid: str = "", eid: str = "", payload: dict | None = None
    ) -> dict[str, Any]:
        return {"id": "mock_translation_001"}

    def get_translation_status(self, translation_id: str) -> dict[str, Any]:
        return {
            "id": translation_id,
            "requestState": "DONE",
            "resultExternalDataIds": ["mock_ext_step_001"],
        }

    def poll_translation(
        self,
        translation_id: str,
        *,
        timeout: int = 120,
        interval: int = 3,
    ) -> dict[str, Any]:
        return self.get_translation_status(translation_id)

    def download_external_data(self, did: str = "", foreign_id: str = "") -> bytes:
        return MINIMAL_STEP_STRING.encode("utf-8")

    def export_step_string(self, *args: Any, **kwargs: Any) -> str:
        """Return AP214 STEP representation as string."""
        return MINIMAL_STEP_STRING

    def export_step(
        self,
        did: str = "",
        wid: str = "",
        part_eid: str = "",
        output_path: str | pathlib.Path | None = None,
        timeout: int = 120,
    ) -> bytes | str:
        """
        Creates a minimal dummy STEP file or returns valid STEP bytes.
        """
        step_bytes = MINIMAL_STEP_STRING.encode("utf-8")
        if output_path is not None:
            p = pathlib.Path(output_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(step_bytes)
            return str(p)
        return step_bytes
