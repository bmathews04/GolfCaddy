import streamlit as st
import pandas as pd
import altair as alt

import altair as alt

# Allow large datasets
alt.data_transformers.disable_max_rows()

# Register a soft chart style that matches the dark theme
alt.themes.register(
    "golf_dark",
    lambda: {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "axis": {
                "labelColor": "#e5e7eb",
                "titleColor": "#e5e7eb",
                "labelFontSize": 11,
                "titleFontSize": 12,
            },
            "legend": {
                "labelColor": "#e5e7eb",
                "titleColor": "#e5e7eb",
            },
        }
    },
)

alt.themes.enable("golf_dark")


from strokes_gained_engine import simulate_expected_strokes_for_shot

# ============================
# CONFIG / CONSTANTS
# ============================

BASELINE_DRIVER_SPEED = 100.0  # mph

# Bias for usual miss pattern
TENDENCY_BIAS_YARDS = 3.0

# Strategy thresholds for auto-pick (yards)
WEDGE_AGGRESSIVE_MAX = 110.0
MID_IRON_MAX = 190.0

# Limit how many candidates get full SG simulation
SG_CANDIDATE_LIMIT = 10

# Default number of SG simulations per candidate
DEFAULT_N_SIM = 200

# Strategy labels (single source of truth)
STRATEGY_BALANCED = "Balanced"
STRATEGY_CONSERVATIVE = "Conservative (Par-focused)"
STRATEGY_AGGRESSIVE = "Aggressive (Pin-seeking)"

# ---- Full-swing wedge carries at 100 mph (center values) ---- #

FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW": 92,
    "LW": 78,
}

# ---- Full bag baseline at 100 mph driver speed ---- #
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

# ---- Shot-type multipliers ---- #

SHOT_MULTIPLIERS = {
    "Full":       1.00,
    "Choke-Down": 0.94,
    "3/4":        0.80,
    "1/2":        0.60,
    "1/4":        0.40,
}

# ---- Scoring shots: (club, shot type, trajectory) ---- #

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

# ---- Simplified wind strengths (mph) ---- #

WIND_STRENGTH_MAP = {
    "none":   0,
    "light":  5,
    "medium": 10,
    "heavy":  20,
}


# ============================
# BASIC HELPERS
# ============================

def scale_value(base_value: float, driver_speed_mph: float) -> float:
    """Scale a baseline value linearly with driver speed."""
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


def get_trouble_mult(label: str) -> float:
    """Convert trouble label to a risk multiplier."""
    l = label.lower()
    if l.startswith("mild"):
        return 1.5
    if l.startswith("severe"):
        return 2.5
    return 1.0


def get_strategy_penalty_scale(strategy_label: str) -> float:
    """How strongly to apply 'safety' penalties vs pure distance."""
    s = strategy_label.lower()
    if s.startswith("conservative"):
        return 1.3
    if s.startswith("aggressive"):
        return 0.7
    return 1.0  # balanced


def get_dispersion_sigma(category: str) -> float:
    """
    Approximate one-standard-deviation distance spread (yards)
    by club category. These are generic averages, not user-specific.
    """
    if category == "scoring_wedge":
        return 5.0
    if category == "short_iron":
        return 7.0
    if category == "mid_iron":
        return 8.0
    if category == "long":
        return 10.0
    # default catch-all
    return 7.0


def compute_roll_yards(shot: dict, green_firmness_label: str) -> float:
    """Approximate roll-out based on trajectory and green firmness."""
    firmness = green_firmness_label.lower()
    if firmness.startswith("soft"):
        base_roll = 1.5
    elif firmness.startswith("firm"):
        base_roll = 8.0
    else:
        base_roll = 4.0

    traj = shot.get("trajectory", "Medium")
    traj_roll_factor = {
        "High":         0.3,
        "Medium-High":  0.5,
        "Medium":       0.7,
        "Medium-Low":   0.9,
        "Low":          1.1,
        "Stock":        0.8,
    }
    factor = traj_roll_factor.get(traj, 0.7)
    return base_roll * factor


# ============================
# DATA BUILDERS
# ============================

@st.cache_data
def build_scoring_shots(driver_speed_mph: float):
    """All scoring shots (PW–LW + shot types) for given driver speed."""
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        full_carry = scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)
        carry = full_carry * SHOT_MULTIPLIERS[shot_type]
        shots.append(
            {
                "club": club,
                "shot_type": shot_type,
                "trajectory": traj,
                "carry": carry,
            }
        )
    return shots


