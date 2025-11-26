import math
from typing import List, Dict, Tuple

import numpy as np

# -------------------- CONSTANTS -------------------- #

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
FULL_BAG_BASE: List[Tuple[str, float, float, int, float, float]] = [
    ("Driver", 148, 13.0, 2500, 233, 253),
    ("3W", 140, 14.5, 3300, 216, 233),
    ("3H", 135, 16.0, 3900, 202, 220),
    ("4i", 128, 14.5, 4600, 182, 194),
    ("5i", 122, 15.5, 5000, 172, 185),
    ("6i", 116, 17.0, 5400, 162, 172),
    ("7i", 110, 18.5, 6200, 151, 161),
    ("8i", 104, 20.5, 7000, 139, 149),
    ("9i", 98, 23.0, 7800, 127, 137),
    ("PW", 92, 28.0, 8500, 118, 124),
    ("GW", 86, 30.0, 9000, 104, 110),
    ("SW", 81, 32.0, 9500, 89, 95),
    ("LW", 75, 34.0, 10500, 75, 81),
]

# Shot-type multipliers
SHOT_MULTIPLIERS = {
    "Full": 1.00,
    "Choke-Down": 0.94,
    "3/4": 0.80,
    "1/2": 0.60,
    "1/4": 0.40,
}

# Scoring shots: (club, shot type, trajectory)
SCORING_DEFS = [
    ("PW", "Full", "Medium-High"),
    ("PW", "Choke-Down", "Medium"),
    ("PW", "3/4", "Medium"),
    ("SW", "Full", "High"),
    ("LW", "Full", "High"),
    ("SW", "3/4", "Medium-High"),
    ("PW", "1/2", "Medium-Low"),
    ("LW", "3/4", "Medium"),
    ("SW", "1/2", "Medium-Low"),
    ("PW", "1/4", "Low"),
    ("LW", "1/2", "Medium-Low"),
    ("GW", "1/4", "Low"),
    ("SW", "1/4", "Low"),
    ("LW", "1/4", "Low"),
    ("GW", "Full", "Medium-High"),
    ("GW", "Choke-Down", "Medium"),
    ("GW", "3/4", "Medium"),
    ("GW", "1/2", "Medium-Low"),
]

# Simplified wind strengths (mph)
WIND_STRENGTH_MAP = {
    "none": 0,
    "light": 5,
    "medium": 10,
    "heavy": 20,
}

# Strategy labels
STRATEGY_BALANCED = "Balanced"
STRATEGY_CONSERVATIVE = "Conservative"
STRATEGY_AGGRESSIVE = "Aggressive"

# Default number of Monte Carlo simulations per candidate
DEFAULT_N_SIM = 800


# -------------------- BASIC SCALING -------------------- #

def _scale_value(base_value: float, driver_speed_mph: float) -> float:
    """Scale a baseline value linearly with driver speed."""
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


# -------------------- PUBLIC WIND / LIE / ELEVATION -------------------- #

def adjust_for_wind(target: float, wind_dir: str, wind_strength_label: str) -> float:
    """
    Tuned wind model:
      - Into: hurts more than downwind helps
      - Down: helps, but less than into hurts
      - Cross: tiny safety bump so you do not under-club
      - Short shots less affected than long shots
    """
    label = wind_strength_label.lower().strip()
    wind_mph = WIND_STRENGTH_MAP.get(label, 0)

    # Scale wind effect based on shot length
    scale = target / 150.0
    scale = max(0.5, min(scale, 1.2))

    adjusted = target
    wd = wind_dir.lower()

    if wd == "into":
        adjusted += wind_mph * 0.9 * scale
    elif wd == "down":
        adjusted -= wind_mph * 0.4 * scale
    elif wd == "cross":
        adjusted += wind_mph * 0.1 * scale

    return adjusted


def apply_elevation(target: float, elevation_label: str) -> float:
    """
    Elevation categories -> yardage adjustment:
      - Flat: 0 yds
      - Slight Uphill: +5 yds
      - Moderate Uphill: +10 yds
      - Slight Downhill: -5 yds
      - Moderate Downhill: -10 yds
    """
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
    """Adjust distance based on lie: good / ok / bad."""
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


# -------------------- DISPERSION MODEL -------------------- #

def get_dispersion_sigma(category: str) -> float:
    """
    Return 1D distance dispersion (std dev in yards) for a given category.
    This is a simple, tour-informed but not exact model.
    """
    cat = category.lower()
    if cat == "scoring_wedge":
        return 5.0
    if cat == "short_iron":
        return 7.0
    if cat == "mid_iron":
        return 8.0
    # long irons, hybrids, woods, driver
    return 10.0


