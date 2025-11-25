import streamlit as st
import pandas as pd

BASELINE_DRIVER_SPEED = 100.0  # mph

# Full-swing wedge carries at 100 mph (center values)
FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW":  92,
    "LW":  78,
}

# Shot-type multipliers
SHOT_MULTIPLIERS = {
    "Full":        1.00,
    "Choke-Down":  0.94,
    "3/4":         0.80,
    "1/2":         0.60,
    "1/4":         0.40,
}

# Scoring shots: club, shot type, trajectory
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


def scale_value(base_value, driver_speed_mph):
    """Scale baseline carry with driver speed."""
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


def build_scoring_shots(driver_speed_mph):
    """All scoring shots (PW–LW plus shot types) for given driver speed."""
    shots = []
    for club, shot_type, traj in SCORING_DEFS:
        full_carry = scale_value(FULL_WEDGE_CARRIES[club], driver_speed_mph)
        carry = full_carry * SHOT_MULTIPLIERS[shot_type]
        shots.append({
            "club": club,
            "shot_type": shot_type,
            "trajectory": traj,
            "carry": carry,
        })
    return shots


def adjust_for_wind(target, wind_dir, wind_strength_label):
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
    # 75 yds  -> 0.5x
    # 150 yds -> 1.0x
    # 200+ yds-> 1.2x (capped)
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
    # "none" or anything else: no change

    return adjusted


def apply_elevation_adjustment(target, elevation_label):
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
    else:  # flat or unknown
        delta = 0.0

    return target + delta


def apply_lie_adjustment(target, lie_label):
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


def recommend_shots(target_carry, scoring_shots, top_n=3):
    """Return top_n scoring shots closest to target."""
    for s in scoring_shots:
        s["diff"] = abs(s["carry"] - target_carry)
    return sorted(scoring_shots, key=lambda s: s["diff"])[:top_n]


def main():
    st.title("Golf Shot Selector")

    # Inputs
    driver_speed = st.slider("Current Driver Speed (mph)", 90, 115, 100)
    scoring_shots = build_scoring_shots(driver_speed)

    target = st.number_input(
        "Target Carry Distance (yards)",
        min_value=10.0,
        max_value=300.0,
        value=150.0,
        step=1.0,
    )

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

    wind_dir = wind_dir_label.lower()
    wind_strength = wind_strength_label.lower()
    lie = lie_label.lower()

    if st.button("Suggest Shots"):
        wind_adjusted = adjust_for_wind(target, wind_dir, wind_strength)
        elev_adjusted = apply_elevation_adjustment(wind_adjusted, elevation_label)
        final_target = apply_lie_adjustment(elev_adjusted, lie)

        st.markdown(f"**Adjusted target:** {final_target:.1f} yds")

        best3 = recommend_shots(final_target, scoring_shots, top_n=3)

        st.subheader("Recommended Options")
        for i, s in enumerate(best3, start=1):
            st.markdown(
                f"**{i}. {s['club']}** — {s['shot_type']} | {s['trajectory']}  "
                f"(Carry ≈ {s['carry']:.1f} yds, diff {s['diff']:.1f})"
            )

    # Yardage table for quick reference
    st.subheader("Scoring Shot Yardage Table")
    df = pd.DataFrame(scoring_shots)
    df = df[["carry", "club", "shot_type", "trajectory"]]
    df = df.sort_values("carry")  # ascending by carry
    df.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
    st.dataframe(df, use_container_width=True)

    # Definitions / help text
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
            "- **Bad**: Thick rough, ball sitting down, bad stance, or wet/heavy lie. Expect the ball to come out shorter."
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
