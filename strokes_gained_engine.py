import math
import random

# ============================================================
# Constants & Baselines
# ============================================================

BASELINE_DRIVER_SPEED = 100.0  # mph

# ---- Environmental / physics constants ---- #
BASELINE_TEMP_F = 75.0           # calibration temperature for your bag
STANDARD_PRESSURE_PA = 101325.0  # sea level pressure
REL_HUMIDITY_DEFAULT = 0.50      # 50% relative humidity
R_DRY_AIR = 287.058              # J/(kg·K)
R_WATER_VAPOR = 461.495          # J/(kg·K)


# Full-swing wedge carries at 100 mph (center values)
FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW": 92,
    "LW": 78,
}

# Full bag baseline at 100 mph driver speed
# club, ball_speed, launch, spin, carry_center, total_center
FULL_BAG_BASE = [
    ("Driver", 148, 13.0, 2500, 233, 253),
    ("3W",     140, 14.5, 3300, 216, 233),
    ("3H",     135, 16.0, 3900, 202, 220),
    ("4i",     128, 14.5, 4600, 182, 194),
    ("5i",     122, 15.5, 5000, 172, 185),
    ("6i",     116, 17.0, 5400, 162, 172),
    ("7i",     110, 18.5, 6200, 151, 161),
    ("8i",     104, 20.5, 7000, 139, 149),
    ("9i",      98, 23.0, 7800, 127, 137),
    ("PW",      92, 28.0, 8500, 118, 124),
    ("GW",      86, 30.0, 9000, 104, 110),
    ("SW",      81, 32.0, 9500,  89,  95),
    ("LW",      75, 34.0,10500,  75,  81),
]

# Shot-type multipliers
SHOT_MULTIPLIERS = {
    "Full":        1.00,
    "Choke-Down":  0.94,
    "3/4":         0.80,
    "1/2":         0.60,
    "1/4":         0.40,
}

# Scoring shots: (club, shot type, trajectory)
SCORING_DEFS = [
    ("PW", "Full",       "Medium-High"),
    ("PW", "Choke-Down", "Medium"),
    ("PW", "3/4",        "Medium"),
    ("SW", "Full",       "High"),
    ("LW", "Full",       "High"),
    ("SW", "3/4",        "Medium-High"),
    ("PW", "1/2",        "Medium-Low"),
    ("LW", "3/4",        "Medium"),
    ("SW", "1/2",        "Medium-Low"),
    ("PW", "1/4",        "Low"),
    ("LW", "1/2",        "Medium-Low"),
    ("GW", "1/4",        "Low"),
    ("SW", "1/4",        "Low"),
    ("LW", "1/4",        "Low"),
    ("GW", "Full",       "Medium-High"),
    ("GW", "Choke-Down", "Medium"),
    ("GW", "3/4",        "Medium"),
    ("GW", "1/2",        "Medium-Low"),
]

# Simplified wind strengths (mph)
WIND_STRENGTH_MAP = {
    "none":   0,
    "light":  5,
    "medium": 10,
    "heavy":  20,
}

# Strategies
STRATEGY_BALANCED = "Balanced"
STRATEGY_CONSERVATIVE = "Conservative"
STRATEGY_AGGRESSIVE = "Aggressive"

DEFAULT_N_SIM = 400


# ============================================================
# Utility functions
# ============================================================

def _scale_value(base_value, driver_speed_mph):
    """Scale a baseline value linearly with driver speed."""
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


def adjust_for_wind(target, wind_dir, wind_strength_label):
    """Into hurts more than downwind helps. Cross adds a small 'safety' bump."""
    label = (wind_strength_label or "none").lower().strip()
    wind_mph = WIND_STRENGTH_MAP.get(label, 0)

    scale = target / 150.0
    scale = max(0.5, min(scale, 1.2))

    wd = (wind_dir or "none").lower()
    adjusted = target

    if wd == "into":
        adjusted += wind_mph * 0.9 * scale
    elif wd == "down":
        adjusted -= wind_mph * 0.4 * scale
    elif wd == "cross":
        adjusted += wind_mph * 0.1 * scale

    return adjusted


