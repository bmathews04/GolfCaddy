import math
import random

# ------------------------------------------------------------
# Constants & Baselines
# ------------------------------------------------------------

BASELINE_DRIVER_SPEED = 100.0  # mph

# Full-swing wedge carries at 100 mph (center values)
FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW":  92,
    "LW":  78,
}

# Full bag baseline at 100 mph driver speed
# club, ball_speed, launch, spin, carry_center, total_center
FULL_BAG_BASE = [
    ("Driver", 148, 13.0,  2500, 233, 253),
    ("3W",     140, 14.5,  3300, 216, 233),
    ("3H",     135, 16.0,  3900, 202, 220),
    ("4i",     128, 14.5,  4600, 182, 194),
    ("5i",     122, 15.5,  5000, 172, 185),
    ("6i",     116, 17.0,  5400, 162, 172),
    ("7i",     110, 18.5,  6200, 151, 161),
    ("8i",     104, 20.5,  7000, 139, 149),
    ("9i",      98, 23.0,  7800, 127, 137),
    ("PW",      92, 28.0,  8500, 118, 124),
    ("GW",      86, 30.0,  9000, 104, 110),
    ("SW",      81, 32.0,  9500,  89,  95),
    ("LW",      75, 34.0, 10500,  75,  81),
]

# Shot-type multipliers
SHOT_MULTIPLIERS = {
    "Full":        1.00,
    "Choke-Down":  0.94,
    "3/4":         0.80,
    "1/2":         0.60,
    "1/4":         0.40,
}

# Wedge trajectory profiles (simplified)
WEDGE_PROFILES = {
    "PW": {
        "Full": "Medium-High",
    },
    "GW": {
        "Full": "Medium-High",
    },
    "SW": {
        "Full": "High",
    },
    "LW": {
        "Full": "High",
    },
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


# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def _scale_value(base_value: float, driver_speed_mph: float) -> float:
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


def adjust_for_wind(target: float, wind_dir: str, wind_strength_label: str) -> float:
    label = wind_strength_label.lower().strip()
    wind_mph = WIND_STRENGTH_MAP.get(label, 0)

    scale = target / 150.0
    scale = max(0.5, min(scale, 1.2))

    wd = wind_dir.lower()
    adjusted = target

    if wd == "into":
        adjusted += wind_mph * 0.9 * scale
    elif wd == "down":
        adjusted -= wind_mph * 0.4 * scale
    elif wd == "cross":
        adjusted += wind_mph * 0.1 * scale

    return adjusted


def apply_elevation(target: float, elevation_label: str) -> float:
    label = elevation_label.lower().strip()
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


def apply_lie(target: float, lie_label: str) -> float:
    lie = lie_label.lower().strip()
    if lie == "good":
        mult = 1.00
    elif lie in ("ok", "okay"):
        mult = 1.05
    elif lie == "bad":
        mult = 1.12
    else:
        mult = 1.00
    return target * mult


# ------------------------------------------------------------
# Dispersion and SG helpers
# ------------------------------------------------------------

def get_dispersion_sigma(category: str) -> float:
    """Approximate depth dispersion (1σ, yards)."""
    cat = category.lower()
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


def get_lateral_sigma(category: str) -> float:
    """Approximate lateral dispersion (1σ, yards)."""
    cat = category.lower()
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


def _expected_strokes_from_distance(distance_yards: float) -> float:
    """
    Very rough baseline: expected strokes to hole out from given distance,
    assuming fairway/normal conditions. Good enough for relative SG comparisons.
    """
    d = max(1.0, min(distance_yards, 350.0))
    # piecewise linear-ish: 0-50, 50-150, 150-250, 250-350
    if d <= 50:
        # ~2.2 at 50
        return 1.8 + 0.008 * d
    if d <= 150:
        # ~3.0 at 150
        return 2.0 + 0.0075 * d
    if d <= 250:
        # ~3.9 at 250
        return 2.5 + 0.0056 * d
    # 250-350 ~4.5-5.0
    return 3.0 + 0.0045 * d


def _trouble_factor(label: str) -> float:
    l = (label or "none").lower()
    if l == "mild":
        return 1.15
    if l == "severe":
        return 1.30
    return 1.0


def _strategy_multiplier(strategy_label: str) -> float:
    s = (strategy_label or STRATEGY_BALANCED).lower()
    if s == "conservative":
        return 0.9
    if s == "aggressive":
        return 1.1
    return 1.0


def _normal_cdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    if sigma <= 0:
        return 0.5 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


# ------------------------------------------------------------
# Bag building
# ------------------------------------------------------------

def _build_full_bag(driver_speed_mph: float):
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


def _build_scoring_shots(driver_speed_mph: float):
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        full_carry = _scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)
        carry = full_carry * SHOT_MULTIPLIERS[shot_type]
        total = carry  # wedges roll very little in this simplified model
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


