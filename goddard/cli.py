"""
Unified CLI for the Goddard Rocket Design Platform.

Subcommands:
  - goddard size: Run coupled rocket sizing and mass estimation.
  - goddard serve: Launch the interactive 3D mission control dashboard.
  - goddard mcp: Run the FastMCP server for LLM agent integration.
  - goddard version: Display version and build info.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from goddard import __version__


def _cmd_version(args: argparse.Namespace) -> int:
    print(f"Goddard Rocket Design Suite v{__version__}")
    return 0


def _cmd_size(args: argparse.Namespace) -> int:
    from goddard.sizing.coupled_wer import run_coupled_sizing
    from goddard.sizing.mission_spec import evaluate_spec_completeness

    mission_alias = {
        "sounding": "sounding_suborbital",
        "sounding_suborbital": "sounding_suborbital",
        "orbital": "orbital_insertion",
        "orbital_insertion": "orbital_insertion",
        "vtvl": "vtvl_hopper",
        "vtvl_hopper": "vtvl_hopper",
    }
    profile = mission_alias.get(args.mission, "sounding_suborbital")

    payload = args.payload
    if payload is None:
        if profile == "orbital_insertion":
            payload = 50.0
        elif profile == "vtvl_hopper":
            payload = 100.0
        else:
            payload = 4.0

    target_orbit = args.target_orbit
    if profile == "orbital_insertion" and target_orbit is None:
        target_orbit = 300.0

    target_apogee = args.target_apogee
    if target_apogee is None:
        if profile == "sounding_suborbital":
            target_apogee = 4200.0
        elif profile == "vtvl_hopper":
            target_apogee = 150.0

    stage_count = 2 if profile == "orbital_insertion" else 1

    spec_input = {
        "mission_profile": profile,
        "payload_mass_kg": payload,
        "target_apogee_m": target_apogee,
        "target_orbit_km": target_orbit,
        "stage_count": stage_count,
        "reusable_booster": bool(profile == "vtvl_hopper"),
    }

    # Evaluate requirements gate
    gate_res = evaluate_spec_completeness(spec_input)
    if gate_res.get("status") == "NEEDS_CLARIFICATION":
        print(f"[*] Requirements Notice for '{profile}':")
        for q in gate_res.get("questions", []):
            print(f"    - {q}")
        print("[*] Proceeding with resolved engineering defaults...\n")

    resolved = gate_res.get("resolved_spec", spec_input)
    sizing_res = run_coupled_sizing(resolved)

    if getattr(args, "json", False):
        print(json.dumps(sizing_res, indent=2))
        return 0

    print("=" * 68)
    print(f" GODDARD SIZING REPORT — {profile.upper()}")
    print("=" * 68)
    print(f" Stage Count         : {sizing_res.get('stage_count')}")
    print(f" Payload Mass        : {payload:.2f} kg")
    if target_orbit:
        print(f" Target Orbit        : {target_orbit:.1f} km")
    if target_apogee:
        print(f" Target Apogee       : {target_apogee:.1f} m")
    mb = sizing_res.get("mass_breakdown", {})
    total_wet = mb.get("total_wet_mass_kg", 0.0) + payload
    total_dry = mb.get("total_dry_mass_kg", 0.0)
    total_prop = mb.get("total_propellant_mass_kg", 0.0)
    total_dv = sizing_res.get("total_delta_v_ms", 0.0)

    print("-" * 68)
    print(f" Gross Liftoff Weight: {total_wet:.2f} kg")
    print(f" Total Dry Mass      : {total_dry:.2f} kg")
    print(f" Total Propellant    : {total_prop:.2f} kg")
    print(f" Total Ideal Delta-V : {total_dv:.1f} m/s")

    geom = sizing_res.get("geometry", {})
    print("-" * 68)
    print(" AIRFRAME GEOMETRY:")
    print(
        f" Body Radius         : {geom.get('body_radius_m', 0.0) * 1000.0:.1f} mm (OD: {geom.get('body_radius_m', 0.0) * 2000.0:.1f} mm)"
    )
    print(f" Body Length         : {geom.get('body_length_m', 0.0):.3f} m")
    print(f" Nose Length         : {geom.get('nose_length_m', 0.0):.3f} m")
    if sizing_res.get("stage_count", 1) > 1:
        print(f" Stage 2 Length      : {geom.get('stage2_length_m', 0.0):.3f} m")
        print(f" Interstage Length   : {geom.get('interstage_length_m', 0.0):.3f} m")

    stages = sizing_res.get("stages", [])
    for idx, st in enumerate(stages, start=1):
        print("-" * 68)
        print(
            f" STAGE {idx} ({st.get('propellant', 'LOX/CH4')}, {st.get('feed_architecture', 'pressure_fed')}):"
        )
        print(
            f"  Thrust             : {st.get('total_thrust_n', 0.0):.1f} N ({st.get('engine_count', 1)} engine(s))"
        )
        print(f"  Burn Time          : {st.get('burn_time_s', 0.0):.2f} s")
        print(f"  Stage Dry Mass     : {st.get('stage_dry_mass_kg', 0.0):.2f} kg")
        print(f"  Propellant Mass    : {st.get('propellant_mass_kg', 0.0):.2f} kg")
        print(f"  Stage Delta-V      : {st.get('delta_v_ms', 0.0):.1f} m/s")

    print("=" * 68)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    print(f"[*] Starting Goddard Mission Control Dashboard on http://{args.host}:{args.port}")
    uvicorn.run("goddard.ui.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    from goddard.server.goddard_mcp import main as mcp_main

    mcp_main()
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from goddard.ui.app import build_revision_bundle_zip, list_revisions

    rev_id_str = args.design_id
    if rev_id_str is None:
        revs = list_revisions()
        if not revs:
            print("Error: No revisions found in design ledger.", file=sys.stderr)
            return 1
        rev_id = revs[-1].get("revision_id", 1)
    else:
        clean_str = str(rev_id_str).lower().replace("rev_", "").replace("rev", "")
        try:
            rev_id = int(clean_str)
        except ValueError:
            print(
                f"Error: Invalid revision ID '{rev_id_str}'. Must be an integer or like 'rev_001'.",
                file=sys.stderr,
            )
            return 1

    try:
        zip_bytes = build_revision_bundle_zip(rev_id)
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        print(f"Error exporting revision {rev_id}: {detail}", file=sys.stderr)
        return 1

    out_path = (
        pathlib.Path(args.output)
        if args.output
        else pathlib.Path.cwd() / f"Goddard_Rev_{rev_id:03d}_Engineering_Package.zip"
    )
    if out_path.is_dir():
        out_path = out_path / f"Goddard_Rev_{rev_id:03d}_Engineering_Package.zip"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(zip_bytes)
    print(
        f"[*] Exported revision {rev_id} bundle to {out_path.resolve()} ({len(zip_bytes) / 1024:.1f} KB)"
    )
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goddard",
        description="Goddard Autonomous Rocket Design Platform CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # goddard version
    subparsers.add_parser("version", help="Print the Goddard version and exit")

    # goddard size
    size_p = subparsers.add_parser("size", help="Execute coupled rocket sizing and mass estimation")
    size_p.add_argument(
        "--mission",
        choices=[
            "sounding",
            "orbital",
            "vtvl",
            "sounding_suborbital",
            "orbital_insertion",
            "vtvl_hopper",
        ],
        default="sounding",
        help="Mission profile (default: sounding)",
    )
    size_p.add_argument(
        "--payload",
        type=float,
        default=None,
        help="Payload mass in kg (default: 4.0 kg for sounding, 50.0 kg for orbital, 100.0 kg for vtvl)",
    )
    size_p.add_argument(
        "--target-orbit",
        type=float,
        default=None,
        help="Target circular orbit altitude in km (default: 300 km for orbital)",
    )
    size_p.add_argument(
        "--target-apogee",
        type=float,
        default=None,
        help="Target apogee altitude in meters (default: 4200 m for sounding, 150 m for vtvl)",
    )
    size_p.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results",
    )

    # goddard serve
    serve_p = subparsers.add_parser(
        "serve", help="Launch the interactive UI mission control server"
    )
    serve_p.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind (default: 0.0.0.0)",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port number to listen on (default: 8050)",
    )
    serve_p.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload on file changes",
    )

    # goddard mcp
    subparsers.add_parser("mcp", help="Run the Goddard FastMCP server")

    # goddard export
    export_p = subparsers.add_parser("export", help="Export complete design bundle ZIP package")
    export_p.add_argument(
        "--design-id",
        "--rev-id",
        "-r",
        dest="design_id",
        default=None,
        help="Revision ID to export (e.g. rev_001 or 1)",
    )
    export_p.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output destination ZIP path",
    )

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "version": _cmd_version,
        "size": _cmd_size,
        "serve": _cmd_serve,
        "mcp": _cmd_mcp,
        "export": _cmd_export,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