def apply_elevation(target, elevation_label):
    label = (elevation_label or "flat").lower().strip()
    if label.startswith("slight up"):
        delta = 5.0
    elif label.startswith("moderate up"):
        delta = 10.0
    elif label.startswith("slight down"):
        delta = -5.0
    elif label.startswith("moderate down"):
        delta = -10.0
    else:
        delta = 0.0
    return target + delta


def apply_lie(target, lie_label):
    lie = (lie_label or "good").lower().strip()
    if lie == "good":
        mult = 1.00
    elif lie in ("ok", "okay"):
        mult = 1.05
    elif lie == "bad":
        mult = 1.12
    else:
        mult = 1.00
    return target * mult


def _f_to_k(temp_f: float) -> float:
    """Convert Fahrenheit to Kelvin."""
    return (temp_f - 32.0) * 5.0 / 9.0 + 273.15


def _air_density(
    temp_f: float,
    pressure_pa: float = STANDARD_PRESSURE_PA,
    rel_humidity: float = REL_HUMIDITY_DEFAULT,
) -> float:
    """
    Compute moist-air density using a simplified physical model.

    Uses:
      - Tetens formula for saturation vapor pressure (approximation)
      - Ideal gas law for dry air + water vapor components

    This is overkill for golf, but gives a tour-level feel.
    """
    # Convert temperature
    t_c = (temp_f - 32.0) * 5.0 / 9.0
    t_k = t_c + 273.15

    # Saturation vapor pressure over water (Tetens formula), in Pa
    # es(T) ≈ 6.112 * exp((17.67*T)/(T+243.5)) hPa  -> multiply by 100 for Pa
    es_hpa = 6.112 * math.exp((17.67 * t_c) / (t_c + 243.5))
    es_pa = es_hpa * 100.0

    # Actual vapor pressure
    e = rel_humidity * es_pa

    # Partial pressure of dry air
    p_dry = pressure_pa - e

    # Density = ρ_dry + ρ_vapor
    rho_dry = p_dry / (R_DRY_AIR * t_k)
    rho_vapor = e / (R_WATER_VAPOR * t_k)

    return rho_dry + rho_vapor


def _environment_distance_scale(
    temp_f: float,
    baseline_temp_f: float = BASELINE_TEMP_F,
    shot_length_yards: float = 150.0,
) -> float:
    """
    Compute a *multiplicative distance scale* based on change in air density.

    Rough idea:
      - Distance is inversely related to sqrt(air density).
      - Longer shots are a bit more sensitive than short shots.
    """
    if temp_f is None:
        return 1.0

    # Air densities at baseline vs current
    rho_base = _air_density(baseline_temp_f)
    rho_cur = _air_density(temp_f)

    # Idealized distance factor from density alone
    # (less dense air -> ball flies farther -> factor > 1)
    raw_factor = (rho_base / rho_cur) ** 0.5

    # Scale sensitivity by shot length (wedge vs long iron vs driver)
    length_factor = max(0.6, min(1.4, shot_length_yards / 150.0))

    # Dial it down a bit so we don't get crazy changes
    # Example: 40°F to 90°F might give ~3–5% change for a 7-iron
    final_factor = 1.0 + (raw_factor - 1.0) * length_factor * 0.7

    return final_factor


def _apply_environment_plays_like(
    target_yards: float,
    temp_f: float,
    baseline_temp_f: float = BASELINE_TEMP_F,
) -> float:
    """
    Apply environmental (temperature/air density) adjustment to a *target yardage*.

    Concept:
      - Your bag is calibrated at baseline_temp_f (e.g., 75°F).
      - On a hotter day, the ball flies farther, so the same raw yardage
        'plays shorter' -> effective target distance is smaller.
      - On a colder day, the opposite: the shot plays longer.

    We do:
      adjusted_target = raw_target / distance_scale
    """
    if temp_f is None:
        return target_yards

    scale = _environment_distance_scale(
        temp_f=temp_f,
        baseline_temp_f=baseline_temp_f,
        shot_length_yards=target_yards,
    )

    # If scale > 1 (ball flies farther), target plays shorter: divide by scale.
    return target_yards / scale



