import streamlit as st

BASELINE_DRIVER_SPEED = 100.0  # mph

FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW":  92,
    "LW":  78,
}

SHOT_MULTIPLIERS = {
    "Full":        1.00,
    "Choke-Down":  0.94,
    "3/4":         0.80,
    "1/2":         0.60,
    "1/4":         0.40,
}

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

WIND_STRENGTH_MAP = {
    "none":  0,
    "light": 5,
    "medium": 10,
    "heavy": 20,
}


def scale_value(base_value, driver_speed_mph):
    return base_value * (driver_speed_mph / BASELINE_DRIVER_SPEED)


def build_scoring_shots(driver_speed_mph):
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


def apply_lie_adjustment(target, lie_label):
    lie = lie_label.lower().strip()
    if lie == "good":
        mult = 1.00
    elif lie == "ok":
        mult = 1.05
    elif lie == "bad":
        mult = 1.12
    else:
        mult = 1.00
    return target * mult


def recommend_shots(target_carry, scoring_shots, top_n=3):
    for s in scoring_shots:
        s["diff"] = abs(s["carry"] - target_carry)
    return sorted(scoring_shots, key=lambda s: s["diff"])[:top_n]


def main():
    st.title("Golf Yardage Helper")

    driver_speed = st.slider("Current Driver Speed (mph)", 90, 115, 100)
    scoring_shots = build_scoring_shots(driver_speed)

    target = st.number_input("Target Carry Distance (yards)", min_value=10.0, max_value=300.0, value=150.0, step=1.0)

    col1, col2, col3 = st.columns(3)
    with col1:
        wind_dir = st.selectbox("Wind Direction", ["none", "into", "down", "cross"])
    with col2:
        wind_strength = st.selectbox("Wind Strength", ["none", "light", "medium", "heavy"])
    with col3:
        lie = st.selectbox("Lie", ["good", "ok", "bad"])

    if st.button("Suggest Shots"):
        wind_adjusted = adjust_for_wind(target, wind_dir, wind_strength)
        final_target = apply_lie_adjustment(wind_adjusted, lie)

        st.write(f"**Adjusted target:** {final_target:.1f} yds")

        best3 = recommend_shots(final_target, scoring_shots, top_n=3)

        for i, s in enumerate(best3, start=1):
            st.write(
                f"**{i}. {s['club']}** — {s['shot_type']} | {s['trajectory']}  "
                f"(Carry ≈ {s['carry']:.1f} yds, diff {s['diff']:.1f})"
            )


if __name__ == "__main__":
    main()
