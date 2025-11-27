import math
import random

# ============================================================
# Constants & Baselines
# ============================================================

BASELINE_DRIVER_SPEED = 100.0  # mph

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


def _apply_temperature(target, temp_f, baseline_temp_f=75.0):
    """
    Very simple temperature adjustment:
    each 10°F colder than baseline reduces distance ~2.5 yds at 150y,
    scaled by shot length.
    """
    if temp_f is None:
        return target
    delta = temp_f - baseline_temp_f  # negative = colder
    adj = (delta / 10.0) * 2.5 * (target / 150.0)
    return target + adj


def calculate_plays_like_yardage(
    raw_yards,
    wind_dir,
    wind_strength_label,
    elevation_label,
    lie_label,
    tendency_label="Neutral",
    temp_f=75.0,
    baseline_temp_f=75.0,
):
    """Shared plays-like calculator (used by Tournament Prep)."""
    val = raw_yards
    val = adjust_for_wind(val, wind_dir, wind_strength_label)
    val = apply_elevation(val, elevation_label)
    val = apply_lie(val, lie_label)
    val = _apply_temperature(val, temp_f, baseline_temp_f)

    tendency_label = tendency_label or "Neutral"
    if tendency_label == "Usually Short":
        val += 3.0
    elif tendency_label == "Usually Long":
        val -= 3.0

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
    if start_distance_yards is None:
        start_distance_yards = target_total

    baseline = _expected_strokes_from_distance(start_distance_yards) / sg_profile_factor
    sf = _strategy_multiplier(strategy_label)
    short_factor = _trouble_factor(short_trouble_label)
    long_factor = _trouble_factor(long_trouble_label)

    results = []

    for shot in candidates:
        total = shot["total"]
        diff = total - target_total
        abs_diff = abs(diff)

        sigma_depth = get_dispersion_sigma(shot["category"]) * skill_factor
        p_close = _normal_cdf(5.0, diff, sigma_depth) - _normal_cdf(
            -5.0, diff, sigma_depth
        )

        if diff < 0:
            miss_penalty = short_factor
        else:
            miss_penalty = long_factor

        expected_from_leave = _expected_strokes_from_distance(max(20.0, abs_diff))
        # Very simple expected strokes model
        exp_strokes = baseline + (abs_diff / 50.0) * miss_penalty * sf

        sg = baseline - exp_strokes

        reason_parts = []
        if abs_diff <= 5:
            reason_parts.append("Distances match the plays-like yardage closely.")
        else:
            reason_parts.append("Distances are reasonably close to the plays-like yardage.")
        if miss_penalty > 1.0:
            if diff < 0 and short_trouble_label.lower() != "none":
                reason_parts.append("Short misses are penal here; being short is risky.")
            elif diff > 0 and long_trouble_label.lower() != "none":
                reason_parts.append("Long misses are penal here; being long is risky.")
        if sg > 0.2:
            reason_parts.append("Strong strokes-gained style profile vs a typical shot.")
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
    fw = (fairway_width_label or "Medium").lower()
    if fw == "narrow":
        base_miss = 0.35
    elif fw == "wide":
        base_miss = 0.20
    else:
        base_miss = 0.28

    def exp_strokes(d):
        return _expected_strokes_from_distance(d)

    def trouble_mult(label):
        return _trouble_factor(label)

    options = []
    for row in full_bag:
        club = row["Club"]
        if club not in ("Driver", "3W", "3H", "4i", "5i", "6i"):
            continue

        total = row["Total (yds)"]
        remaining = max(10.0, hole_yards - total)

        if club == "Driver":
            tee_sigma = 22.0 * skill_factor
        elif club in ("3W", "3H"):
            tee_sigma = 18.0 * skill_factor
        else:
            tee_sigma = 14.0 * skill_factor

        miss_prob = min(0.6, base_miss * (tee_sigma / 18.0))

        approach = exp_strokes(remaining)
        t_mult = max(trouble_mult(tee_left_trouble_label),
                     trouble_mult(tee_right_trouble_label))
        approach *= 1.0 + miss_prob * (t_mult - 1.0)

        expected_score = 1.0 + approach  # tee + rest
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

    def exp_strokes(d):
        return _expected_strokes_from_distance(d)

    layup_target = 100.0
    layup_dist = max(0.0, remaining - layup_target)
    layup_approach = exp_strokes(layup_dist)
    wedge_approach = exp_strokes(layup_target)
    layup_score = 1.0 + layup_approach + wedge_approach  # tee + layup + wedge

    go_for_it_score = None
    if remaining <= 260:
        go_approach = exp_strokes(remaining)
        go_for_it_score = 1.0 + go_approach  # tee + long shot

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
    """
    raw_yards = random.randint(110, 220)
    wind_dir = random.choice(["None", "Into", "Down", "Cross"])
    wind_strength = random.choice(["None", "Light", "Medium", "Heavy"])
    elevation = random.choice(
        ["Flat", "Slight Uphill", "Moderate Uphill", "Slight Downhill", "Moderate Downhill"]
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
