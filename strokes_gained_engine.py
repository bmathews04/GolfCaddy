import math
from typing import List, Dict, Tuple, Optional

import numpy as np

# ============================================================
# CONSTANTS & BASE DATA
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

# Shot-type multipliers (fallback for wedges if no profile found)
SHOT_MULTIPLIERS = {
    "Full": 1.00,
    "Choke-Down": 0.94,
    "3/4": 0.80,
    "1/2": 0.60,
    "1/4": 0.40,
}

# More detailed wedge profiles (carry multiplier, extra spin factor, dispersion tweak)
# These are heuristic but “feel” like good tour-informed starting points.
WEDGE_PROFILES: Dict[Tuple[str, str], Dict[str, float]] = {
    ("PW", "Full"): {"carry_mult": 1.00, "spin_mult": 1.0, "sigma_mult": 1.0},
    ("PW", "Choke-Down"): {"carry_mult": 0.94, "spin_mult": 1.05, "sigma_mult": 0.95},
    ("PW", "3/4"): {"carry_mult": 0.82, "spin_mult": 1.10, "sigma_mult": 0.9},
    ("PW", "1/2"): {"carry_mult": 0.62, "spin_mult": 1.15, "sigma_mult": 0.85},
    ("PW", "1/4"): {"carry_mult": 0.42, "spin_mult": 1.20, "sigma_mult": 0.8},

    ("GW", "Full"): {"carry_mult": 1.00, "spin_mult": 1.0, "sigma_mult": 1.0},
    ("GW", "Choke-Down"): {"carry_mult": 0.94, "spin_mult": 1.05, "sigma_mult": 0.95},
    ("GW", "3/4"): {"carry_mult": 0.80, "spin_mult": 1.10, "sigma_mult": 0.9},
    ("GW", "1/2"): {"carry_mult": 0.60, "spin_mult": 1.15, "sigma_mult": 0.85},
    ("GW", "1/4"): {"carry_mult": 0.40, "spin_mult": 1.20, "sigma_mult": 0.8},

    ("SW", "Full"): {"carry_mult": 1.00, "spin_mult": 1.0, "sigma_mult": 1.0},
    ("SW", "Choke-Down"): {"carry_mult": 0.94, "spin_mult": 1.05, "sigma_mult": 0.95},
    ("SW", "3/4"): {"carry_mult": 0.80, "spin_mult": 1.10, "sigma_mult": 0.9},
    ("SW", "1/2"): {"carry_mult": 0.60, "spin_mult": 1.20, "sigma_mult": 0.85},
    ("SW", "1/4"): {"carry_mult": 0.40, "spin_mult": 1.25, "sigma_mult": 0.8},

    ("LW", "Full"): {"carry_mult": 1.00, "spin_mult": 1.0, "sigma_mult": 1.0},
    ("LW", "Choke-Down"): {"carry_mult": 0.92, "spin_mult": 1.05, "sigma_mult": 0.95},
    ("LW", "3/4"): {"carry_mult": 0.78, "spin_mult": 1.15, "sigma_mult": 0.9},
    ("LW", "1/2"): {"carry_mult": 0.58, "spin_mult": 1.25, "sigma_mult": 0.85},
    ("LW", "1/4"): {"carry_mult": 0.38, "spin_mult": 1.30, "sigma_mult": 0.8},
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

# Launch “windows” per club (approx tour-ish ranges)
# Not currently used by app.py, but available for future Range/Coach modes.
LAUNCH_WINDOWS = {
    "Driver": {"launch_deg": (10, 15), "spin_rpm": (2000, 2800)},
    "3W": {"launch_deg": (11, 16), "spin_rpm": (2600, 3300)},
    "3H": {"launch_deg": (13, 18), "spin_rpm": (3200, 4000)},
    "4i": {"launch_deg": (13, 17), "spin_rpm": (3800, 4600)},
    "5i": {"launch_deg": (14, 18), "spin_rpm": (4300, 5200)},
    "6i": {"launch_deg": (15, 19), "spin_rpm": (4700, 5600)},
    "7i": {"launch_deg": (16, 20), "spin_rpm": (5000, 6500)},
    "8i": {"launch_deg": (18, 22), "spin_rpm": (6000, 7500)},
    "9i": {"launch_deg": (20, 24), "spin_rpm": (7000, 8500)},
    "PW": {"launch_deg": (24, 30), "spin_rpm": (8000, 9500)},
    "GW": {"launch_deg": (26, 32), "spin_rpm": (8500, 10000)},
    "SW": {"launch_deg": (28, 36), "spin_rpm": (9000, 10500)},
    "LW": {"launch_deg": (30, 38), "spin_rpm": (9000, 11000)},
}


# ============================================================
# BASIC SCALING & PUBLIC ADJUST FUNCTIONS
# ============================================================

def _scale_value(base_value: float, driver_speed_mph: float) -> float:
    """Scale a baseline value slightly nonlinearly with driver speed."""
    factor = driver_speed_mph / BASELINE_DRIVER_SPEED
    # Mildly super-linear scaling to reflect speed benefits (~1.03 exponent).
    return base_value * (factor ** 1.03)


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


# ============================================================
# DISPERSION MODEL
# ============================================================

def get_dispersion_sigma(category: str) -> float:
    """
    Return 1D distance dispersion (std dev in yards) for a given category.
    This is a simple, tour-informed but not exact model.
    """
    cat = (category or "").lower()
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


# ============================================================
# BALL FLIGHT / ROLL MODEL (SIMPLIFIED)
# ============================================================

def _estimate_roll_from_spin(
    base_roll: float,
    spin_rpm: float,
    green_firmness_label: str,
    category: str,
) -> float:
    """
    Adjust roll-out based on spin, firmness, and club category.
    Higher spin + softer greens = less roll.
    Lower spin + firm = more roll.
    """
    firmness = (green_firmness_label or "Medium").lower()
    cat = (category or "").lower()

    # Normalize spin relative to a mid-iron-ish reference.
    ref_spin = 5500.0
    spin_ratio = max(0.5, min(spin_rpm / ref_spin, 1.8))

    # Firmness multiplier
    if firmness == "soft":
        firm_mult = 0.6
    elif firmness == "firm":
        firm_mult = 1.4
    else:
        firm_mult = 1.0

    # Category influence: wedges roll less, long clubs more.
    if cat == "scoring_wedge":
        cat_mult = 0.5
    elif cat == "short_iron":
        cat_mult = 0.8
    elif cat == "mid_iron":
        cat_mult = 1.0
    else:
        cat_mult = 1.3

    # Higher spin → less roll
    roll = base_roll * firm_mult * cat_mult / spin_ratio

    # Clamp for sanity
    return max(0.0, roll)


# ============================================================
# BAG & SHOT GENERATION
# ============================================================

def _build_full_bag(driver_speed_mph: float, green_firmness_label: str = "Medium"):
    """
    Full bag distances for given driver speed with simple carry/roll model.
    Returns a list of dicts with:
      Club, Ball Speed (mph), Launch (°), Spin (rpm), Carry (yds), Total (yds)
    """
    out = []
    for club, bs, launch, spin, carry_base, total_base in FULL_BAG_BASE:
        cat = _club_category(club)

        # Scale ball speed & carry with driver speed
        bs_scaled = _scale_value(bs, driver_speed_mph)
        carry_scaled = _scale_value(carry_base, driver_speed_mph)

        # Base roll from baseline spec
        base_roll = max(0.0, total_base - carry_base)
        roll_adj = _estimate_roll_from_spin(
            base_roll=base_roll,
            spin_rpm=spin,
            green_firmness_label=green_firmness_label,
            category=cat,
        )
        total_scaled = carry_scaled + roll_adj

        out.append(
            {
                "Club": club,
                "Ball Speed (mph)": bs_scaled,
                "Launch (°)": launch,
                "Spin (rpm)": spin,
                "Carry (yds)": carry_scaled,
                "Total (yds)": total_scaled,
            }
        )
    return out


def _build_scoring_shots(driver_speed_mph: float):
    """
    All scoring shots (PW–LW + shot types) for given driver speed.
    Returns list of dicts with: club, shot_type, trajectory, carry, total, category.
    """
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        base_full_carry = _scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)

        profile = WEDGE_PROFILES.get((club, shot_type))
        if profile:
            carry = base_full_carry * profile["carry_mult"]
        else:
            carry = base_full_carry * SHOT_MULTIPLIERS.get(shot_type, 1.0)

        # For now assume total ≈ carry for scoring wedges (they stop quickly).
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
    # Use "Medium" as baseline firmness for bag modeling – the app passes
    # firmness later into SG sims for more detailed behavior.
    full_bag = _build_full_bag(driver_speed_mph, green_firmness_label="Medium")
    scoring_shots = _build_scoring_shots(driver_speed_mph)

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

    # Add scoring wedges (partials)
    all_shots.extend(scoring_shots)

    return all_shots, scoring_shots, full_bag