def build_all_candidate_shots(driver_speed_mph: float):
    """
    Returns:
      all_shots_base: list of candidate shots (dict)
      scoring_shots: list for tables
      full_bag:      yardage table for full clubs
    """
    full_bag = _build_full_bag(driver_speed_mph)
    scoring_shots = _build_scoring_shots(driver_speed_mph)

    all_shots = []

    # Full swings from full_bag
    for row in full_bag:
        club = row["Club"]
        carry = row["Carry (yds)"]
        total = row["Total (yds)"]
        if club == "Driver":
            cat = "driver"
        elif club in ("3W",):
            cat = "wood"
        elif club in ("3H",):
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

    # Add wedge scoring shots
    all_shots.extend(scoring_shots)

    return all_shots, scoring_shots, full_bag


# ------------------------------------------------------------
# Core recommendation engine
# ------------------------------------------------------------

def recommend_shots_with_sg(
    target_total: float,
    candidates,
    short_trouble_label: str = "None",
    long_trouble_label: str = "None",
    left_trouble_label: str = "None",
    right_trouble_label: str = "None",
    green_firmness_label: str = "Medium",
    strategy_label: str = STRATEGY_BALANCED,
    start_distance_yards: float = None,
    start_surface: str = "fairway",
    front_yards: float = 0.0,
    back_yards: float = 0.0,
    skill_factor: float = 1.0,
    pin_lateral_offset: float = 0.0,
    green_width: float = 0.0,
    n_sim: int = DEFAULT_N_SIM,
    top_n: int = 5,
    sg_profile_factor: float = 1.0,
):
    """
    Simplified SG-based ranking:
      - Penalizes distance error from plays-like yardage
      - Adds extra penalty when error points toward trouble (short/long)
      - Uses very rough expected-strokes model, scaled by sg_profile_factor
    """
    if start_distance_yards is None:
        start_distance_yards = target_total

    baseline = _expected_strokes_from_distance(start_distance_yards) / sg_profile_factor

    results = []
    sf = _strategy_multiplier(strategy_label)
    short_factor = _trouble_factor(short_trouble_label)
    long_factor = _trouble_factor(long_trouble_label)

    for shot in candidates:
        total = shot["total"]
        diff = total - target_total
        abs_diff = abs(diff)

        # basic dispersion estimate -> how often we miss more than X
        sigma_depth = get_dispersion_sigma(shot["category"]) * skill_factor
        # prob of finishing within 5 yds of target (depth only)
        p_close = _normal_cdf(5.0, diff, sigma_depth) - _normal_cdf(-5.0, diff, sigma_depth)

        # effective miss penalty
        if diff < 0:  # likely short
            miss_penalty = short_factor
        else:
            miss_penalty = long_factor

        # expected strokes from resulting leave distance (approx)
        expected_from_leave = _expected_strokes_from_distance(max(20.0, abs_diff))

        # combine into a simple expected strokes number:
        # baseline + (miss_penalty * error term) - (benefit from p_close)
        exp_strokes = baseline + (abs_diff / 50.0) * miss_penalty * sf + (1.0 - p_close) * 0.1
        sg = baseline - exp_strokes  # positive = better

        reason = []
        reason.append(f"Distances match the plays-like yardage {'closely' if abs_diff <= 5 else 'reasonably well'}.")
        if miss_penalty > 1.0:
            if diff < 0 and short_trouble_label.lower() != "none":
                reason.append("Short misses are penal here; this option risks leaving the ball short into trouble.")
            elif diff > 0 and long_trouble_label.lower() != "none":
                reason.append("Long misses are penal here; this option risks flying into trouble long.")
        else:
            reason.append("Misses in this direction are relatively safe compared with the alternative side.")

        if sg > 0.2:
            reason.append("Strong strokes-gained profile compared with a typical shot from here.")
        elif sg < -0.2:
            reason.append("Weaker strokes-gained profile; consider a safer alternative if available.")
        else:
            reason.append("Strokes-gained profile is roughly neutral vs. a typical shot from here.")

        shot_out = dict(shot)
        shot_out.update(
            {
                "diff": diff,
                "sg": sg,
                "expected_strokes": exp_strokes,
                "p_close": p_close,
                "reason": " ".join(reason),
            }
        )
        results.append(shot_out)

    # Sort primarily by SG descending, then by absolute diff
    results.sort(key=lambda s: (-s["sg"], abs(s["diff"])))
    return results[:top_n]


