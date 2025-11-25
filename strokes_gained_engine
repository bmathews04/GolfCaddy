# strokes_gained_engine.py

import math
import random

# ---- Expected Strokes Curves (Simplified) ---- #
# Distances are in yards, putting distances in feet.

# Fairway / Good lie: approximate expected strokes to hole out
FAIRWAY_CURVE = [
    (250, 3.95),
    (225, 3.75),
    (200, 3.50),
    (175, 3.25),
    (150, 3.05),
    (125, 2.85),
    (100, 2.70),
    (75,  2.55),
    (50,  2.40),
    (30,  2.20),
    (20,  1.95),
    (10,  1.75),
]

# Light rough / "Ok" lie: slightly worse than fairway
LIGHT_ROUGH_CURVE = [(d, v + 0.05) for (d, v) in FAIRWAY_CURVE]

# Heavy rough / "Bad" lie: worse still
HEAVY_ROUGH_CURVE = [(d, v + 0.15) for (d, v) in FAIRWAY_CURVE]

# Around the green (chip / pitch) in yards
AROUND_GREEN_CURVE = [
    (30,  2.25),
    (20,  2.05),
    (15,  1.95),
    (10,  1.85),
    (5,   1.70),
    (3,   1.60),
    (1,   1.50),
]

# Putting: expected putts from distance in feet
PUTTING_CURVE = [
    (1, 1.00),
    (3, 1.05),
    (5, 1.15),
    (8, 1.30),
    (10,1.40),
    (15,1.60),
    (20,1.80),
    (30,2.00),
    (40,2.20),
    (60,2.50),
]


def _interp_curve(curve, x: float) -> float:
    """
    Piecewise-linear interpolation/extrapolation on (distance, value) pairs.
    Distances are assumed descending.
    """
    if x >= curve[0][0]:
        return curve[0][1]
    if x <= curve[-1][0]:
        return curve[-1][1]

    for i in range(len(curve) - 1):
        d1, v1 = curve[i]
        d2, v2 = curve[i + 1]
        if d1 >= x >= d2:
            t = (d1 - x) / (d1 - d2)
            return v1 + t * (v2 - v1)

    return curve[-1][1]


def expected_putts_from_distance(feet: float) -> float:
    """Expected number of putts from given distance in feet."""
    return _interp_curve(PUTTING_CURVE, feet)


def expected_strokes_from_distance(distance_yards: float, surface: str) -> float:
    """
    Expected strokes to hole out from a given distance and surface.

    surface in:
      - 'fairway'
      - 'light_rough'
      - 'heavy_rough'
      - 'around_green'
      - 'green'
    """
    d = max(distance_yards, 0.0)
    s = surface.lower()

    if s == "green":
        feet = d * 3.0
        return expected_putts_from_distance(feet)
    elif s == "around_green":
        return _interp_curve(AROUND_GREEN_CURVE, d)
    elif s == "light_rough":
        return _interp_curve(LIGHT_ROUGH_CURVE, d)
    elif s == "heavy_rough":
        return _interp_curve(HEAVY_ROUGH_CURVE, d)
    else:
        # default to fairway
        return _interp_curve(FAIRWAY_CURVE, d)


# ---- Dispersion helpers ---- #

def get_lateral_sigma(category: str) -> float:
    """
    Rough lateral dispersion (yards) for each club category before skill scaling.
    """
    c = category.lower()
    if c == "long":
        return 15.0
    if c == "mid_iron":
        return 12.0
    if c == "short_iron":
        return 10.0
    if c == "scoring_wedge":
        return 8.0
    return 10.0


def sample_normal(mean: float, sigma: float) -> float:
    """Sample from a normal distribution using Box-Muller."""
    if sigma <= 0:
        return mean
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2.0 * math.log(u1 + 1e-12)) * math.cos(2 * math.pi * u2)
    return mean + sigma * z


# ---- Penalty / trouble modeling ---- #

def trouble_penalty(trouble_label: str) -> float:
    """
    Extra penalty strokes when a shot finishes in a trouble zone.

    - Mild: small cost (e.g., tough bunker/rough)
    - Severe: larger cost (e.g., water/OB/very bad miss)
    """
    t = trouble_label.lower()
    if t.startswith("mild"):
        return 0.30  # ~ a third of a stroke
    if t.startswith("severe"):
        return 0.80  # close to a full stroke lost
    return 0.0