def _club_category(club: str) -> str:
    """Map a club name to a dispersion category."""
    if club in ["PW", "GW", "SW", "LW"]:
        return "scoring_wedge"
    if club in ["9i", "8i"]:
        return "short_iron"
    if club in ["7i", "6i", "5i"]:
        return "mid_iron"
    return "long"


# -------------------- BAG & SHOT GENERATION -------------------- #

def _build_full_bag(driver_speed_mph: float) -> List[Dict]:
    """
    Full bag distances for given driver speed.
    Returns a list of dicts with keys:
      Club, Ball Speed (mph), Launch (°), Spin (rpm), Carry (yds), Total (yds)
    """
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


def _build_scoring_shots(driver_speed_mph: float) -> List[Dict]:
    """
    All scoring shots (PW–LW + shot types) for given driver speed.
    Returns list of dicts with: club, shot_type, trajectory, carry, total.
    """
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        full_carry = _scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)
        carry = full_carry * SHOT_MULTIPLIERS[shot_type]
        # For scoring shots, assume total is roughly same as carry (high, soft)
        total = carry
        shots.append(
            {
                "club": club,
                "shot_type": shot_type,
                "trajectory": traj,
                "carry": carry,
                "total": total,
                "category": _club_category(club),
            }
        )
    return shots


def build_all_candidate_shots(driver_speed_mph: float):
    """
    Public entrypoint used by the app.

    Returns:
      all_shots_base: list[dict] of all candidate shots for the engine
      scoring_shots: list[dict] of wedge/scoring shots (for table)
      full_bag:      list[dict] of full-bag yardages (for tables/range)
    """
    full_bag = _build_full_bag(driver_speed_mph)
    scoring_shots = _build_scoring_shots(driver_speed_mph)

    # Build candidates:
    #  - All full-swing clubs from full_bag
    #  - All scoring shots (partials, etc.)
    all_shots: List[Dict] = []

    # Full-swing clubs (treat as "Full" shot type)
    for row in full_bag:
        club = row["Club"]
        cat = _club_category(club)
        all_shots.append(
            {
                "club": club,
                "shot_type": "Full",
                "trajectory": "Stock",
                "category": cat,
                "carry": row["Carry (yds)"],
                "total": row["Total (yds)"],
            }
        )

    # Add scoring wedges (these add partial swings for PW/GW/SW/LW)
    all_shots.extend(scoring_shots)

    return all_shots, scoring_shots, full_bag


# -------------------- STROKES GAINED CORE -------------------- #

# Very simple distance -> expected strokes mapping (approximate).
# This is not a perfect PGA Tour table, but reasonable and smooth.
_DISTANCE_STROKES_TABLE = [
    (0.0, 1.00),
    (3.0, 1.10),
    (8.0, 1.30),
    (20.0, 1.70),
    (40.0, 1.90),
    (80.0, 2.20),
    (120.0, 2.50),
    (180.0, 2.90),
    (230.0, 3.20),
    (280.0, 3.50),
    (360.0, 3.90),
]


def _interp_expected_strokes(distance_yards: float) -> float:
    """Linear interpolation over the distance-strokes table."""
    d = max(0.0, float(distance_yards))
    table = _DISTANCE_STROKES_TABLE

    if d <= table[0][0]:
        return table[0][1]
    if d >= table[-1][0]:
        return table[-1][1]

    for i in range(len(table) - 1):
        d0, s0 = table[i]
        d1, s1 = table[i + 1]
        if d0 <= d <= d1:
            if d1 == d0:
                return s0
            t = (d - d0) / (d1 - d0)
            return s0 + t * (s1 - s0)

    return table[-1][1]


def _strategy_penalty_multiplier(strategy_label: str) -> float:
    """How harshly to punish trouble outcomes based on strategy."""
    lab = strategy_label or STRATEGY_BALANCED
    if lab == STRATEGY_CONSERVATIVE:
        return 1.3
    if lab == STRATEGY_AGGRESSIVE:
        return 0.7
    return 1.0


def _trouble_severity(label: str) -> float:
    """
    Convert 'None' / 'Mild' / 'Severe' into additional strokes per bad miss, baseline.
    """
    l = (label or "None").lower()
    if l == "mild":
        return 0.4
    if l == "severe":
        return 1.0
    return 0.0