def compute_optimal_carry_for_target(target_total: float, category: str) -> float:
    """
    Placeholder 'perfect carry' calculation. For now returns target_total minus
    a small bias based on category.
    """
    cat = category.lower()
    if cat in ("driver", "wood", "hybrid"):
        return target_total - 5.0
    if cat in ("long_iron", "mid_iron"):
        return target_total - 3.0
    return target_total - 1.0


# ------------------------------------------------------------
# Par 3 / Par 4 / Par 5 Strategy Helpers
# ------------------------------------------------------------

def par3_strategy(
    hole_yards: float,
    candidates,
    skill_factor: float = 1.0,
    green_width: float = 0.0,
    short_trouble_label: str = "None",
    long_trouble_label: str = "None",
    left_trouble_label: str = "None",
    right_trouble_label: str = "None",
    strategy_label: str = STRATEGY_BALANCED,
    sg_profile_factor: float = 1.0,
    n_sim: int = DEFAULT_N_SIM,
):
    """
    Use the same recommendation engine but treat the shot as a tee shot on a Par 3.
    Returns dict with 'best' and 'alternatives'.
    """
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
        green_width=green_width,
        skill_factor=skill_factor,
        n_sim=n_sim,
        sg_profile_factor=sg_profile_factor,
        top_n=5,
    )

    if not ranked:
        return {"best": None, "alternatives": []}

    best = ranked[0]

    # Approximate probabilities based on dispersion
    sigma_depth = get_dispersion_sigma(best["category"]) * skill_factor
    sigma_lat = get_lateral_sigma(best["category"]) * skill_factor
    diff = best["total"] - hole_yards

    # radial approximations
    p_within_5 = (
        _normal_cdf(5.0, diff, sigma_depth) - _normal_cdf(-5.0, diff, sigma_depth)
    ) * (
        _normal_cdf(5.0, 0.0, sigma_lat) - _normal_cdf(-5.0, 0.0, sigma_lat)
    )

    p_within_10 = (
        _normal_cdf(10.0, diff, sigma_depth) - _normal_cdf(-10.0, diff, sigma_depth)
    ) * (
        _normal_cdf(10.0, 0.0, sigma_lat) - _normal_cdf(-10.0, 0.0, sigma_lat)
    )

    if green_width > 0:
        half_w = green_width / 2.0
        p_on_lat = _normal_cdf(half_w, 0.0, sigma_lat) - _normal_cdf(-half_w, 0.0, sigma_lat)
        p_on_depth = _normal_cdf(5.0, diff, sigma_depth) - _normal_cdf(-5.0, diff, sigma_depth)
        p_on_green = max(0.0, min(1.0, p_on_lat * p_on_depth))
    else:
        p_on_green = p_within_10

    best_out = dict(best)
    best_out.update(
        {
            "p_on_green": p_on_green,
            "p_within_5": p_within_5,
            "p_within_10": p_within_10,
        }
    )

    # compute SG vs generic par-3 baseline
    baseline_par3 = 3.1  # rough amateur baseline
    best_out["sg"] = baseline_par3 - best["expected_strokes"]

    # for alternatives we just keep top few from ranked
    alts = ranked[1:4]

    return {
        "best": best_out,
        "alternatives": alts,
    }