@st.cache_data
def build_full_bag(driver_speed_mph: float):
    """Full bag distances for given driver speed."""
    out = []
    for club, bs, launch, spin, carry, total in FULL_BAG_BASE:
        out.append(
            {
                "Club": club,
                "Ball Speed (mph)": scale_value(bs, driver_speed_mph),
                "Launch (°)": launch,
                "Spin (rpm)": spin,
                "Carry (yds)": scale_value(carry, driver_speed_mph),
                "Total (yds)": scale_value(total, driver_speed_mph),
            }
        )
    return out


@st.cache_data
def build_all_candidate_shots(driver_speed_mph: float):
    """
    Return (all_shots, scoring_shots, full_bag).

    all_shots includes:
      - Full-swing long/mid/short irons + woods
      - All defined scoring wedge shots

    Each shot has:
      club, shot_type, trajectory, carry, category, is_scoring, sigma
    """
    scoring_shots = build_scoring_shots(driver_speed_mph)
    full_bag = build_full_bag(driver_speed_mph)

    long_game = {"Driver", "3W", "3H"}
    wedges = set(FULL_WEDGE_CARRIES.keys())

    all_shots = []

    # 1) Add non-wedge full-swing clubs
    for row in full_bag:
        club = row["Club"]
        if club in wedges:
            continue

        if club in long_game:
            category = "long"
        elif club in {"4i", "5i", "6i"}:
            category = "mid_iron"
        else:
            category = "short_iron"

        sigma = get_dispersion_sigma(category)

        all_shots.append(
            {
                "club": club,
                "shot_type": "Full",
                "trajectory": "Stock",
                "carry": row["Carry (yds)"],
                "category": category,
                "is_scoring": False,
                "sigma": sigma,
            }
        )

    # 2) Add scoring wedge shots (with category + sigma)
    for s in scoring_shots:
        category = "scoring_wedge"
        sigma = get_dispersion_sigma(category)
        all_shots.append(
            {
                **s,
                "category": category,
                "is_scoring": True,
                "sigma": sigma,
            }
        )

    return all_shots, scoring_shots, full_bag


# ============================
# ADJUSTMENT MODELS
# ============================

