import streamlit as st
import pandas as pd

# ---- CONSTANTS ---- #

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
    "Full":       1.00,
    "Choke-Down": 0.94,
    "3/4":        0.80,
    "1/2":        0.60,
    "1/4":        0.40,
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

# ---- CALCULATION FUNCTIONS ---- #

def scale_value(base_value: float, driver_speed_mph: float) -> float:
    """Scale a baseline value linearly with driver speed."""
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


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
      club, shot_type, trajectory, carry, category, is_scoring
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

        all_shots.append(
            {
                "club": club,
                "shot_type": "Full",
                "trajectory": "Stock",
                "carry": row["Carry (yds)"],
                "category": category,
                "is_scoring": False,
            }
        )

    # 2) Add scoring wedge shots (with category info)
    for s in scoring_shots:
        all_shots.append(
            {
                **s,
                "category": "scoring_wedge",
                "is_scoring": True,
            }
        )

    return all_shots, scoring_shots, full_bag


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
    if scale < 0.5:
        scale = 0.5
    elif scale > 1.2:
        scale = 1.2

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


def shot_score(target_carry: float, shot: dict) -> float:
    """
    Lower = better.
    Base term is distance difference; then we add small penalties
    to make the choice more 'golf-smart'.
    """
    diff = abs(shot["carry"] - target_carry)
    penalty = 0.0

    category = shot.get("category", "")
    shot_type = shot.get("shot_type", "Full")
    swing_mult = SHOT_MULTIPLIERS.get(shot_type, 1.0)

    # 1) Club-type preferences by distance
    if target_carry < 60:
        # Very short: strongly prefer wedges
        if category != "scoring_wedge":
            penalty += 40.0
    elif target_carry < 120:
        # Classic scoring wedge zone
        if category != "scoring_wedge":
            penalty += 5.0
    elif target_carry < 190:
        # Mid-iron zone, avoid long game or weird wedges
        if category in ("long", "scoring_wedge"):
            penalty += 8.0
    else:
        # Long game territory
        if category != "long":
            penalty += 12.0

    # 2) Prefer fuller swings for longer shots
    if target_carry > 100 and swing_mult < 0.8:
        # discourage 1/2, 1/4 wedges on 150-yd shots
        penalty += 8.0

    # 3) Prefer less-than-full shots for short-ish wedges
    if target_carry < 90 and swing_mult >= 0.94 and category == "scoring_wedge":
        # small nudge away from nuking a full wedge on a 70-yd shot
        penalty += 3.0

    return diff + penalty


def recommend_shots(target_carry: float, candidates, top_n: int = 3):
    """Return top_n shots sorted by 'golf-smart' score."""
    scored = []
    for s in candidates:
        sc = shot_score(target_carry, s)
        scored.append(
            {
                **s,
                "diff": abs(s["carry"] - target_carry),
                "score": sc,
            }
        )
    scored.sort(key=lambda x: x["score"])
    return scored[:top_n]


def explain_shot_choice(shot: dict, target_carry: float) -> str:
    """Generate a human-friendly explanation for why this shot was chosen."""
    club = shot["club"]
    shot_type = shot["shot_type"]
    category = shot.get("category", "")
    carry = shot["carry"]
    diff = shot["diff"]

    base = f"Target is ~{target_carry:.0f} yds, this shot carries about {carry:.0f} yds (off by {diff:.1f} yds). "

    # Scoring wedges
    if category == "scoring_wedge":
        if target_carry < 60:
            return base + "Short distance: using a soft wedge keeps it controlled around the green."
        elif target_carry < 90:
            return base + "Inside wedge range: a partial wedge gives better distance and spin control."
        elif target_carry < 120:
            return base + "This is classic scoring distance: a controlled wedge is preferred over an iron."
        else:
            return base + "Even though this is longer, this wedge option still fits the distance well."

    # Short irons
    if category == "short_iron":
        return base + "Short iron is ideal here: high enough flight with plenty of control for this distance."

    # Mid irons
    if category == "mid_iron":
        return base + "Mid-iron suits this range: enough carry without forcing a long club or over-swinging."

    # Long game
    if category == "long":
        if target_carry > 200:
            return base + "Distance is long enough to justify a wood/hybrid/driver; this is the most efficient option."
        else:
            return base + "This club reaches the number while avoiding over-swinging a shorter iron."

    # Fallback
    return base + "This option best matches the distance while keeping the swing and club choice reasonable."


# ---- STREAMLIT APP ---- #