# ============================================================
# STROKES-GAINED TABLES (BY LIE TYPE)
# ============================================================

# Approximate “tour-ish” baseline from ShotLink-style data,
# but smoothed and simplified.
_EXPECTED_STROKES_BY_LIE = {
    "fairway": [
        (0.0, 1.00),
        (3.0, 1.07),
        (8.0, 1.25),
        (20.0, 1.65),
        (40.0, 1.90),
        (80.0, 2.20),
        (120.0, 2.55),
        (160.0, 2.80),
        (200.0, 3.00),
        (240.0, 3.25),
        (280.0, 3.50),
        (360.0, 3.90),
    ],
    "rough": [
        (0.0, 1.05),
        (3.0, 1.12),
        (8.0, 1.35),
        (20.0, 1.80),
        (40.0, 2.05),
        (80.0, 2.45),
        (120.0, 2.80),
        (160.0, 3.05),
        (200.0, 3.30),
        (240.0, 3.60),
        (280.0, 3.85),
        (360.0, 4.25),
    ],
    "sand": [
        (0.0, 1.10),
        (3.0, 1.20),
        (8.0, 1.45),
        (20.0, 1.95),
        (40.0, 2.25),
        (80.0, 2.70),
        (120.0, 3.10),
        (160.0, 3.40),
        (200.0, 3.70),
        (240.0, 4.00),
        (280.0, 4.30),
        (360.0, 4.70),
    ],
    "recovery": [
        (0.0, 1.20),
        (10.0, 1.60),
        (30.0, 2.10),
        (60.0, 2.60),
        (100.0, 3.10),
        (150.0, 3.60),
        (220.0, 4.10),
        (300.0, 4.60),
        (380.0, 5.00),
    ],
    "green": [
        (0.0, 1.00),
        (3.0, 1.20),
        (8.0, 1.40),
        (20.0, 1.80),
    ],
}