def calculate_plays_like_yardage(
    raw_yards: float,
    wind_dir: str,
    wind_strength_label: str,
    elevation_label: str,
    lie_label: str,
    tendency_label: str = "Neutral",
    temp_f: float = None,
    baseline_temp_f: float = BASELINE_TEMP_F,
) -> float:
    """
    Shared plays-like calculator (used by Caddy + Tournament Prep).

    Steps:
      1) Start from raw rangefinder yardage.
      2) Adjust for wind (direction + strength).
      3) Adjust for elevation.
      4) Adjust for lie quality.
      5) Adjust for player distance tendency (usually short/long).
      6) Apply Level-3 environment model (air density via temperature).

    NOTE:
      - We assume your *bag yardages* are calibrated at baseline_temp_f
        (e.g., 75°F). So temperature is modeled by changing the *effective
        target*, not your stored yardages.
    """
    val = float(raw_yards)

    # Wind / elevation / lie
    val = adjust_for_wind(val, wind_dir, wind_strength_label)
    val = apply_elevation(val, elevation_label)
    val = apply_lie(val, lie_label)

    # Player tendency (distance bias)
    tendency_label = (tendency_label or "Neutral").strip()
    if tendency_label == "Usually Short":
        val += 3.0
    elif tendency_label == "Usually Long":
        val -= 3.0

    # Environment (air density / temperature)
    if temp_f is not None:
        val = _apply_environment_plays_like(
            target_yards=val,
            temp_f=temp_f,
            baseline_temp_f=baseline_temp_f,
        )

    return val



# ============================================================
# Dispersion & SG helpers
# ============================================================

def get_dispersion_sigma(category):
    cat = (category or "").lower()
    if cat in ("driver", "wood", "hybrid"):
        return 18.0
    if cat == "long_iron":
        return 15.0
    if cat == "mid_iron":
        return 12.0
    if cat == "short_iron":
        return 9.0
    if cat == "scoring_wedge":
        return 7.0
    return 10.0


def get_lateral_sigma(category):
    cat = (category or "").lower()
    if cat in ("driver", "wood", "hybrid"):
        return 20.0
    if cat == "long_iron":
        return 15.0
    if cat == "mid_iron":
        return 12.0
    if cat == "short_iron":
        return 9.0
    if cat == "scoring_wedge":
        return 7.0
    return 10.0


def _expected_strokes_from_distance(distance_yards):
    """Rough strokes baseline for amateurs; used only for relative SG."""
    d = max(1.0, min(distance_yards, 350.0))
    if d <= 50:
        return 1.8 + 0.008 * d
    if d <= 150:
        return 2.0 + 0.0075 * d
    if d <= 250:
        return 2.5 + 0.0056 * d
    return 3.0 + 0.0045 * d

def expected_strokes(distance_yards, surface="fairway", handicap_factor=1.0):
    """
    Handicap + lie aware expected-strokes model.

    - distance_yards: remaining distance to the hole
    - surface: 'tee', 'fairway', 'rough', 'sand', 'recovery', 'green', ...
    - handicap_factor:
        < 1.0  -> stronger player baseline
        = 1.0  -> neutral baseline
        > 1.0  -> higher-handicap baseline
    """
    dist = max(1.0, distance_yards)
    base = _expected_strokes_from_distance(dist)

    s = (surface or "fairway").lower()
    if s in ("tee", "fairway"):
        surface_mult = 1.0
    elif s == "rough":
        surface_mult = 1.06
    elif s in ("sand", "bunker"):
        surface_mult = 1.12
    elif s in ("recovery", "trees", "punch"):
        surface_mult = 1.20
    elif s == "green":
        surface_mult = 0.80
    else:
        surface_mult = 1.0

    # Handicap factor scales difficulty up or down
    return base * surface_mult * handicap_factor