def par4_strategy(
    hole_yards: float,
    full_bag,
    skill_factor: float = 1.0,
    fairway_width_label: str = "Medium",
    tee_left_trouble_label: str = "None",
    tee_right_trouble_label: str = "None",
    sg_profile_factor: float = 1.0,
):
    """
    Very simplified Par 4 strategy:
      - Evaluate each tee club from Driver down to ~6i.
      - Compute remaining distance and expected score (tee + approach).
    """
    # Map fairway width -> miss probability
    fw = fairway_width_label.lower()
    if fw == "narrow":
        base_miss = 0.35
    elif fw == "wide":
        base_miss = 0.20
    else:
        base_miss = 0.28

    options = []
    for row in full_bag:
        club = row["Club"]
        if club not in ("Driver", "3W", "3H", "4i", "5i", "6i"):
            continue

        total = row["Total (yds)"]
        remaining = max(10.0, hole_yards - total)

        # tee dispersion: driver widest
        if club == "Driver":
            tee_sigma = 22.0 * skill_factor
        elif club in ("3W", "3H"):
            tee_sigma = 18.0 * skill_factor
        else:
            tee_sigma = 14.0 * skill_factor

        miss_prob = min(0.6, base_miss * (tee_sigma / 18.0))

        exp_approach = _expected_strokes_from_distance(remaining)
        # penalty for missing fairway
        trouble_factor = max(_trouble_factor(tee_left_trouble_label),
                             _trouble_factor(tee_right_trouble_label))
        exp_approach *= (1.0 + miss_prob * (trouble_factor - 1.0))

        # tee shot itself is one stroke; simple SG vs baseline
        expected_score = 1.0 + exp_approach
        baseline_score = 4.2  # generic amateur par-4 scoring baseline
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
    hole_yards: float,
    full_bag,
    skill_factor: float = 1.0,
    fairway_width_label: str = "Medium",
    tee_left_trouble_label: str = "None",
    tee_right_trouble_label: str = "None",
    sg_profile_factor: float = 1.0,
):
    """
    Simplified Par 5 strategy:
      - Choose tee club similar to Par 4
      - Decide between layup vs go-for-it based on remaining distance
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
        return {"best_tee": None, "strategy": "Unknown", "expected_score": None,
                "remaining_after_tee": None, "layup_score": None,
                "layup_target": None, "go_for_it_score": None}

    remaining = best_tee["remaining_yards"]

    # Layup target ~90-110 yards
    layup_target = 100.0
    layup_dist = max(0.0, remaining - layup_target)
    layup_approach = _expected_strokes_from_distance(layup_dist)
    wedge_approach = _expected_strokes_from_distance(layup_target)

    layup_score = 1.0 + layup_approach + wedge_approach  # tee + layup + wedge

    # Go-for-it option if remaining <= 260
    go_for_it_score = None
    if remaining <= 260:
        go_approach = _expected_strokes_from_distance(remaining)
        go_for_it_score = 1.0 + go_approach  # tee + long shot

    # Baseline par-5 scoring
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