def _simulate_candidate_sg(
    candidate: Dict,
    target_total: float,
    short_trouble_label: str,
    long_trouble_label: str,
    strategy_label: str,
    start_distance_yards: float,
    skill_factor: float,
    n_sim: int,
) -> Tuple[float, float]:
    """
    Monte Carlo strokes-gained estimate for a single candidate shot.

    Returns:
      (expected_strokes_after, strokes_gained)
    """
    cat = candidate["category"]
    sigma_base = get_dispersion_sigma(cat)
    sigma_eff = max(0.1, sigma_base * skill_factor)

    # Mean error (positive = long, negative = short) in yards
    mu = candidate["total"] - target_total

    # Sample shot outcomes in 1D (along line to target)
    errors = np.random.normal(loc=mu, scale=sigma_eff, size=n_sim)

    # Distance remaining is abs(error)
    remaining = np.abs(errors)

    # Base strokes after shot (1 stroke to hit, plus expected strokes from remaining)
    strokes_from_remaining = np.array(
        [_interp_expected_strokes(d) for d in remaining]
    )
    strokes_samples = 1.0 + strokes_from_remaining

    # Trouble penalties for big misses short/long
    short_severity = _trouble_severity(short_trouble_label)
    long_severity = _trouble_severity(long_trouble_label)
    strat_mult = _strategy_penalty_multiplier(strategy_label)

    if short_severity > 0.0:
        # Consider "bad short" if > 5 yards short of target
        short_mask = errors < -5.0
        strokes_samples[short_mask] += short_severity * strat_mult

    if long_severity > 0.0:
        # Consider "bad long" if > 5 yards long of target
        long_mask = errors > 5.0
        strokes_samples[long_mask] += long_severity * strat_mult

    expected_after = float(strokes_samples.mean())

    # Baseline from current distance (before this shot)
    baseline_from_here = _interp_expected_strokes(start_distance_yards)

    # Strokes gained = baseline - expected actual
    sg = baseline_from_here - expected_after
    return expected_after, sg


def recommend_shots_with_sg(
    target_total: float,
    candidates: List[Dict],
    short_trouble_label: str,
    long_trouble_label: str,
    green_firmness_label: str,
    strategy_label: str,
    start_distance_yards: float,
    start_surface: str,
    front_yards: float,
    back_yards: float,
    skill_factor: float,
    pin_lateral_offset: float,
    green_width: float,
    n_sim: int = DEFAULT_N_SIM,
    top_n: int = 10,
) -> List[Dict]:
    """
    Rank candidate shots by strokes gained, returning up to top_n.

    Many of the arguments (green_firmness_label, front/back, lateral) are
    accepted for future expansion, but the current model focuses on
    along-the-line distance + simple short/long trouble.
    """
    # Filter candidates to reasonable window around target to keep noise down
    filtered: List[Dict] = []
    for c in candidates:
        # basic sanity: ignore very short chips or huge overclubs for now
        if c["total"] < 0.5 * target_total:
            continue
        if c["total"] > 1.5 * target_total:
            continue
        filtered.append(c)

    evaluated: List[Dict] = []
    for c in filtered:
        diff = c["total"] - target_total
        expected_after, sg = _simulate_candidate_sg(
            candidate=c,
            target_total=target_total,
            short_trouble_label=short_trouble_label,
            long_trouble_label=long_trouble_label,
            strategy_label=strategy_label,
            start_distance_yards=start_distance_yards,
            skill_factor=skill_factor,
            n_sim=n_sim,
        )

        # Legacy "score": tighter to target is better, punish large misses
        legacy_score = -abs(diff) - 0.2 * get_dispersion_sigma(c["category"])

        # Reason string for UI
        reason_parts = []
        if abs(diff) <= 5:
            reason_parts.append("Distances match the plays-like yardage closely.")
        elif diff < -5:
            reason_parts.append("Tends to finish a bit short of the plays-like yardage.")
        else:
            reason_parts.append("Tends to finish a bit past the plays-like yardage.")

        if short_trouble_label != "None" or long_trouble_label != "None":
            if short_trouble_label != "None" and diff >= -5:
                reason_parts.append("Keeps most of the miss pattern away from short trouble.")
            if long_trouble_label != "None" and diff <= 5:
                reason_parts.append("Limits the chance of bringing long trouble directly into play.")

        if sg > 0.15:
            reason_parts.append("Strong strokes-gained profile compared with a typical shot from here.")
        elif sg > 0.05:
            reason_parts.append("Slightly positive strokes-gained expectation from this position.")
        elif sg < -0.15:
            reason_parts.append("Higher-risk or lower-value outcome on average compared with safer options.")

        reason = " ".join(reason_parts)

        evaluated.append(
            {
                "club": c["club"],
                "shot_type": c["shot_type"],
                "trajectory": c.get("trajectory", "Stock"),
                "category": c["category"],
                "carry": c["carry"],
                "total": c["total"],
                "diff": diff,
                "score": legacy_score,
                "expected_strokes": expected_after,
                "sg": sg,
                "reason": reason,
            }
        )

    # Sort primarily by SG descending, then by legacy score
    evaluated.sort(key=lambda x: (x["sg"], x["score"]), reverse=True)

    return evaluated[:top_n]