def _trouble_factor(label):
    l = (label or "none").lower()
    if l == "mild":
        return 1.15
    if l == "severe":
        return 1.30
    return 1.0


def _strategy_multiplier(strategy_label):
    s = (strategy_label or STRATEGY_BALANCED).lower()
    if s == "conservative":
        return 0.9
    if s == "aggressive":
        return 1.1
    return 1.0


def _normal_cdf(x, mu=0.0, sigma=1.0):
    if sigma <= 0:
        return 0.5 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


# ============================================================
# Bag building
# ============================================================

def _build_full_bag(driver_speed_mph):
    out = []
    for club, bs, launch, spin, carry, total in FULL_BAG_BASE:
        out.append(
            {
                "Club": club,
                "Ball Speed (mph)": _scale_value(bs, driver_speed_mph),
                "Launch (°)": launch,
                "Spin (rpm)": spin,
                "Carry (yds)": _scale_value(carry, driver_speed_mph),
                "Total (yds)": _scale_value(total, driver_speed_mph),
            }
        )
    return out


def _build_scoring_shots(driver_speed_mph):
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        full_carry = _scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)
        carry = full_carry * SHOT_MULTIPLIERS[shot_type]
        total = carry  # small roll assumed
        shots.append(
            {
                "club": club,
                "shot_type": shot_type,
                "trajectory": traj,
                "carry": carry,
                "total": total,
                "category": "scoring_wedge",
            }
        )
    return shots


def build_all_candidate_shots(driver_speed_mph):
    """
    Returns:
      all_shots_base: list of candidate full and partial shots
      scoring_shots: wedge scoring shots only
      full_bag:      full-club yardage table
    """
    full_bag = _build_full_bag(driver_speed_mph)
    scoring_shots = _build_scoring_shots(driver_speed_mph)
    all_shots = []

    for row in full_bag:
        club = row["Club"]
        carry = row["Carry (yds)"]
        total = row["Total (yds)"]

        if club == "Driver":
            cat = "driver"
        elif club == "3W":
            cat = "wood"
        elif club == "3H":
            cat = "hybrid"
        elif club in ("4i", "5i"):
            cat = "long_iron"
        elif club in ("6i", "7i"):
            cat = "mid_iron"
        elif club in ("8i", "9i"):
            cat = "short_iron"
        else:
            cat = "scoring_wedge"

        all_shots.append(
            {
                "club": club,
                "shot_type": "Full",
                "trajectory": "Stock",
                "carry": carry,
                "total": total,
                "category": cat,
            }
        )

    all_shots.extend(scoring_shots)
    return all_shots, scoring_shots, full_bag


# ============================================================
# Recommendation engine (simplified SG)
# ============================================================