def adjust_for_wind(target: float, wind_dir: str, wind_strength_label: str) -> float:
    """
    Tuned wind model:
      - Into: hurts more than downwind helps
      - Down: helps, but less than into hurts
      - Cross: small safety bump so you do not under-club
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
    """Adjust distance based on lie."""
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


# ============================
# STRATEGY & SCORING
# ============================

def shot_score(
    target_total: float,
    total: float,
    shot: dict,
    short_trouble_label: str,
    long_trouble_label: str,
    strategy_label: str,
) -> float:
    """
    Legacy distance/risk score used as a tie-breaker.
    Lower = better.
    """
    diff = abs(total - target_total)

    # Asymmetric risk: short vs long
    short_mult = get_trouble_mult(short_trouble_label)
    long_mult = get_trouble_mult(long_trouble_label)

    sigma = shot.get("sigma", 7.0)

    # Extra risk if dispersion is wide and there's trouble in that direction
    risk_scale = 1.0
    if total < target_total and short_trouble_label != "None":
        risk_scale += sigma / 20.0  # bigger sigma => heavier penalty
    elif total > target_total and long_trouble_label != "None":
        risk_scale += sigma / 20.0

    if total < target_total:
        effective_diff = diff * short_mult * risk_scale
    else:
        effective_diff = diff * long_mult * risk_scale

    # Additional club / shot-type preferences
    category = shot.get("category", "")
    shot_type = shot.get("shot_type", "Full")
    swing_mult = SHOT_MULTIPLIERS.get(shot_type, 1.0)

    penalty = 0.0

    # 1) Club-type preferences by distance
    if target_total < 60:
        # Very short: strongly prefer wedges
        if category != "scoring_wedge":
            penalty += 40.0
    elif target_total < 120:
        # Classic scoring wedge zone
        if category != "scoring_wedge":
            penalty += 5.0
    elif target_total < 190:
        # Mid-iron zone, avoid long game or weird wedges
        if category in ("long", "scoring_wedge"):
            penalty += 8.0
    else:
        # Long game territory
        if category != "long":
            penalty += 12.0

    # 2) Prefer fuller swings for longer shots
    if target_total > 100 and swing_mult < 0.8:
        penalty += 8.0

    # 3) Prefer less-than-full shots for short-ish wedges
    if target_total < 90 and swing_mult >= 0.94 and category == "scoring_wedge":
        penalty += 3.0

    # Strategy style: how strong are the safety penalties?
    penalty_scale = get_strategy_penalty_scale(strategy_label)

    return effective_diff + penalty * penalty_scale


def explain_shot_choice(
    shot: dict,
    target_total: float,
    short_trouble_label: str,
    long_trouble_label: str,
    green_firmness_label: str,
    strategy_label: str,
) -> str:
    """Generate a human-friendly explanation for why this shot was chosen."""
    club = shot["club"]
    shot_type = shot["shot_type"]
    category = shot.get("category", "")
    carry = shot["carry"]
    total = shot["total"]
    diff = shot["diff"]
    sigma = shot.get("sigma")

    base = (
        f"Target plays ~{target_total:.0f} yds. "
        f"{club} {shot_type} is expected to carry about {carry:.0f} yds "
        f"and play out to ~{total:.0f} yds (off by {diff:.1f} yds). "
    )

    if sigma is not None:
        base += f"Typical distance spread for this type of shot is about ±{sigma:.0f} yds. "

    firm = green_firmness_label.lower()
    short_t = short_trouble_label.lower()
    long_t = long_trouble_label.lower()
    strat = strategy_label.lower()

    # Mention roll / firmness logic
    if "firm" in firm:
        base += "On a firm green this shot will release more, so roll-out is factored into the total distance. "
    elif "soft" in firm:
        base += "On a soft green the ball should stop closer to its carry distance. "

    # Trouble-aware explanation
    if total >= target_total and short_t.startswith("severe"):
        base += "There is severe trouble short, so this option slightly favors finishing past the front edge. "
    if total <= target_total and long_t.startswith("severe"):
        base += "There is severe trouble long, so this option biases slightly short of the pin. "

    # Strategy style
    if strat.startswith("conservative"):
        base += "Strategy is conservative, so safety is prioritized over being perfect on the number. "
    elif strat.startswith("aggressive"):
        base += "Strategy is aggressive, so the recommendation tolerates more risk to get closer to the pin. "

    # Category-specific flavor
    if category == "scoring_wedge":
        if target_total < 60:
            base += "This is a very short shot, so a softer wedge keeps distance and spin under control."
        elif target_total < 90:
            base += "This is inside classic wedge distance, so a partial wedge offers the best control."
        elif target_total < 120:
            base += "This is prime scoring range, so a wedge is preferred over an iron for proximity."
        else:
            base += "Although it is on the longer side, this wedge setup still matches the number well."
    elif category == "short_iron":
        base += "A short iron provides good height and control for this distance."
    elif category == "mid_iron":
        base += "A mid-iron is ideal here—enough carry without forcing a long club."
    elif category == "long":
        if target_total > 200:
            base += "The distance is long enough that a wood, hybrid, or driver is the most efficient choice."
        else:
            base += "This long club reaches the number without requiring an over-swing with a shorter iron."

    return base


def build_situation_summary(
    lie_label: str,
    elevation_label: str,
    wind_dir_label: str,
    wind_strength_label: str,
    green_firmness_label: str,
    strategy_label: str,
):
    """Create a one-line human summary of the shot context."""
    lie_text = f"{lie_label.lower()} lie"
    elev_text = elevation_label.lower()
    wind_parts = []
    if wind_strength_label != "None":
        wind_parts.append(wind_strength_label.lower())
    if wind_dir_label != "None":
        wind_parts.append(wind_dir_label.lower())
    wind_text = "no wind" if not wind_parts else " ".join(wind_parts) + " wind"
    firm_text = f"{green_firmness_label.lower()} green"

    if strategy_label.startswith("Conservative"):
        strat_text = "conservative strategy"
    elif strategy_label.startswith("Aggressive"):
        strat_text = "aggressive strategy"
    else:
        strat_text = "balanced strategy"

    return f"{lie_text}, {elev_text}, {wind_text}, {firm_text}, {strat_text}."


def auto_pick_strategy(
    target_distance_yards: float,
    trouble_short_label: str,
    trouble_long_label: str,
    skill: str,
) -> str:
    """
    Simple rule-based strategy picker.

    Returns one of:
      - STRATEGY_CONSERVATIVE
      - STRATEGY_BALANCED
      - STRATEGY_AGGRESSIVE
    """
    t_short = trouble_short_label.lower()
    t_long = trouble_long_label.lower()
    skill_norm = skill.lower()

    severe_trouble = (t_short.startswith("severe") or t_long.startswith("severe"))
    mild_trouble = (t_short.startswith("mild") or t_long.startswith("mild"))

    # Very short wedges: more room to be aggressive if no big trouble
    if target_distance_yards < WEDGE_AGGRESSIVE_MAX:
        if severe_trouble or mild_trouble:
            return STRATEGY_BALANCED
        return STRATEGY_AGGRESSIVE

    # Mid-iron zone
    if WEDGE_AGGRESSIVE_MAX <= target_distance_yards <= MID_IRON_MAX:
        if severe_trouble:
            return STRATEGY_CONSERVATIVE
        if mild_trouble:
            if skill_norm == "recreational":
                return STRATEGY_CONSERVATIVE
            else:
                return STRATEGY_BALANCED
        return STRATEGY_BALANCED

    # Long shots (190+)
    if severe_trouble or mild_trouble:
        return STRATEGY_CONSERVATIVE

    if skill_norm == "highly consistent":
        return STRATEGY_BALANCED
    return STRATEGY_CONSERVATIVE


def recommend_shots_with_sg(
    target_total: float,
    candidates,
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
    top_n: int = 3,
):
    """
    Recommend shots using strokes gained as the primary ranking metric.

    Returns:
      List of candidate shot dicts with:
        - carry, total, diff
        - score (legacy distance-based score)
        - sg (strokes gained vs baseline)
    """

    # ---- First pass: distance/risk pre-filter ---- #
    prelim = []
    for s in candidates:
        carry = s["carry"]
        roll = compute_roll_yards(s, green_firmness_label)
        total = carry + roll
        score_dist = shot_score(
            target_total,
            total,
            s,
            short_trouble_label,
            long_trouble_label,
            strategy_label,
        )
        prelim.append(
            {
                "base": s,
                "carry": carry,
                "total": total,
                "distance_score": score_dist,
            }
        )

    # Keep the best N candidates by distance/risk
    prelim.sort(key=lambda x: x["distance_score"])
    filtered = prelim[:SG_CANDIDATE_LIMIT]

    scored = []

    # ---- Second pass: full SG simulation on filtered set ---- #
    for item in filtered:
        s = item["base"]
        carry = item["carry"]
        total = item["total"]

        legacy_score = item["distance_score"]

        # Prepare shot dict for SG engine
        shot_for_sg = {
            "total": total,
            "sigma": s.get("sigma", 7.0),
            "category": s.get("category", ""),
        }

        baseline, expected_if_played = simulate_expected_strokes_for_shot(
            shot_for_sg,
            start_distance_yards=start_distance_yards,
            start_surface=start_surface,
            target_distance_yards=start_distance_yards,
            front_yards=front_yards,
            back_yards=back_yards,
            trouble_short_label=short_trouble_label,
            trouble_long_label=long_trouble_label,
            skill_factor=skill_factor,
            n_sim=n_sim,
            pin_lateral_offset=pin_lateral_offset,
            green_width=green_width,
            # seed left as default for deterministic behavior;
            # pass seed=None if you ever want fresh randomness per call.
        )

        sg = baseline - expected_if_played  # positive = good

        scored.append(
            {
                **s,
                "carry": carry,
                "total": total,
                "diff": abs(total - target_total),
                "score": legacy_score,
                "sg": sg,
            }
        )

    # Sort primarily by strokes gained (descending), then by legacy score (ascending)
    scored.sort(key=lambda x: (-x["sg"], x["score"]))
    return scored[:top_n]


# ============================
# STREAMLIT APP
# ============================

def main():
    st.set_page_config(
        page_title="Golf Caddy",
        layout="centered",
    )

# --- Global CSS Theme Polish ---
    st.markdown(
    """
    <style>

    /* Reduce overall app padding slightly */
    section.main > div {
        padding-top: 1.2rem;
    }

    /* Title styling */
    h1 {
        font-size: 2.3rem !important;
        margin-bottom: 0.2rem !important;
        font-weight: 700 !important;
    }

    /* Subheaders clean spacing */
    h3 {
        margin-top: 1.4rem !important;
        margin-bottom: 0.45rem !important;
        font-weight: 600 !important;
    }

    /* DataFrame font size */
    .stDataFrame tbody, .stDataFrame th {
        font-size: 0.92rem !important;
    }

    /* Slightly round all containers/panels */
    .stApp [data-testid="stVerticalBlock"] {
        border-radius: 0.75rem;
    }

    /* Make expanded sections smoother */
    .streamlit-expanderHeader {
        font-weight: 600 !important;
    }

    </style>
    """,
    unsafe_allow_html=True
    )

    st.title("Golf Caddy")

    st.caption(
        "Enter your conditions and let Golf Caddy suggest shot options based on "
        "professional-style decision logic and strokes gained."
    )

    # Driver speed and precomputed data (shared across tabs)
    driver_speed = st.slider(
        "Current Driver Speed (mph)",
        90,
        115,
        100,
        help="Used to scale your entire bag's distances from a 100 mph baseline.",
    )
    all_shots_base, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)

    # Tabs for Caddy (on-course), Yardages (practice), Info
    tab_caddy, tab_yardages, tab_info = st.tabs(["Caddy", "Yardages", "Info"])

    # ---------- CADDY TAB ---------- #
    with tab_caddy:
        # Mode selector
        mode = st.radio(
            "Mode",
            ["Quick", "Advanced"],
            horizontal=True,
            help=(
                "Quick mode keeps inputs minimal for fast on-course use. "
                "Advanced mode lets you tweak every detail (trouble, green layout, pin side, tendencies)."
            ),
        )

        # Core inputs
        pin_col1, pin_col2 = st.columns([2, 1])
        with pin_col1:
            target_pin = st.number_input(
                "Pin Yardage (yards)",
                min_value=10.0,
                max_value=300.0,
                value=150.0,
                step=1.0,
                help="Measured distance to the flag from your current position.",
            )
        with pin_col2:
            st.write("")
            st.write("")
            st.markdown("**Core Shot Inputs**")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            wind_dir_label = st.selectbox(
                "Wind Direction",
                ["None", "Into", "Down", "Cross"],
                help="Direction the wind is blowing relative to your target.",
            )
            wind_strength_label = st.radio(
                "Wind Strength",
                ["None", "Light", "Medium", "Heavy"],
                horizontal=True,
                help="Stronger winds have a bigger impact on the plays-as yardage.",
            )

        with col_b:
            lie_label = st.radio(
                "Ball Lie",
                ["Good", "Ok", "Bad"],
                horizontal=True,
                help="Good = fairway/tee, Ok = light rough or small slope, Bad = heavy rough or poor stance.",
            )
            elevation_label = st.selectbox(
                "Elevation to Target",
                ["Flat", "Slight Uphill", "Moderate Uphill",
                 "Slight Downhill", "Moderate Downhill"],
                help="Relative height difference between you and the target.",
            )

        with col_c:
            if mode == "Advanced":
                use_auto_strategy = st.checkbox(
                    "Auto-select strategy based on situation",
                    value=True,
                    help="Let Golf Caddy choose Conservative/Balanced/Aggressive "
                         "based on distance, trouble, and your consistency.",
                )
                manual_strategy = st.radio(
                    "Strategy (if not auto)",
                    [STRATEGY_BALANCED, STRATEGY_CONSERVATIVE, STRATEGY_AGGRESSIVE],
                    index=0,
                    help="Conservative favors safety, Aggressive chases pins, Balanced is in between.",
                )
                strategy_label = manual_strategy  # may be overridden later
            else:
                # Quick mode: always auto strategy, do not show manual controls
                use_auto_strategy = True
                strategy_label = STRATEGY_BALANCED
                st.markdown("**Strategy**")
                st.caption("Quick mode uses auto-selected strategy based on distance and situation.")

        # Advanced options (only shown in Advanced mode)
        if mode == "Advanced":
            with st.expander("Advanced: Green, Trouble, Pin Position & Player Tendencies (Optional)"):
                st.markdown("**Green Layout & Safe Center**")
                use_center = st.checkbox(
                    "Aim at the safe center using front/back of green",
                    value=False,
                )

                front_yards = 0.0
                back_yards = 0.0
                if use_center:
                    colf, colb = st.columns(2)
                    with colf:
                        front_yards = st.number_input(
                            "Front of green (yards)",
                            min_value=0.0,
                            max_value=400.0,
                            value=0.0,
                            step=1.0,
                            help="Distance to the front edge of the green.",
                        )
                    with colb:
                        back_yards = st.number_input(
                            "Back of green (yards)",
                            min_value=0.0,
                            max_value=400.0,
                            value=0.0,
                            step=1.0,
                            help="Distance to the back edge of the green.",
                        )
                    st.caption(
                        "If both front and back are > 0 and back > front, "
                        "Golf Caddy will target the center of the green instead of the exact pin."
                    )

                st.markdown("---")
                st.markdown("**Trouble & Green Firmness**")
                tcol1, tcol2, tcol3 = st.columns(3)
                with tcol1:
                    trouble_short_label = st.selectbox(
                        "Trouble Short?",
                        ["None", "Mild", "Severe"],
                        help="How penal is a miss that finishes short of the target?",
                    )
                with tcol2:
                    trouble_long_label = st.selectbox(
                        "Trouble Long?",
                        ["None", "Mild", "Severe"],
                        help="How penal is a miss that finishes long of the target?",
                    )
                with tcol3:
                    green_firmness_label = st.selectbox(
                        "Green Firmness",
                        ["Soft", "Medium", "Firm"],
                        help="Soft = stops close to carry distance, Firm = more roll-out.",
                    )

                st.markdown("---")
                st.markdown("**Pin Lateral Position (Optional)**")
                pw1, pw2 = st.columns(2)
                with pw1:
                    green_width = st.number_input(
                        "Green width (yards, left-to-right)",
                        min_value=0.0,
                        max_value=60.0,
                        value=0.0,
                        step=1.0,
                        help="Approximate green width. Leave 0 if you do not want lateral modeling.",
                    )
                with pw2:
                    pin_side = st.selectbox(
                        "Pin side",
                        ["Center", "Left", "Right"],
                        help="Approximate lateral pin location on the green.",
                    )

                pin_lateral_offset = 0.0
                if green_width > 0:
                    half_w = green_width / 2.0
                    if pin_side == "Left":
                        pin_lateral_offset = -0.66 * half_w
                    elif pin_side == "Right":
                        pin_lateral_offset = 0.66 * half_w
                    else:
                        pin_lateral_offset = 0.0

                st.markdown("---")
                st.markdown("**Player Tendencies (Optional)**")
                tendency = st.radio(
                    "Usual Miss (Distance)",
                    ["Neutral", "Usually Short", "Usually Long"],
                    horizontal=True,
                    help="If you typically come up short or long, Golf Caddy can bias the target slightly to compensate.",
                )
                skill = st.radio(
                    "Ball Striking Consistency",
                    ["Recreational", "Intermediate", "Highly Consistent"],
                    help="Used to scale dispersion windows and strokes-gained simulations.",
                )
        else:
            # Quick mode defaults: no explicit trouble/green/tendency modeling
            use_center = False
            front_yards = 0.0
            back_yards = 0.0
            trouble_short_label = "None"
            trouble_long_label = "None"
            green_firmness_label = "Medium"
            green_width = 0.0
            pin_lateral_offset = 0.0
            tendency = "Neutral"
            skill = "Intermediate"

        # Skill factor for dispersion scaling (used in SG + charts)
        skill_norm = skill.lower()
        if skill_norm == "recreational":
            skill_factor = 1.3
        elif skill_norm == "highly consistent":
            skill_factor = 0.8
        else:
            skill_factor = 1.0

        all_shots = all_shots_base  # don't mutate cached shots

        # Normalize for logic
        wind_dir = wind_dir_label.lower()
        wind_strength = wind_strength_label.lower()
        lie = lie_label.lower()

        if st.button("Suggest Shots ✅"):
            # Decide raw target (pin vs center of green)
            raw_target = target_pin
            using_center = False
            if (
                mode == "Advanced"
                and use_center
                and front_yards > 0
                and back_yards > front_yards
            ):
                raw_target = (front_yards + back_yards) / 2.0
                using_center = True

            # Adjust the target for environment to get "plays as" distance
            after_wind = adjust_for_wind(raw_target, wind_dir, wind_strength)
            after_elev = apply_elevation(after_wind, elevation_label)
            final_target = apply_lie(after_elev, lie)

            # Apply player tendency bias
            bias_adjust = 0.0
            if tendency == "Usually Short":
                bias_adjust = TENDENCY_BIAS_YARDS
            elif tendency == "Usually Long":
                bias_adjust = -TENDENCY_BIAS_YARDS

            final_target_biased = final_target + bias_adjust

            # Auto-pick strategy if enabled
            if use_auto_strategy:
                strategy_label = auto_pick_strategy(
                    target_distance_yards=final_target_biased,
                    trouble_short_label=trouble_short_label,
                    trouble_long_label=trouble_long_label,
                    skill=skill,
                )
                st.caption(f"Auto-selected strategy: **{strategy_label}**")
            else:
                st.caption(f"Using manual strategy selection: **{strategy_label}**")

            st.markdown(f"### Adjusted Target (plays as): **{final_target_biased:.1f} yds**")

            summary = build_situation_summary(
                lie_label,
                elevation_label,
                wind_dir_label,
                wind_strength_label,
                green_firmness_label,
                strategy_label,
            )
            st.caption(summary)

            if using_center:
                st.caption(
                    f"Using safe center of green: front {front_yards:.0f} yds, "
                    f"back {back_yards:.0f} yds, center {raw_target:.0f} yds."
                )
            else:
                st.caption("Using pin yardage as the target.")

            if tendency != "Neutral":
                st.caption(
                    f"Target includes a small adjustment for your usual miss pattern ({tendency.lower()})."
                )

            # Map lie to SG surface
            if lie_label == "Good":
                start_surface = "fairway"
            elif lie_label == "Ok":
                start_surface = "light_rough"
            else:
                start_surface = "heavy_rough"

            # For SG, treat the plays-as distance as the effective starting distance
            start_distance_yards = final_target_biased

            front_for_sg = (
                front_yards if (mode == "Advanced" and use_center and front_yards > 0) else 0.0
            )
            back_for_sg = (
                back_yards if (mode == "Advanced" and use_center and back_yards > front_for_sg) else 0.0
            )

            best3 = recommend_shots_with_sg(
                target_total=final_target_biased,
                candidates=all_shots,
                short_trouble_label=trouble_short_label,
                long_trouble_label=trouble_long_label,
                green_firmness_label=green_firmness_label,
                strategy_label=strategy_label,
                start_distance_yards=start_distance_yards,
                start_surface=start_surface,
                front_yards=front_for_sg,
                back_yards=back_for_sg,
                skill_factor=skill_factor,
                pin_lateral_offset=pin_lateral_offset,
                green_width=green_width,
                n_sim=DEFAULT_N_SIM,
                top_n=3,
            )

            st.subheader("Shot Recommendations")
            for i, s in enumerate(best3, start=1):
                st.markdown(
                    f"**{i}. {s['club']}** — {s['shot_type']} | {s['trajectory']}  "
                    f"(Carry ≈ {s['carry']:.1f} yds, plays to ~{s['total']:.1f} yds)"
                )

                sg_value = s.get("sg", None)
                if sg_value is not None:
                    st.caption(
                        f"Expected strokes gained vs baseline from this position: {sg_value:+.2f}"
                    )

                st.caption(
                    explain_shot_choice(
                        s,
                        final_target_biased,
                        trouble_short_label,
                        trouble_long_label,
                        green_firmness_label,
                        strategy_label,
                    )
                )

            # ---- Dispersion visualization for recommended shots ---- #
            st.subheader("Dispersion Preview (Recommended Shots)")

            disp_rows = []
            for s in best3:
                base_sigma = s.get("sigma", 7.0)
                sigma_effective = base_sigma * skill_factor
                disp_rows.append(
                    {
                        "Shot": f"{s['club']} {s['shot_type']}",
                        "Expected Total (yds)": round(s["total"], 1),
                        "Min (yds)": round(s["total"] - sigma_effective, 1),
                        "Max (yds)": round(s["total"] + sigma_effective, 1),
                    }
                )
            df_disp = pd.DataFrame(disp_rows)
            st.dataframe(df_disp, use_container_width=True)
            st.caption("Min/Max show an approximate ±1σ distance range for each shot option.")

            # 1) Error-bar chart (Expected ±1σ)
            error_base = alt.Chart(df_disp).encode(
                x=alt.X("Shot:N", sort=None),
            )

            error_points = error_base.mark_point(size=80).encode(
                y=alt.Y("Expected Total (yds):Q", title="Distance (yds)"),
            )

            error_bars = error_base.mark_rule().encode(
                y="Min (yds):Q",
                y2="Max (yds):Q",
            )

            target_line_v = alt.Chart(
                pd.DataFrame(
                    {
                        "Shot": df_disp["Shot"],
                        "Target": [final_target_biased] * len(df_disp),
                    }
                )
            ).mark_rule(strokeDash=[4, 4]).encode(
                y="Target:Q"
            )

            st.altair_chart(error_points + error_bars + target_line_v, use_container_width=True)

            # 2) Shot windows & green mini-map
            st.subheader("Shot Windows & Green Mini-Map")

            range_chart = alt.Chart(df_disp).mark_bar(opacity=0.6).encode(
                y=alt.Y("Shot:N", sort=None),
                x=alt.X("Min (yds):Q", title="Distance (yds)"),
                x2="Max (yds):Q",
            )

            greens_data = []

            if mode == "Advanced":
                if front_yards > 0:
                    greens_data.append({"Distance": front_yards, "Label": "Front"})
                if back_yards > 0 and back_yards > front_yards:
                    greens_data.append({"Distance": back_yards, "Label": "Back"})

                if using_center:
                    greens_data.append({"Distance": raw_target, "Label": "Center"})

            greens_data.append({"Distance": target_pin, "Label": "Pin"})
            greens_data.append({"Distance": final_target_biased, "Label": "Plays As"})

            if greens_data:
                greens_df = pd.DataFrame(greens_data)

                greens_rules = alt.Chart(greens_df).mark_rule(strokeDash=[4, 4]).encode(
                    x="Distance:Q",
                    color="Label:N",
                )

                greens_text = alt.Chart(greens_df).mark_text(
                    dy=-8,
                    angle=90
                ).encode(
                    x="Distance:Q",
                    text="Label:N",
                    color="Label:N",
                )

                mini_map = range_chart + greens_rules + greens_text
                st.altair_chart(mini_map, use_container_width=True)
            else:
                st.altair_chart(range_chart, use_container_width=True)

    # ---------- YARDAGES TAB ---------- #
    with tab_yardages:
        st.subheader("Scoring Shot Yardage Table")
        df_scoring = pd.DataFrame(scoring_shots)
        df_scoring = df_scoring[["carry", "club", "shot_type", "trajectory"]]
        df_scoring.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
        df_scoring = df_scoring.sort_values("Carry (yds)", ascending=False)
        df_scoring = df_scoring.reset_index(drop=True)
        st.dataframe(df_scoring, use_container_width=True)

        st.subheader("Full Bag Yardages")
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(1)
        df_full = df_full.sort_values("Carry (yds)", ascending=False)
        df_full = df_full.reset_index(drop=True)
        st.dataframe(df_full, use_container_width=True)

    # ---------- INFO TAB ---------- #
    with tab_info:
        st.subheader("How Golf Caddy Works")
        st.markdown(
            "Golf Caddy evaluates your target distance, wind, lie, elevation, green firmness, "
            "trouble around the green, your consistency, and your strategy preferences. "
            "It then recommends shots based on both distance/risk logic and strokes gained calculations."
        )

        st.markdown("### Key Concepts")

        st.markdown("**Modes**")
        st.markdown(
            "- **Quick**: Minimal inputs for fast on-course decisions (pin yardage, wind, lie, elevation). "
            "Defaults are used behind the scenes for trouble and green details.\n"
            "- **Advanced**: Full control over green layout, trouble, pin side, tendencies, and strategy."
        )

        st.markdown("**Adjusted Target (Plays As)**")
        st.markdown(
            "The app converts your raw pin or center-of-green yardage into a 'plays as' distance by "
            "accounting for wind, elevation, lie, and (optionally) your usual miss pattern."
        )

        st.markdown("**Trouble Short / Long**")
        st.markdown(
            "Misses short and long are not treated equally. If there is severe trouble (e.g., water or OB) "
            "on one side, shots that are more likely to finish there are penalized more heavily in the scoring."
        )

        st.markdown("**Pin Lateral Position & Short-Siding**")
        st.markdown(
            "When you provide green width and pin side (left/center/right), the strokes-gained engine models "
            "left/right dispersion relative to the pin and penalizes short-sided misses that finish outside the green."
        )

        st.markdown("**Green Firmness & Roll-Out**")
        st.markdown(
            "Firm greens lead to more roll after landing, while soft greens stop closer to carry distance. "
            "The model estimates roll based on green firmness and shot trajectory."
        )

        st.markdown("**Dispersion and Consistency**")
        st.markdown(
            "Each club category is assigned a typical distance dispersion (±1σ). Your selected ball striking "
            "consistency scales these values up or down, influencing both the visual dispersion windows and how "
            "heavily wide-dispersion options are penalized when trouble is present."
        )

        st.markdown("**Strategy (Manual or Auto)**")
        st.markdown(
            "You can either choose a strategy (Conservative/Balanced/Aggressive) manually in Advanced mode, "
            "or let Golf Caddy auto-select one based on distance, trouble severity, and your consistency level."
        )

        st.markdown("**Strokes Gained**")
        st.markdown(
            "Strokes gained compares your expected performance from the current position to a baseline player. "
            "For each candidate shot, Golf Caddy simulates dispersions and uses distance-to-hole curves to estimate "
            "how many strokes it will take to finish the hole if you choose that shot. The difference vs baseline "
            "is reported as expected strokes gained."
        )

        st.markdown("**Safe Center Target**")
        st.markdown(
            "When front and back yardages of the green are provided, Golf Caddy can target the center of the "
            "green rather than the pin. This mirrors how professional players often manage risk on challenging pins."
        )


if __name__ == "__main__":
    main()