def _interp_expected_strokes(distance_yards: float, lie_type: str) -> float:
    """Linear interpolation over the distance-strokes table for a given lie."""
    d = max(0.0, float(distance_yards))
    lie = (lie_type or "fairway").lower()
    table = _EXPECTED_STROKES_BY_LIE.get(lie, _EXPECTED_STROKES_BY_LIE["fairway"])

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


# ============================================================
# SG SIMULATION
# ============================================================

def _simulate_candidate_sg(
    candidate: Dict,
    target_total: float,
    short_trouble_label: str,
    long_trouble_label: str,
    strategy_label: str,
    start_distance_yards: float,
    start_surface: str,
    skill_factor: float,
    green_firmness_label: str,
    n_sim: int,
):
    """
    Monte Carlo strokes-gained estimate for a single candidate shot.

    Returns:
      (expected_strokes_after, strokes_gained)
    """
    cat = candidate["category"]
    sigma_base = get_dispersion_sigma(cat)

    # Skill factor: recreational > 1, highly consistent < 1
    sigma_eff = max(0.1, sigma_base * skill_factor)

    # Mean error (positive = long, negative = short) in yards
    mu = candidate["total"] - target_total

    # Sample shot outcomes in 1D (along line to target)
    errors = np.random.normal(loc=mu, scale=sigma_eff, size=n_sim)

    # Distance remaining is abs(error)
    remaining = np.abs(errors)

    # Assume outcome lie is fairway/green most of the time;
    # for now we keep same lie as starting surface for expected strokes.
    outcome_lie = start_surface or "fairway"

    # Base strokes after shot (1 stroke to hit, plus expected strokes from remaining)
    strokes_from_remaining = np.array(
        [_interp_expected_strokes(d, outcome_lie) for d in remaining]
    )
    strokes_samples = 1.0 + strokes_from_remaining

    # Trouble penalties for big misses short/long
    short_severity = _trouble_severity(short_trouble_label)
    long_severity = _trouble_severity(long_trouble_label)
    strat_mult = _strategy_penalty_multiplier(strategy_label)

    if short_severity > 0.0:
        short_mask = errors < -5.0  # bad short if 5+ yds short
        strokes_samples[short_mask] += short_severity * strat_mult

    if long_severity > 0.0:
        long_mask = errors > 5.0   # bad long if 5+ yds long
        strokes_samples[long_mask] += long_severity * strat_mult

    expected_after = float(strokes_samples.mean())

    # Baseline from current distance (before this shot)
    baseline_from_here = _interp_expected_strokes(start_distance_yards, start_surface)

    # SG = baseline - expected actual
    sg = baseline_from_here - expected_after
    return expected_after, sg