def recommend_shots_with_sg(
    target_total,
    candidates,
    short_trouble_label="None",
    long_trouble_label="None",
    left_trouble_label="None",
    right_trouble_label="None",
    green_firmness_label="Medium",
    strategy_label=STRATEGY_BALANCED,
    start_distance_yards=None,
    start_surface="fairway",
    front_yards=0.0,
    back_yards=0.0,
    skill_factor=1.0,
    pin_lateral_offset=0.0,
    green_width=0.0,
    n_sim=DEFAULT_N_SIM,
    top_n=5,
    sg_profile_factor=1.0,
):
    """
    Rank candidate shots by strokes-gained style value using a more realistic baseline:

      - Baseline = expected_strokes(start_distance, start_surface, handicap_factor)
      - For each shot:
          * We approximate remaining distance by |shot.total - target_total|
          * Compute expected_strokes for that leave from a fairway-like surface
          * Inflate that leave if short/long trouble is present in the miss direction
          * Total exp strokes = 1 (this shot) + leave_exp
          * SG = baseline - total_exp

    This is still an approximation but much closer to true SG logic:
      'How many strokes does this choice cost vs my baseline from here?'
    """
    if start_distance_yards is None:
        start_distance_yards = target_total

    # Baseline SG from current position
    baseline = expected_strokes(
        distance_yards=start_distance_yards,
        surface=start_surface,
        handicap_factor=sg_profile_factor,
    )

    sf = _strategy_multiplier(strategy_label)
    short_factor = _trouble_factor(short_trouble_label)
    long_factor = _trouble_factor(long_trouble_label)

    results = []

    for shot in candidates:
        total = shot["total"]
        diff = total - target_total        # + = long, - = short
        abs_diff = abs(diff)

        # Depth dispersion for this club category
        sigma_depth = get_dispersion_sigma(shot["category"]) * skill_factor
        p_close = _normal_cdf(5.0, diff, sigma_depth) - _normal_cdf(
            -5.0, diff, sigma_depth
        )

        # Approximate remaining distance after the shot
        leave_distance = max(1.0, abs_diff)

        # Assume we are around the green complex / fairway-type surface
        leave_surface = "fairway"

        # Base expected strokes from that remaining distance
        leave_exp = expected_strokes(
            distance_yards=leave_distance,
            surface=leave_surface,
            handicap_factor=sg_profile_factor,
        )

        # Directional trouble multipliers
        trouble_mult = 1.0
        if diff < 0:  # finishes short
            trouble_mult *= short_factor
        elif diff > 0:  # finishes long
            trouble_mult *= long_factor

        # Strategy multiplier (aggressive vs conservative)
        leave_exp *= trouble_mult * sf

        # Total expected score from this decision:
        #   1 stroke for this shot + expected from leave
        exp_strokes = 1.0 + leave_exp

        sg = baseline - exp_strokes

        # ---- Reason text ---- #
        reason_parts = []
        if abs_diff <= 5:
            reason_parts.append("Distances match the plays-like yardage closely.")
        else:
            reason_parts.append("Distances are reasonably close to the plays-like yardage.")

        if trouble_mult > 1.0:
            if diff < 0 and short_trouble_label.lower() != "none":
                reason_parts.append("Short misses are penal here; being short is risky.")
            elif diff > 0 and long_trouble_label.lower() != "none":
                reason_parts.append("Long misses are penal here; being long is risky.")

        if sg > 0.2:
            reason_parts.append("Strong strokes-gained style profile vs your baseline.")
        elif sg < -0.2:
            reason_parts.append("Weaker strokes-gained style profile; consider safer options.")
        else:
            reason_parts.append("Strokes-gained profile is roughly neutral.")

        shot_out = dict(shot)
        shot_out.update(
            {
                "diff": diff,
                "sg": sg,
                "expected_strokes": exp_strokes,
                "p_close": p_close,
                "reason": " ".join(reason_parts),
            }
        )
        results.append(shot_out)

    results.sort(key=lambda s: (-s["sg"], abs(s["diff"])))
    return results[:top_n]

def compute_optimal_carry_for_target(target_total, category):
    """Simple category-based 'ideal carry' offset."""
    cat = (category or "").lower()
    if cat in ("driver", "wood", "hybrid"):
        return target_total - 5.0
    if cat in ("long_iron", "mid_iron"):
        return target_total - 3.0
    return target_total - 1.0


# ============================================================
# Par 3 / 4 / 5 Strategy (simplified)
# ============================================================

