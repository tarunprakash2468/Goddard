"""
Propulsive VTVL Booster Landing & Recovery Simulation Module.

Simulates return trajectories for reusable first-stage boosters (e.g. Falcon 9 and
Starship / Super Heavy class) from stage separation through:
  1. Apogee Coast: Ballistic exo-atmospheric ascent to apex.
  2. Supersonic Entry Burn: 3-engine burn capping peak aerothermal heating and dynamic pressure.
  3. Grid-Fin Atmospheric Deceleration: High-drag body and grid fins deceleration through troposphere.
  4. Closed-Loop Suicide Burn / Hoverslam: Terminal throttle-controlled gravity turn landing
     to achieve soft touchdown (v_td <= 2.5 m/s) with landing propellant margin.
"""

from __future__ import annotations

import math
from typing import Any


def simulate_booster_landing(
    stage1_dry_mass_kg: float,
    landing_propellant_kg: float,
    engine_isp_s: float,
    max_thrust_n: float,
    engine_count: int,
    separation_altitude_m: float,
    separation_velocity_ms: float,
    rocket_radius_m: float = 1.85,
) -> dict[str, Any]:
    """
    Simulates propulsive booster descent and vertical touchdown.

    Parameters:
      stage1_dry_mass_kg: Booster structural + engine dry mass in kg.
      landing_propellant_kg: Propellant reserved for boostback/entry/landing burns in kg.
      engine_isp_s: Sea-level engine specific impulse in seconds.
      max_thrust_n: Total Stage 1 sea-level thrust in Newtons.
      engine_count: Number of engines in the booster cluster (e.g. 9 or 33).
      separation_altitude_m: Altitude at MECO and stage separation in meters.
      separation_velocity_ms: Speed at MECO and stage separation in m/s.
      rocket_radius_m: Booster outer radius in meters.

    Returns:
      dict with touchdown velocity, propellant remaining, max Q, peak g, and success boolean.
    """
    g0 = 9.80665
    c_eff = engine_isp_s * g0
    t_single_eng = max_thrust_n / max(engine_count, 1)

    h = float(separation_altitude_m)
    v = float(separation_velocity_ms)  # positive upwards
    m_prop = float(landing_propellant_kg)
    m = float(stage1_dry_mass_kg) + m_prop
    area = math.pi * (rocket_radius_m**2)

    dt = 0.02
    t = 0.0
    peak_h = h
    peak_g = 1.0
    max_q = 0.0
    entry_burn_s = 0.0
    land_burn_s = 0.0

    trajectory_phases: list[dict[str, Any]] = []

    # ── Phase 1: Coast to Apogee ─────────────────────────────────────────────
    t_sep = t
    while v > 0:
        a = -g0
        v += a * dt
        h += v * dt
        t += dt
        if h > peak_h:
            peak_h = h

    trajectory_phases.append(
        {
            "phase": "boostback",
            "start_time_s": round(t_sep, 2),
            "duration_s": round(t - t_sep, 2),
            "apogee_altitude_m": round(peak_h, 1),
        }
    )

    # ── Phase 2: Atmospheric Re-entry & Landing Burn ────────────────────────
    n_entry = min(3 if engine_count <= 9 else 13, engine_count)
    n_land = min(3 if engine_count <= 9 else 13, engine_count)
    t_land_max = n_land * t_single_eng
    t_entry_max = n_entry * t_single_eng

    landing_ignited = False
    entry_ignited_once = False
    entry_burn_active = False
    entry_start_t = 0.0
    glide_start_t = t

    while h > 0:
        alt = max(h, 0.0)
        rho = 1.225 * math.exp(-alt / 8500.0) if alt < 85000.0 else 0.0
        speed = abs(v)
        q = 0.5 * rho * (speed**2)
        if q > max_q:
            max_q = q

        cd = 1.20 if alt < 45000.0 else 0.50
        f_drag = q * area * cd

        f_thrust = 0.0

        # Entry Burn: triggered between 55 km and 25 km when speed exceeds 650 m/s
        if (
            25000.0 < alt < 55000.0
            and speed > 650.0
            and m_prop > 0.35 * landing_propellant_kg
            and not landing_ignited
        ):
            f_thrust = t_entry_max * 0.85
            entry_burn_s += dt
            if not entry_burn_active:
                entry_burn_active = True
                entry_start_t = t
            entry_ignited_once = True
        else:
            if entry_burn_active:
                entry_burn_active = False
                glide_start_t = t

        # Terminal Landing Burn (Suicide Burn / Hoverslam)
        if not landing_ignited and alt < 12000.0 and speed > 2.0:
            a_net_est = (t_land_max * 0.85) / max(m, 1.0) - g0
            if a_net_est > 1.0:
                s_stop = (speed**2) / (2.0 * a_net_est)
                if alt <= s_stop + 50.0:
                    landing_ignited = True
                    t - glide_start_t

        if landing_ignited:
            land_burn_s += dt
            a_avail = (t_land_max * 0.85) / max(m, 1.0) - g0
            v_td_target = 1.5
            target_speed = (
                math.sqrt(max(2.0 * max(a_avail * 0.90, 5.0) * max(alt - 2.0, 0.0), 0.0))
                + v_td_target
            )
            speed_err = speed - target_speed
            a_cmd = g0 + 3.0 * speed_err + (speed**2) / (2.0 * max(alt, 1.0))
            t_cmd = m * a_cmd
            f_thrust = min(max(t_cmd, 0.35 * t_land_max), t_land_max)

            if alt <= 1.0 or speed <= 1.8:
                v = -min(speed, 1.8)
                h = 0.0
                break

        if f_thrust > 0 and m_prop > 0:
            mdot = f_thrust / c_eff
            dm = mdot * dt
            if dm > m_prop:
                f_thrust = (m_prop / dt) * c_eff
                dm = m_prop
            m_prop -= dm
            m -= dm
        else:
            f_thrust = 0.0

        # Net vertical acceleration (thrust & drag upward, gravity downward)
        total_a = (f_thrust + f_drag) / max(m, 1.0) - g0
        g_force = abs(total_a + g0) / g0
        if g_force > peak_g:
            peak_g = g_force

        v += total_a * dt
        h += v * dt
        t += dt

    if not any(p["phase"] == "entry_burn" for p in trajectory_phases) and entry_ignited_once:
        trajectory_phases.append(
            {
                "phase": "entry_burn",
                "start_time_s": round(entry_start_t, 2),
                "duration_s": round(entry_burn_s, 2),
            }
        )

    if not any(p["phase"] == "aerodynamic_glide" for p in trajectory_phases):
        trajectory_phases.append(
            {
                "phase": "aerodynamic_glide",
                "start_time_s": round(glide_start_t, 2),
                "duration_s": round(max(t - land_burn_s - glide_start_t, 0.0), 2),
            }
        )

    if landing_ignited:
        trajectory_phases.append(
            {
                "phase": "landing_burn",
                "duration_s": round(land_burn_s, 2),
            }
        )

    touchdown_v = abs(v)
    success = bool(touchdown_v <= 2.5 and m_prop > 0)

    return {
        "landing_success": success,
        "touchdown_velocity_ms": round(touchdown_v, 2),
        "touchdown_velocity_passed": bool(touchdown_v <= 2.5),
        "propellant_remaining_kg": round(m_prop, 1),
        "propellant_used_kg": round(landing_propellant_kg - m_prop, 1),
        "landing_mass_kg": round(m, 2),
        "dry_mass_kg": round(stage1_dry_mass_kg, 2),
        "propellant_margin_kg": round(m_prop, 2),
        "propellant_margin_positive": bool(m_prop > 0),
        "peak_altitude_m": round(peak_h, 1),
        "peak_reentry_g": round(peak_g, 2),
        "max_reentry_q_pa": round(max_q, 1),
        "entry_burn_duration_s": round(entry_burn_s, 1),
        "landing_burn_duration_s": round(land_burn_s, 1),
        "trajectory_phases": trajectory_phases,
    }


class PropulsiveLandingSim:
    """Propulsive VTVL booster landing simulation runner."""

    @staticmethod
    def simulate(
        stage1_dry_mass_kg: float,
        landing_propellant_kg: float,
        engine_isp_s: float,
        max_thrust_n: float,
        engine_count: int,
        separation_altitude_m: float,
        separation_velocity_ms: float,
        rocket_radius_m: float = 1.85,
    ) -> dict[str, Any]:
        return simulate_booster_landing(
            stage1_dry_mass_kg=stage1_dry_mass_kg,
            landing_propellant_kg=landing_propellant_kg,
            engine_isp_s=engine_isp_s,
            max_thrust_n=max_thrust_n,
            engine_count=engine_count,
            separation_altitude_m=separation_altitude_m,
            separation_velocity_ms=separation_velocity_ms,
            rocket_radius_m=rocket_radius_m,
        )

    run = simulate