# ============================================================
# PUBLIC RECOMMENDER
# ============================================================

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

    Arguments front/back/pin_lateral/green_width are accepted for future
    expansion (2D dispersion / lateral trouble), but the current model
    focuses on along-the-line distance + simple short/long trouble.
    """
    # Filter candidates to reasonable window around target to keep noise down
    filtered: List[Dict] = []
    for c in candidates:
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
            start_surface=start_surface,
            skill_factor=skill_factor,
            green_firmness_label=green_firmness_label,
            n_sim=n_sim,
        )

        # Legacy target proximity score (for tie-breaking)
        legacy_score = -abs(diff) - 0.2 * get_dispersion_sigma(c["category"])

        # Plain-language reason for the UI
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

    # Sort by SG first, then by legacy proximity score
    evaluated.sort(key=lambda x: (x["sg"], x["score"]), reverse=True)
    return evaluated[:top_n]


# ============================================================
# EXTRA HELPERS FOR FUTURE MODES
# ============================================================

def get_launch_window(club: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """
    Return recommended launch & spin window for a given club, if defined.
    Not currently used by app.py, but available for Range/Coach modes.
    """
    return LAUNCH_WINDOWS.get(club)


def compute_optimal_carry_for_target(
    target_pin_yards: float,
    candidates: List[Dict],
    skill_factor: float,
    short_trouble_label: str = "None",
    long_trouble_label: str = "None",
    start_surface: str = "fairway",
    green_firmness_label: str = "Medium",
    n_sim: int = 600,
    carry_search_window: float = 10.0,
) -> Dict:
    """
    Prototype "perfect carry" helper for Combine-style or practice modes.

    For each candidate shot, searches around its natural total distance
    +/- carry_search_window and finds the aiming point (plays-to distance)
    that yields the best strokes-gained profile relative to the pin.

    Returns the best configuration:
      {
        "club": ...,
        "shot_type": ...,
        "best_target_total": ...,
        "best_sg": ...,
      }
    """
    best_cfg = None

    for c in candidates:
        # We treat the candidate's natural total as central guess
        base_total = c["total"]
        cat = c["category"]

        # Explore a grid of offsets (aim slightly short/long)
        offsets = np.linspace(-carry_search_window, carry_search_window, 9)

        for off in offsets:
            aim_total = base_total + off
            if aim_total <= 0:
                continue

            # When we aim shorter/longer, "target_total" in SG is aim_total,
            # but baseline SG is still referenced to pin distance.
            target_total_for_sg = aim_total
            start_distance = aim_total  # plays-like distance of the strike

            expected_after, sg = _simulate_candidate_sg(
                candidate=c,
                target_total=target_total_for_sg,
                short_trouble_label=short_trouble_label,
                long_trouble_label=long_trouble_label,
                strategy_label=STRATEGY_BALANCED,
                start_distance_yards=start_distance,
                start_surface=start_surface,
                skill_factor=skill_factor,
                green_firmness_label=green_firmness_label,
                n_sim=n_sim,
            )

            # We care about how good this is relative to the pin distance
            # as well, but for now we rank purely by SG from this position.
            cfg = {
                "club": c["club"],
                "shot_type": c["shot_type"],
                "aim_offset": off,
                "aim_total": aim_total,
                "sg": sg,
            }

            if best_cfg is None or sg > best_cfg["sg"]:
                best_cfg = cfg

    return best_cfg or {}