def par3_strategy(
    hole_yards,
    candidates,
    skill_factor=1.0,
    green_width=0.0,
    short_trouble_label="None",
    long_trouble_label="None",
    left_trouble_label="None",
    right_trouble_label="None",
    strategy_label=STRATEGY_BALANCED,
    sg_profile_factor=1.0,
    n_sim=DEFAULT_N_SIM,
):
    ranked = recommend_shots_with_sg(
        target_total=hole_yards,
        candidates=candidates,
        short_trouble_label=short_trouble_label,
        long_trouble_label=long_trouble_label,
        left_trouble_label=left_trouble_label,
        right_trouble_label=right_trouble_label,
        strategy_label=strategy_label,
        start_distance_yards=hole_yards,
        start_surface="tee",
        front_yards=0.0,
        back_yards=0.0,
        skill_factor=skill_factor,
        pin_lateral_offset=0.0,
        green_width=green_width,
        n_sim=n_sim,
        top_n=5,
        sg_profile_factor=sg_profile_factor,
    )

    if not ranked:
        return {"best": None, "alternatives": []}

    best = ranked[0]
    sigma_depth = get_dispersion_sigma(best["category"]) * skill_factor
    diff = best["total"] - hole_yards

    def phi(x, mu, sigma):
        return _normal_cdf(x, mu, sigma)

    p_depth_5 = phi(5.0, diff, sigma_depth) - phi(-5.0, diff, sigma_depth)
    p_depth_10 = phi(10.0, diff, sigma_depth) - phi(-10.0, diff, sigma_depth)
    # approximate, ignoring lateral here
    p_within_5 = max(0.0, min(1.0, p_depth_5))
    p_within_10 = max(0.0, min(1.0, p_depth_10))
    p_on_green = p_within_10

    baseline_par3 = 3.1
    sg = baseline_par3 - best["expected_strokes"]

    best_out = dict(best)
    best_out.update(
        {
            "p_on_green": p_on_green,
            "p_within_5": p_within_5,
            "p_within_10": p_within_10,
            "sg": sg,
        }
    )

    return {"best": best_out, "alternatives": ranked[1:4]}


def par4_strategy(
    hole_yards,
    full_bag,
    skill_factor=1.0,
    fairway_width_label="Medium",
    tee_left_trouble_label="None",
    tee_right_trouble_label="None",
    sg_profile_factor=1.0,
):
    """
    Choose best tee club on a par 4 using:

      - Tee club total distance (from full_bag)
      - Fairway width -> miss probability
      - Trouble left/right -> penalty severity
      - expected_strokes(distance, surface, handicap_factor) as baseline
    """
    fw = (fairway_width_label or "Medium").lower()
    if fw == "narrow":
        base_miss = 0.35
    elif fw == "wide":
        base_miss = 0.20
    else:
        base_miss = 0.28

    def exp_strokes(d, surface="fairway"):
        return expected_strokes(d, surface=surface, handicap_factor=sg_profile_factor)

    def trouble_mult(label):
        return _trouble_factor(label)

    options = []

    # Consider realistic tee clubs only
    for row in full_bag:
        club = row["Club"]
        if club not in ("Driver", "3W", "3H", "4i", "5i", "6i"):
            continue

        total = row["Total (yds)"]
        remaining = max(10.0, hole_yards - total)

        # Dispersion on tee shot: longer clubs = wider pattern
        if club == "Driver":
            tee_sigma = 22.0 * skill_factor
        elif club in ("3W", "3H"):
            tee_sigma = 18.0 * skill_factor
        else:
            tee_sigma = 14.0 * skill_factor

        miss_prob = min(0.6, base_miss * (tee_sigma / 18.0))

        # Expected strokes for the approach (from fairway distance 'remaining')
        approach = exp_strokes(remaining, surface="fairway")

        # Tee trouble multiplier (if you miss left/right into something bad)
        t_mult = max(trouble_mult(tee_left_trouble_label),
                     trouble_mult(tee_right_trouble_label))

        # Only the miss-prob portion gets penalized
        approach *= 1.0 + miss_prob * (t_mult - 1.0)

        # Total expected score from tee:
        #   1 stroke for tee shot + approach expectation
        expected_score = 1.0 + approach

        # Rough baseline par-4 scoring for reference; does not affect ranking
        baseline_score = 4.2
        sg_vs_baseline = baseline_score - expected_score

        options.append(
            {
                "tee_club": club,
                "avg_total": total,
                "remaining_yards": remaining,
                "expected_score": expected_score,
                "sg_vs_baseline": sg_vs_baseline,
                "miss_prob": miss_prob,
            }
        )

    if not options:
        return {"best": None, "options": []}

    options.sort(key=lambda x: x["expected_score"])
    best = options[0]
    return {"best": best, "options": options}