# ---- Main SG simulation ---- #

def simulate_expected_strokes_for_shot(
    shot: dict,
    start_distance_yards: float,
    start_surface: str,
    target_distance_yards: float,
    front_yards: float,
    back_yards: float,
    trouble_short_label: str,
    trouble_long_label: str,
    skill_factor: float = 1.0,
    n_sim: int = 200,
) -> tuple[float, float]:
    """
    Monte Carlo simulation for expected strokes from this shot choice.

    Inputs:
      - shot: dict with at least:
          'total': expected total distance (carry + roll, yards)
          'sigma': longitudinal distance sigma (yards)
          'category': club category ('long', 'mid_iron', 'short_iron', 'scoring_wedge')
      - start_distance_yards: distance from hole before the shot
      - start_surface: 'fairway', 'light_rough', 'heavy_rough'
      - target_distance_yards: geometric distance to the hole (pin or green center)
      - front_yards, back_yards: front/back of green (yards). If invalid, a virtual
        green is constructed around the target distance.
      - trouble_short_label / trouble_long_label: 'None', 'Mild', 'Severe'
      - skill_factor: scales dispersion (1.0 = neutral, >1 = more scatter, <1 = tighter)
      - n_sim: number of random outcomes to simulate

    Returns:
      (baseline_expected_strokes, expected_strokes_if_played)

    Strokes gained for this shot choice:
      SG = baseline_expected_strokes - expected_strokes_if_played
    """
    # Seed for reproducibility per call (optional: comment out if you want randomness each run)
    random.seed(42)

    # Baseline from starting position
    baseline = expected_strokes_from_distance(start_distance_yards, start_surface)

    # Green model
    if front_yards <= 0 or back_yards <= front_yards:
        # Virtual green around target
        green_front = target_distance_yards - 7.0
        green_back = target_distance_yards + 7.0
    else:
        green_front = front_yards
        green_back = back_yards

    green_center = 0.5 * (green_front + green_back)
    green_half_width = 10.0  # lateral radius in yards assumed

    # Longitudinal dispersion (already scaled by your logic if desired)
    sigma_long = shot.get("sigma", 7.0) * skill_factor

    # Lateral dispersion by category
    category = shot.get("category", "")
    base_lat_sigma = get_lateral_sigma(category)
    sigma_lat = base_lat_sigma * skill_factor

    expected_list = []

    for _ in range(n_sim):
        base_total = shot["total"]

        # Sample actual distance and lateral offset
        actual_total = sample_normal(base_total, sigma_long)
        lateral = sample_normal(0.0, sigma_lat)

        # Distance to hole (radial)
        diff = actual_total - target_distance_yards
        dist_to_hole_yards = abs(diff)

        # Now approximate remaining strokes
        if dist_to_hole_yards <= 0.5:
            # Holed
            rem_strokes = 0.0
        elif dist_to_hole_yards <= 2.0:
            # Very close putt
            rem_strokes = expected_strokes_from_distance(dist_to_hole_yards, "green")
        elif dist_to_hole_yards <= 40.0:
            # Short game zone
            on_green_like = (
                green_front <= actual_total <= green_back
                and abs(lateral) <= green_half_width
            )
            if on_green_like:
                feet = dist_to_hole_yards * 3.0
                rem_strokes = expected_putts_from_distance(feet)
            else:
                rem_strokes = expected_strokes_from_distance(
                    dist_to_hole_yards,
                    "around_green",
                )
        else:
            # Longer miss: rough + possible trouble
            if diff < 0:
                # Short miss
                surface_after = "light_rough"
                rem_strokes = expected_strokes_from_distance(
                    dist_to_hole_yards, surface_after
                )
                rem_strokes += trouble_penalty(trouble_short_label)
            else:
                # Long miss
                surface_after = "light_rough"
                rem_strokes = expected_strokes_from_distance(
                    dist_to_hole_yards, surface_after
                )
                rem_strokes += trouble_penalty(trouble_long_label)

        total_strokes = 1.0 + rem_strokes
        expected_list.append(total_strokes)

    expected_if_played = sum(expected_list) / len(expected_list)
    return baseline, expected_if_played