def main():
    st.title("Golf Shot Selector")

    # Driver speed and precomputed data
    driver_speed = st.slider("Current Driver Speed (mph)", 90, 115, 100)
    all_shots, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)

    # Target carry
    target = st.number_input(
        "Target Carry Distance (yards)",
        min_value=10.0,
        max_value=300.0,
        value=150.0,
        step=1.0,
    )

    # Wind / lie / elevation inputs
    col1, col2, col3 = st.columns(3)
    with col1:
        wind_dir_label = st.selectbox(
            "Wind Direction",
            ["None", "Into", "Down", "Cross"],
        )
    with col2:
        wind_strength_label = st.selectbox(
            "Wind Strength",
            ["None", "Light", "Medium", "Heavy"],
        )
    with col3:
        lie_label = st.selectbox(
            "Lie",
            ["Good", "Ok", "Bad"],
        )

    elevation_label = st.selectbox(
        "Elevation",
        ["Flat", "Slight Uphill", "Moderate Uphill",
         "Slight Downhill", "Moderate Downhill"],
    )

    # Normalize for logic
    wind_dir = wind_dir_label.lower()
    wind_strength = wind_strength_label.lower()
    lie = lie_label.lower()

    if st.button("Suggest Shots"):
        after_wind = adjust_for_wind(target, wind_dir, wind_strength)
        after_elev = apply_elevation(after_wind, elevation_label)
        final_target = apply_lie(after_elev, lie)

        st.markdown(f"### Adjusted Target: **{final_target:.1f} yds**")

        best3 = recommend_shots(final_target, all_shots, top_n=3)

        st.subheader("Recommended Options")
        for i, s in enumerate(best3, start=1):
            st.markdown(
                f"**{i}. {s['club']}** — {s['shot_type']} | {s['trajectory']}  "
                f"(Carry ≈ {s['carry']:.1f} yds, diff {s['diff']:.1f})"
            )
            st.caption(explain_shot_choice(s, final_target))

    # ---- Scoring Shot Yardage Table (DESCENDING) ---- #
    st.subheader("Scoring Shot Yardage Table")
    df_scoring = pd.DataFrame(scoring_shots)
    df_scoring = df_scoring[["carry", "club", "shot_type", "trajectory"]]
    df_scoring.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
    df_scoring = df_scoring.sort_values("Carry (yds)", ascending=False)
    df_scoring = df_scoring.reset_index(drop=True)
    st.dataframe(df_scoring, use_container_width=True)

    # ---- Full Bag Yardage Table (DESCENDING) ---- #
    st.subheader("Full Bag Yardages")
    df_full = pd.DataFrame(full_bag)
    df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
    df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
    df_full["Total (yds)"] = df_full["Total (yds)"].round(1)
    df_full = df_full.sort_values("Carry (yds)", ascending=False)
    df_full = df_full.reset_index(drop=True)
    st.dataframe(df_full, use_container_width=True)

    # ---- Definitions ---- #
    with st.expander("Definitions"):
        st.markdown("**Wind Direction**")
        st.markdown(
            "- **Into**: Wind blowing toward you from the target (headwind).\n"
            "- **Down**: Wind blowing from behind you toward the target (tailwind).\n"
            "- **Cross**: Wind mostly left-to-right or right-to-left.\n"
            "- **None**: Calm or wind too light to matter."
        )

        st.markdown("**Wind Strength**")
        st.markdown(
            "- **Light**: Roughly 0–7 mph. Small effect, a few yards at most.\n"
            "- **Medium**: Around 8–15 mph. Enough to change club selection.\n"
            "- **Heavy**: 16+ mph. Strong wind that significantly affects distance.\n"
            "- **None**: Ignore wind in the calculation."
        )

        st.markdown("**Lie**")
        st.markdown(
            "- **Good**: Fairway, tee, or clean first cut. Normal strike expected.\n"
            "- **Ok**: Light rough, small slope, ball slightly above/below feet.\n"
            "- **Bad**: Thick rough, ball sitting down, bad stance, or wet/heavy lie. "
            "Expect the ball to come out shorter."
        )

        st.markdown("**Elevation**")
        st.markdown(
            "- **Flat**: No real change in height from ball to target.\n"
            "- **Slight Uphill**: Target a little higher than you (plays ~5 yards longer).\n"
            "- **Moderate Uphill**: Noticeably uphill (plays ~10 yards longer).\n"
            "- **Slight Downhill**: Target a little lower (plays ~5 yards shorter).\n"
            "- **Moderate Downhill**: Clearly downhill (plays ~10 yards shorter)."
        )


if __name__ == "__main__":
    main()