def par5_strategy(
    hole_yards,
    full_bag,
    skill_factor=1.0,
    fairway_width_label="Medium",
    tee_left_trouble_label="None",
    tee_right_trouble_label="None",
    sg_profile_factor=1.0,
):
    """
    Simple par-5 logic:

      1) Choose best tee club using par4_strategy logic.
      2) Given remaining distance, compare:
           - Layup to ~100 yards (three-shot plan)
           - Go for it in two (if remaining <= ~260)

      Uses expected_strokes(...) for both legs.
    """
    par4_res = par4_strategy(
        hole_yards=hole_yards,
        full_bag=full_bag,
        skill_factor=skill_factor,
        fairway_width_label=fairway_width_label,
        tee_left_trouble_label=tee_left_trouble_label,
        tee_right_trouble_label=tee_right_trouble_label,
        sg_profile_factor=sg_profile_factor,
    )
    best_tee = par4_res.get("best")
    if not best_tee:
        return {
            "best_tee": None,
            "strategy": "Unknown",
            "expected_score": None,
            "remaining_after_tee": None,
            "layup_score": None,
            "layup_target": None,
            "go_for_it_score": None,
        }

    remaining = best_tee["remaining_yards"]

    def exp_strokes(d, surface="fairway"):
        return expected_strokes(d, surface=surface, handicap_factor=sg_profile_factor)

    # Three-shot (layup) plan
    layup_target = 100.0
    layup_dist = max(0.0, remaining - layup_target)
    layup_approach = exp_strokes(layup_dist, surface="fairway")
    wedge_approach = exp_strokes(layup_target, surface="fairway")
    layup_score = 1.0 + layup_approach + wedge_approach  # many approximations here

    # Two-shot (go-for-it) plan, only if reachable
    go_for_it_score = None
    if remaining <= 260:
        go_approach = exp_strokes(remaining, surface="fairway")
        go_for_it_score = 1.0 + go_approach

    # Rough baseline par-5 scoring for reference
    baseline_score = 5.2

    if go_for_it_score is None or layup_score + 0.05 < go_for_it_score:
        strategy = "Three-shot (layup) plan"
        expected_score = layup_score
    else:
        strategy = "Aggressive two-shot plan"
        expected_score = go_for_it_score

    return {
        "best_tee": best_tee,
        "strategy": strategy,
        "expected_score": expected_score,
        "remaining_after_tee": remaining,
        "layup_score": layup_score,
        "layup_target": layup_target,
        "go_for_it_score": go_for_it_score,
    }



# ============================================================
# Tournament Prep helpers
# ============================================================

def generate_random_scenario():
    """
    Random practice scenario for Tournament Prep Mode.
    Returns dict with raw_yards, wind_dir, wind_strength, elevation,
    lie, temp_f, pin_depth, green_firmness.
    Wind direction/strength are kept consistent:
      - Either 'None' / 'None'
      - Or (Into/Down/Cross) with (Light/Medium/Heavy)
    """
    raw_yards = random.randint(110, 220)

    # ~30% of the time: truly calm
    if random.random() < 0.3:
        wind_dir = "None"
        wind_strength = "None"
    else:
        wind_dir = random.choice(["Into", "Down", "Cross"])
        wind_strength = random.choice(["Light", "Medium", "Heavy"])

    elevation = random.choice(
        ["Flat", "Slight Uphill", "Moderate Uphill",
         "Slight Downhill", "Moderate Downhill"]
    )
    lie = random.choice(["Good", "Ok", "Bad"])
    temp_f = random.choice([50, 55, 60, 65, 70, 75, 80, 85, 90])
    pin_depth = random.choice(["Front", "Middle", "Back"])
    green_firmness = random.choice(["Soft", "Medium", "Firm"])

    return {
        "raw_yards": raw_yards,
        "wind_dir": wind_dir,
        "wind_strength": wind_strength,
        "elevation": elevation,
        "lie": lie,
        "temp_f": temp_f,
        "pin_depth": pin_depth,
        "green_firmness": green_firmness,
    }
