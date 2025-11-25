import streamlit as st
import pandas as pd

BASELINE_DRIVER_SPEED = 100.0  # mph

# Full-swing wedge carries at 100 mph
FULL_WEDGE_CARRIES = {
    "PW": 121,
    "GW": 107,
    "SW":  92,
    "LW":  78,
}

# Full bag baseline (from your earlier table)
FULL_BAG_BASE = [
    ("Driver", 148, 13,   2500, 233, 253),
    ("3W",     140, 14.5, 3300, 216, 233),
    ("3H",     135, 16,   3900, 202, 220),
    ("4i",     128, 14.5, 4600, 182, 194),
    ("5i",     122, 15.5, 5000, 172, 185),
    ("6i",     116, 17,   5400, 162, 172),
    ("7i",     110, 18.5, 6200, 151, 161),
    ("8i",     104, 20.5, 7000, 139, 149),
    ("9i",      98, 23,   7800, 127, 137),
    ("PW",      92, 28,   8500, 118, 124),
    ("GW",      86, 30,   9000, 104, 110),
    ("SW",      81, 32,   9500,  89,  95),
    ("LW",      75, 34,  10500,  75,  81),
]

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
    "none":   0,
    "light":  5,
    "medium": 10,
    "heavy":  20,
}

# --------- Core Functions ---------

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

def build_full_bag(driver_speed_mph):
    out = []
    for club, bs, launch, spin, carry, total in FULL_BAG_BASE:
        out.append({
            "Club": club,
            "Ball Speed (mph)": scale_value(bs, driver_speed_mph),
            "Launch (°)": launch,
            "Spin (rpm)": spin,
            "Carry (yds)": scale_value(carry, driver_speed_mph),
            "Total (yds)": scale_value(total, driver_speed_mph),
        })
    return out

def adjust_for_wind(target, wind_dir, strength):
    wind_mph = WIND_STRENGTH_MAP.get(strength, 0)
    scale = min(max(target / 150, 0.5), 1.2)

    if wind_dir == "into":
        return target + wind_mph * 0.9 * scale
    if wind_dir == "down":
        return target - wind_mph * 0.4 * scale
    if wind_dir == "cross":
        return target + wind_mph * 0.1 * scale
    return target

def apply_elevation(target, label):
    label = label.lower()
    if "slight up" in label:
        return target + 5
    if "moderate up" in label:
        return target + 10
    if "slight down" in label:
        return target - 5
    if "moderate down" in label:
        return target - 10
    return target

def apply_lie(target, lie):
    if lie == "ok":
        return target * 1.05
    if lie == "bad":
        return target * 1.12
    return target

def recommend_shots(target, shots, n=3):
    for s in shots:
        s["diff"] = abs(s["carry"] - target)
    return sorted(shots, key=lambda x: x["diff"])[:n]

# --------- Streamlit App ---------

def main():
    st.title("Golf Shot Selector")

    driver_speed = st.slider("Current Driver Speed (mph)", 90, 115, 100)

    scoring_shots = build_scoring_shots(driver_speed)
    full_bag = build_full_bag(driver_speed)

    target = st.number_input("Target Carry Distance (yards)", 10.0, 300.0, 150.0)

    c1, c2, c3 = st.columns(3)
    with c1:
        wind_dir = st.selectbox("Wind Direction", ["None", "Into", "Down", "Cross"])
    with c2:
        wind_strength = st.selectbox("Wind Strength", ["None", "Light", "Medium", "Heavy"])
    with c3:
        lie = st.selectbox("Lie", ["Good", "Ok", "Bad"])

    elevation = st.selectbox("Elevation", [
        "Flat", "Slight Uphill", "Moderate Uphill",
        "Slight Downhill", "Moderate Downhill"
    ])

    # Convert to lowercase for logic
    wind_dir = wind_dir.lower()
    wind_strength = wind_strength.lower()
    lie = lie.lower()

    if st.button("Suggest Shots"):
        after_wind = adjust_for_wind(target, wind_dir, wind_strength)
        after_elev = apply_elevation(after_wind, elevation)
        final_target = apply_lie(after_elev, lie)

        st.markdown(f"### Adjusted Target: **{final_target:.1f} yds**")

        best3 = recommend_shots(final_target, scoring_shots)

        st.subheader("Recommended Shots")
        for i, s in enumerate(best3, start=1):
            st.markdown(
                f"**{i}. {s['club']}** — {s['shot_type']} | {s['trajectory']} "
                f"(Carry ≈ {s['carry']:.1f} yd, diff {s['diff']:.1f})"
            )

# ---------- Scoring Shot Table ----------
st.subheader("Scoring Shot Yardage Table")
df_scoring = pd.DataFrame(scoring_shots)
df_scoring = df_scoring[["carry", "club", "shot_type", "trajectory"]]
df_scoring.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
df_scoring = df_scoring.sort_values("Carry (yds)", ascending=False)  # DESCENDING
st.dataframe(df_scoring, use_container_width=True)

# ---------- Full Bag Table ----------
st.subheader("Full Bag Yardages")
df_full = pd.DataFrame(full_bag)
df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
df_full["Total (yds)"] = df_full["Total (yds)"].round(1)
df_full = df_full.sort_values("Carry (yds)", ascending=False)  # DESCENDING
st.dataframe(df_full, use_container_width=True)


if __name__ == "__main__":
    main()
