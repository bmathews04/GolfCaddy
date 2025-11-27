import streamlit as st
import pandas as pd
import numpy as np
import math

# Import the strokes-gained / distance engine as a module
import strokes_gained_engine as sge

# Page config
st.set_page_config(
    page_title="Golf Caddy",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------------------------------------------
# Session-state defaults
# -------------------------------------------------------------------

DEFAULTS = {
    "mode": "Quick",              # Quick vs Advanced Caddy mode
    "skill": "Intermediate",      # Ball striking consistency
    "tendency": "Neutral",        # Usually Short / Neutral / Usually Long
    "tournament_mode": False,     # Tournament vs Normal play
    "handicap_factor": 1.0,       # SG / dispersion scaling by handicap
    "driver_speed": 100.0,        # mph, used to scale the bag
}


def init_session_state():
    """Initialize Streamlit session_state with safe defaults."""
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


# Call once at import time so everything below can rely on session_state
init_session_state()

# -------------------------------------------------------------------
# Simple club-category helper for tables (rest of your file continues)
# -------------------------------------------------------------------

def _category_for_club(club: str) -> str:
    """Map a club name to a rough category label (for tables/dispersion)."""
    c = club.lower()
    if c in ("driver",):
        return "driver"
    if c in ("3w", "5w"):
        return "wood"
    if c in ("3h", "4h", "5h"):
        return "hybrid"
    if c in ("4i", "5i"):
        return "long_iron"
    if c in ("6i", "7i"):
        return "mid_iron"
    if c in ("8i", "9i"):
        return "short_iron"
    return "scoring_wedge"



# ------------------------------------------------------------
# Sidebar: Player profile + tournament toggle
# ------------------------------------------------------------

with st.sidebar:
    st.header("Player Profile & Modes")

    handicap = st.slider(
        "Approx Handicap Index",
        min_value=0.0,
        max_value=30.0,
        value=14.0,
        step=0.1,
        help="Used to tune the strokes-gained baseline to your scoring level.",
    )
    if handicap <= 5:
        sg_profile_factor = 0.92
    elif handicap <= 10:
        sg_profile_factor = 1.00
    elif handicap <= 20:
        sg_profile_factor = 1.05
    else:
        sg_profile_factor = 1.10

    st.caption(
        "Lower handicap = slightly tougher strokes-gained baseline. "
        "Higher handicap = more forgiving baseline."
    )

    tournament_mode = st.checkbox(
        "Tournament Mode (USGA Legal View)",
        value=False,
        help="Play tab shows only raw yardages when enabled.",
    )

    st.markdown("---")
    st.markdown("**About Golf Caddy**")
    st.caption(
        "Use all features in casual rounds and practice. "
        "In tournament play, enable Tournament Mode so the Play tab behaves like a "
        "digital yardage book (no plays-like or strategy advice)."
    )

# ------------------------------------------------------------
# Main header & shared bag data
# ------------------------------------------------------------

st.title("Golf Caddy")

driver_speed = st.slider(
    "Current Driver Speed (mph)",
    min_value=90.0,
    max_value=120.0,
    value=float(st.session_state.driver_speed),
    step=1.0,  # or 0.5 if you want half-mph increments
    help="Used to scale your entire bag's distances from a 100 mph baseline.",
)

st.session_state.driver_speed = float(driver_speed)

all_shots_base, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)

# Tabs
tab_play, tab_range, tab_yardages, tab_strategy, tab_prep, tab_info = st.tabs(
    ["Play", "Range", "Yardages", "Par Strategy", "Tournament Prep", "How it Works"]
)

# ------------------------------------------------------------
# PLAY TAB (Caddy / Tournament)
# ------------------------------------------------------------

with tab_play:
    if tournament_mode:
        # ---------------- TOURNAMENT MODE ---------------- #
        st.subheader("Tournament Mode: Raw Yardage Book")

        col_tm1, col_tm2 = st.columns([2, 1])
        with col_tm1:
            pin_yardage = st.number_input(
                "Pin Yardage (yards)",
                min_value=10.0,
                max_value=350.0,
                value=150.0,
                step=1.0,
                help="Measured distance from your rangefinder or GPS.",
            )
        with col_tm2:
            st.markdown("**Tournament Note**")
            st.caption(
                "Use this screen as a digital yardage book. "
                "No plays-like calculations or strategy recommendations are shown."
            )

        st.markdown("### Raw Full-Bag Yardages")
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(0).astype(int)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(0).astype(int)

        dispersion_list = []
        for _, row in df_full.iterrows():
            cat = _category_for_club(row["Club"])
            sigma = get_dispersion_sigma(cat)
            dispersion_list.append(round(sigma))

        df_full["Dispersion (±yds)"] = dispersion_list
        df_full = df_full[
            [
                "Club",
                "Carry (yds)",
                "Total (yds)",
                "Dispersion (±yds)",
                "Ball Speed (mph)",
                "Launch (°)",
                "Spin (rpm)",
            ]
        ]
        df_full = df_full.reset_index(drop=True)
        st.dataframe(df_full, use_container_width=True)

        st.markdown("### Raw Scoring Shot Yardages (Wedges & Partials)")
        df_score = pd.DataFrame(scoring_shots)
        df_score = df_score[["carry", "club", "shot_type", "trajectory"]]
        df_score.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
        df_score["Carry (yds)"] = df_score["Carry (yds)"].round(0).astype(int)
        df_score = df_score.sort_values("Carry (yds)", ascending=False).reset_index(
            drop=True
        )
        st.dataframe(df_score, use_container_width=True)

        st.info(
            "In Tournament Mode, Golf Caddy acts like a digital yardage book. "
            "No plays-like calculations, strategy suggestions, or club recommendations are used."
        )

    else:
        # ---------------- CADDY MODE ---------------- #
        st.subheader("On-Course Caddy Mode")

        mode = st.radio(
            "Mode",
            ["Quick", "Advanced"],
            horizontal=True,
            index=0 if st.session_state.mode == "Quick" else 1,
            help=(
                "Quick mode = minimal inputs for fast decisions. "
                "Advanced mode = tweak green layout, trouble, and tendencies."
            ),
        )
        st.session_state.mode = mode

        # Core inputs
        pin_col1, pin_col2 = st.columns([2, 1])
        with pin_col1:
            target_pin = st.number_input(
                "Pin Yardage (yards)",
                min_value=10.0,
                max_value=350.0,
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
                help="Stronger winds have a bigger impact on plays-like yardage.",
            )

        with col_b:
            lie_label = st.radio(
                "Ball Lie",
                ["Good", "Ok", "Bad"],
                horizontal=True,
                help="Good = fairway/tee, Ok = light rough / small slope, Bad = heavy rough / poor stance.",
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
                    "Auto-select strategy",
                    value=True,
                    help="Let Golf Caddy adjust Conservative/Balanced/Aggressive based on the situation.",
                )
                manual_strategy = st.radio(
                    "Strategy (if not auto)",
                    [STRATEGY_BALANCED, STRATEGY_CONSERVATIVE, STRATEGY_AGGRESSIVE],
                    index=0,
                    help="Conservative = safety first; Aggressive = chase pins when trouble is minimal.",
                )
                strategy_label = manual_strategy
            else:
                use_auto_strategy = True
                strategy_label = STRATEGY_BALANCED
                st.markdown("**Strategy**")
                st.caption(
                    "Quick mode always uses auto strategy based on distance and trouble."
                )

        # Advanced controls
        if mode == "Advanced":
            with st.expander("Advanced: Green, Trouble, Pin Position & Tendencies (Optional)"):
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
                        )
                    with colb:
                        back_yards = st.number_input(
                            "Back of green (yards)",
                            min_value=0.0,
                            max_value=400.0,
                            value=0.0,
                            step=1.0,
                        )
                    st.caption(
                        "If both front and back are set and back > front, "
                        "target is the center of the green."
                    )

                st.markdown("---")
                st.markdown("**Trouble Around the Green**")
                t1, t2, t3, t4 = st.columns(4)
                with t1:
                    trouble_short_label = st.selectbox(
                        "Trouble Short",
                        ["None", "Mild", "Severe"],
                    )
                with t2:
                    trouble_long_label = st.selectbox(
                        "Trouble Long",
                        ["None", "Mild", "Severe"],
                    )
                with t3:
                    trouble_left_label = st.selectbox(
                        "Trouble Left",
                        ["None", "Mild", "Severe"],
                    )
                with t4:
                    trouble_right_label = st.selectbox(
                        "Trouble Right",
                        ["None", "Mild", "Severe"],
                    )

                green_firmness_label = st.selectbox(
                    "Green Firmness",
                    ["Soft", "Medium", "Firm"],
                    help="Soft = stops close to carry distance, Firm = more roll-out.",
                )

                st.markdown("---")
                st.markdown("**Pin Lateral Position**")
                pw1, pw2 = st.columns(2)
                with pw1:
                    green_width = st.number_input(
                        "Green width (yards)",
                        min_value=0.0,
                        max_value=60.0,
                        value=0.0,
                        step=1.0,
                    )
                with pw2:
                    pin_side = st.selectbox(
                        "Pin side",
                        ["Center", "Left", "Right"],
                    )

                pin_lateral_offset = 0.0
                if green_width > 0:
                    half_w = green_width / 2.0
                    if pin_side == "Left":
                        pin_lateral_offset = -0.66 * half_w
                    elif pin_side == "Right":
                        pin_lateral_offset = 0.66 * half_w

                st.markdown("---")
                st.markdown("**Player Tendencies**")
                tendency = st.radio(
                    "Usual Miss (Distance)",
                    ["Neutral", "Usually Short", "Usually Long"],
                    horizontal=True,
                    index=["Neutral", "Usually Short", "Usually Long"].index(
                        st.session_state.tendency
                    ),
                    help="Used to bias plays-like yardage slightly if you typically miss short or long.",
                )
                st.session_state.tendency = tendency

                skill = st.radio(
                    "Ball Striking Consistency",
                    ["Recreational", "Intermediate", "Highly Consistent"],
                    index=["Recreational", "Intermediate", "Highly Consistent"].index(
                        st.session_state.skill
                    ),
                    help="Used to scale dispersion windows and SG simulations.",
                )
                st.session_state.skill = skill
        else:
            use_center = False
            front_yards = 0.0
            back_yards = 0.0
            trouble_short_label = "None"
            trouble_long_label = "None"
            trouble_left_label = "None"
            trouble_right_label = "None"
            green_firmness_label = "Medium"
            green_width = 0.0
            pin_lateral_offset = 0.0
            tendency = st.session_state.tendency
            skill = st.session_state.skill

        # Skill factor
        skill_norm = skill.lower()
        if skill_norm == "recreational":
            skill_factor = 1.3
        elif skill_norm == "highly consistent":
            skill_factor = 0.8
        else:
            skill_factor = 1.0

        # Normalize
        wind_dir = wind_dir_label.lower()
        wind_strength = wind_strength_label.lower()
        lie = lie_label.lower()

        tendency_adj = 0.0
        if tendency == "Usually Short":
            tendency_adj = 3.0
        elif tendency == "Usually Long":
            tendency_adj = -3.0

        if st.button("Suggest Shots ✅"):
            with st.spinner("Crunching the numbers..."):
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

                after_wind = adjust_for_wind(raw_target, wind_dir, wind_strength)
                after_elev = apply_elevation(after_wind, elevation_label)
                final_target = apply_lie(after_elev, lie) + tendency_adj
                plays_like = final_target

                st.markdown(
                    f"### Plays-Like Yardage: **{round(plays_like)} yds** "
                    f"({'center of green' if using_center else 'to pin'})"
                )

                if use_auto_strategy:
                    dist = plays_like
                    if any(lbl == "Severe" for lbl in [
                        trouble_short_label,
                        trouble_long_label,
                        trouble_left_label,
                        trouble_right_label,
                    ]):
                        strategy_label = STRATEGY_CONSERVATIVE
                    elif dist < 120 and all(
                        lbl == "None"
                        for lbl in [
                            trouble_short_label,
                            trouble_long_label,
                            trouble_left_label,
                            trouble_right_label,
                        ]
                    ):
                        strategy_label = STRATEGY_AGGRESSIVE
                    else:
                        strategy_label = STRATEGY_BALANCED

                ranked = recommend_shots_with_sg(
                    target_total=plays_like,
                    candidates=all_shots_base,
                    short_trouble_label=trouble_short_label,
                    long_trouble_label=trouble_long_label,
                    left_trouble_label=trouble_left_label,
                    right_trouble_label=trouble_right_label,
                    green_firmness_label=green_firmness_label,
                    strategy_label=strategy_label,
                    start_distance_yards=plays_like,
                    start_surface="fairway",
                    front_yards=front_yards,
                    back_yards=back_yards,
                    skill_factor=skill_factor,
                    pin_lateral_offset=pin_lateral_offset,
                    green_width=green_width,
                    n_sim=DEFAULT_N_SIM,
                    top_n=5,
                    sg_profile_factor=sg_profile_factor,
                )

                if not ranked:
                    st.warning("No suitable shots found for this plays-like yardage.")
                else:
                    st.subheader("Recommended Options")
                    for i, shot in enumerate(ranked, start=1):
                        st.markdown(
                            f"**{i}. {shot['club']} — {shot['shot_type']}** | "
                            f"{shot['trajectory']}  "
                            f"(Carry ≈ {round(shot['carry'])} yds, "
                            f"Total ≈ {round(shot['total'])} yds, "
                            f"SG ≈ {shot['sg']:.3f})"
                        )
                        with st.expander(f"Why this shot? (#{i})", expanded=(i == 1)):
                            st.write(shot["reason"])

                    # 2D shot pattern preview for top recommendation
                    top = ranked[0]
                    st.markdown("### Shot Pattern Preview (Top Recommendation)")

                    cat = top["category"]
                    sigma_depth = get_dispersion_sigma(cat) * skill_factor
                    sigma_lat = get_lateral_sigma(cat) * skill_factor

                    mu_depth = top["total"] - plays_like
                    mu_lat = 0.0

                    n_samples = 400
                    depth_errors = np.random.normal(mu_depth, sigma_depth, n_samples)
                    lat_errors = np.random.normal(mu_lat, sigma_lat, n_samples)

                    df_disp = pd.DataFrame(
                        {"Depth (yds)": depth_errors, "Lateral (yds)": lat_errors}
                    )

                    points = (
                        alt.Chart(df_disp)
                        .mark_point(filled=True, opacity=0.35, size=40)
                        .encode(
                            x=alt.X(
                                "Lateral (yds):Q",
                                title="Left (-) / Right (+) relative to target line",
                            ),
                            y=alt.Y(
                                "Depth (yds):Q",
                                title="Short (-) / Long (+) vs plays-like yardage",
                            ),
                        )
                    )
                    vline = (
                        alt.Chart(pd.DataFrame({"x": [0]}))
                        .mark_rule(strokeDash=[4, 4])
                        .encode(x="x:Q")
                    )
                    hline = (
                        alt.Chart(pd.DataFrame({"y": [0]}))
                        .mark_rule(strokeDash=[4, 4])
                        .encode(y="y:Q")
                    )

                    charts = [points, vline, hline]

                    if green_width > 0:
                        rect_df = pd.DataFrame(
                            [
                                {
                                    "x0": -green_width / 2.0,
                                    "x1": green_width / 2.0,
                                    "y0": -5.0,
                                    "y1": 5.0,
                                }
                            ]
                        )
                        green_rect = (
                            alt.Chart(rect_df)
                            .mark_rect(fillOpacity=0.08)
                            .encode(
                                x="x0:Q",
                                x2="x1:Q",
                                y="y0:Q",
                                y2="y1:Q",
                            )
                        )
                        charts.append(green_rect)

                    chart = alt.layer(*charts).properties(
                        width="container",
                        height=320,
                        title=f"{top['club']} — {top['shot_type']} (simulated pattern)",
                    )

                    with st.expander("Show 2D shot dispersion (simulation)"):
                        st.altair_chart(chart, use_container_width=True)

                        radial = np.sqrt(depth_errors**2 + lat_errors**2)
                        pct_within_5 = (radial <= 5.0).mean() * 100.0
                        pct_within_10 = (radial <= 10.0).mean() * 100.0

                        avg_depth = depth_errors.mean()
                        avg_lat = lat_errors.mean()

                        summary_lines = []
                        summary_lines.append(
                            f"- ~{pct_within_5:.0f}% of simulated shots finish within **5 yds** of the target."
                        )
                        summary_lines.append(
                            f"- ~{pct_within_10:.0f}% finish within **10 yds** of the target."
                        )

                        if green_width > 0:
                            half_w = green_width / 2.0
                            on_green_mask = (
                                (np.abs(depth_errors) <= 5.0)
                                & (np.abs(lat_errors) <= half_w)
                            )
                            pct_on_green = on_green_mask.mean() * 100.0
                            summary_lines.append(
                                f"- ~{pct_on_green:.0f}% of shots land inside the **green area** "
                                f"(±5 yds depth, ±{half_w:.1f} yds lateral)."
                            )

                        if abs(avg_depth) >= 0.5:
                            depth_dir = "long" if avg_depth > 0 else "short"
                            summary_lines.append(
                                f"- Average depth bias: **{abs(avg_depth):.1f} yds {depth_dir}**."
                            )
                        else:
                            summary_lines.append(
                                "- Average depth bias: essentially **pin high** on average."
                            )

                        if abs(avg_lat) >= 0.5:
                            lat_dir = "right" if avg_lat > 0 else "left"
                            summary_lines.append(
                                f"- Average lateral bias: **{abs(avg_lat):.1f} yds {lat_dir}**."
                            )
                        else:
                            summary_lines.append(
                                "- Average lateral bias: essentially **straight at the target line**."
                            )

                        st.markdown("#### Pattern Summary")
                        st.markdown("\n".join(summary_lines))

# ------------------------------------------------------------
# RANGE TAB (practice)
# ------------------------------------------------------------

with tab_range:
    st.subheader("Range Mode (Practice)")

    practice_target = st.number_input(
        "Practice Yardage (plays-like target, yards)",
        min_value=10.0,
        max_value=300.0,
        value=150.0,
        step=1.0,
        help="Use this to build a stock yardage map and dial in specific distances.",
    )

    practice_strategy = st.radio(
        "Practice Focus",
        [STRATEGY_BALANCED, STRATEGY_CONSERVATIVE, STRATEGY_AGGRESSIVE],
        index=0,
        horizontal=True,
        help="Balanced = normal target practice, Conservative = emphasize center of green, Aggressive = tighter windows.",
    )

    practice_skill_label = st.session_state.skill
    practice_skill_norm = practice_skill_label.lower()
    if practice_skill_norm == "recreational":
        practice_skill_factor = 1.3
    elif practice_skill_norm == "highly consistent":
        practice_skill_factor = 0.8
    else:
        practice_skill_factor = 1.0

    if st.button("Suggest Practice Shots 🎯"):
        ranked_practice = recommend_shots_with_sg(
            target_total=practice_target,
            candidates=all_shots_base,
            short_trouble_label="None",
            long_trouble_label="None",
            left_trouble_label="None",
            right_trouble_label="None",
            green_firmness_label="Medium",
            strategy_label=practice_strategy,
            start_distance_yards=practice_target,
            start_surface="fairway",
            front_yards=0.0,
            back_yards=0.0,
            skill_factor=practice_skill_factor,
            pin_lateral_offset=0.0,
            green_width=0.0,
            n_sim=DEFAULT_N_SIM,
            top_n=5,
            sg_profile_factor=sg_profile_factor,
        )

        if not ranked_practice:
            st.warning("No suitable practice shots found for this yardage.")
        else:
            st.markdown("### Recommended Shots to Work On")
            for i, shot in enumerate(ranked_practice, start=1):
                st.markdown(
                    f"**{i}. {shot['club']} — {shot['shot_type']}** "
                    f"(Carry ≈ {round(shot['carry'])} yds, "
                    f"Total ≈ {round(shot['total'])} yds, "
                    f"SG ≈ {shot['sg']:.3f})"
                )

            # 2D pattern for top practice shot
            top_p = ranked_practice[0]
            st.markdown("### Shot Pattern Preview (Top Practice Shot)")

            cat = top_p["category"]
            sigma_depth = get_dispersion_sigma(cat) * practice_skill_factor
            sigma_lat = get_lateral_sigma(cat) * practice_skill_factor
            mu_depth = top_p["total"] - practice_target
            mu_lat = 0.0

            n_samples = 400
            depth_errors = np.random.normal(mu_depth, sigma_depth, n_samples)
            lat_errors = np.random.normal(mu_lat, sigma_lat, n_samples)

            df_disp = pd.DataFrame(
                {"Depth (yds)": depth_errors, "Lateral (yds)": lat_errors}
            )

            points = (
                alt.Chart(df_disp)
                .mark_point(filled=True, opacity=0.35, size=40)
                .encode(
                    x=alt.X(
                        "Lateral (yds):Q",
                        title="Left (-) / Right (+) relative to target line",
                    ),
                    y=alt.Y(
                        "Depth (yds):Q",
                        title="Short (-) / Long (+) vs practice yardage",
                    ),
                )
            )
            vline = (
                alt.Chart(pd.DataFrame({"x": [0]}))
                .mark_rule(strokeDash=[4, 4])
                .encode(x="x:Q")
            )
            hline = (
                alt.Chart(pd.DataFrame({"y": [0]}))
                .mark_rule(strokeDash=[4, 4])
                .encode(y="y:Q")
            )

            chart = alt.layer(points, vline, hline).properties(
                width="container",
                height=320,
                title=f"{top_p['club']} — {top_p['shot_type']} (practice pattern)",
            )

            st.altair_chart(chart, use_container_width=True)

            st.caption(
                "Use this pattern to visualize your misses on the range. "
                "Your goal is not perfection—just shrinking the pattern over time."
            )

# ------------------------------------------------------------
# YARDAGES TAB
# ------------------------------------------------------------

with tab_yardages:
    st.subheader("Bag Yardages & Scoring Shots")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Full-Bag Yardages")
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(0).astype(int)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(0).astype(int)

        dispersion_list = []
        for _, row in df_full.iterrows():
            cat = _category_for_club(row["Club"])
            sigma = get_dispersion_sigma(cat)
            dispersion_list.append(round(sigma))

        df_full["Dispersion (±yds)"] = dispersion_list
        df_full = df_full[
            [
                "Club",
                "Carry (yds)",
                "Total (yds)",
                "Dispersion (±yds)",
                "Ball Speed (mph)",
                "Launch (°)",
                "Spin (rpm)",
            ]
        ]
        df_full = df_full.reset_index(drop=True)
        st.dataframe(df_full, use_container_width=True)

    with c2:
        st.markdown("### Scoring Shot Yardages (Wedges & Partials)")
        df_score = pd.DataFrame(scoring_shots)
        df_score = df_score[["carry", "club", "shot_type", "trajectory"]]
        df_score.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
        df_score["Carry (yds)"] = df_score["Carry (yds)"].round(0).astype(int)
        df_score = df_score.sort_values("Carry (yds)", ascending=False).reset_index(
            drop=True
        )
        st.dataframe(df_score, use_container_width=True)

# ------------------------------------------------------------
# PAR STRATEGY TAB
# ------------------------------------------------------------

with tab_strategy:
    st.subheader("Tee-to-Green Par Strategy")

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        par_value = st.selectbox("Hole Par", [3, 4, 5], index=1)
    with col_h2:
        if par_value == 3:
            default_len = 160
            min_len, max_len = 90, 260
        elif par_value == 4:
            default_len = 410
            min_len, max_len = 280, 520
        else:
            default_len = 520
            min_len, max_len = 420, 650

        hole_yards = st.slider(
            "Hole Length (yards)",
            min_value=float(min_len),
            max_value=float(max_len),
            value=float(default_len),
            step=1.0,
            help="Measured total yardage from the tee markers you play.",
        )

    st.markdown("**Tee & Green Context**")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        fairway_width_label = st.selectbox(
            "Fairway Width",
            ["Narrow", "Medium", "Wide"],
        )
    with col_s2:
        green_width_strategy = st.slider(
            "Green Width (yards, left-to-right)",
            min_value=0.0,
            max_value=50.0,
            value=25.0,
            step=1.0,
        )
    with col_s3:
        st.caption(
            "Narrow fairways with severe trouble often reward a more conservative tee club."
        )

    st.markdown("**Trouble Severity Around the Hole**")
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        trouble_short_label_s = st.selectbox(
            "Trouble Short",
            ["None", "Mild", "Severe"],
        )
    with col_t2:
        trouble_long_label_s = st.selectbox(
            "Trouble Long",
            ["None", "Mild", "Severe"],
        )
    with col_t3:
        trouble_left_label_s = st.selectbox(
            "Trouble Left",
            ["None", "Mild", "Severe"],
        )
    with col_t4:
        trouble_right_label_s = st.selectbox(
            "Trouble Right",
            ["None", "Mild", "Severe"],
        )

    skill_label = st.session_state.skill
    skill_norm = skill_label.lower()
    if skill_norm == "recreational":
        strategy_skill_factor = 1.3
    elif skill_norm == "highly consistent":
        strategy_skill_factor = 0.8
    else:
        strategy_skill_factor = 1.0

    if st.button("Compute Hole Strategy 🧠"):
        if par_value == 3:
            st.markdown("### Par 3 Strategy")
            res = par3_strategy(
                hole_yards=hole_yards,
                candidates=all_shots_base,
                skill_factor=strategy_skill_factor,
                green_width=green_width_strategy,
                short_trouble_label=trouble_short_label_s,
                long_trouble_label=trouble_long_label_s,
                left_trouble_label=trouble_left_label_s,
                right_trouble_label=trouble_right_label_s,
                strategy_label=STRATEGY_BALANCED,
                sg_profile_factor=sg_profile_factor,
                n_sim=DEFAULT_N_SIM,
            )
            best = res.get("best")
            if not best:
                st.warning("No suitable clubs found for this Par 3 setup.")
            else:
                st.markdown(
                    f"**Recommended: {best['club']} — {best['shot_type']} "
                    f"(Total ≈ {round(best['total'])} yds)**"
                )
                st.markdown(
                    f"- Expected strokes from tee: **{best['expected_strokes']:.2f}**."
                )
                st.markdown(
                    f"- Hit-green probability (approx): **{best['p_on_green']*100:.0f}%**."
                )
                st.markdown(
                    f"- ~{best['p_within_5']*100:.0f}% within 5 yds; "
                    f"~{best['p_within_10']*100:.0f}% within 10 yds."
                )

                st.markdown("#### Alternate Club Options")
                alt_rows = []
                for alt in res["alternatives"]:
                    alt_rows.append(
                        {
                            "Club": alt["club"],
                            "Shot Type": alt["shot_type"],
                            "Total (yds)": round(alt["total"]),
                            "Diff vs Hole (yds)": round(alt["total"] - hole_yards),
                            "Strokes Gained (est)": round(alt["sg"], 3),
                        }
                    )
                df_par3 = pd.DataFrame(alt_rows)
                st.dataframe(df_par3, use_container_width=True)

        elif par_value == 4:
            st.markdown("### Par 4 Strategy")
            res4 = par4_strategy(
                hole_yards=hole_yards,
                full_bag=full_bag,
                skill_factor=strategy_skill_factor,
                fairway_width_label=fairway_width_label,
                tee_left_trouble_label=trouble_left_label_s,
                tee_right_trouble_label=trouble_right_label_s,
                sg_profile_factor=sg_profile_factor,
            )
            best4 = res4.get("best")
            if not best4:
                st.warning("No tee strategy could be computed for this Par 4.")
            else:
                st.markdown(
                    f"**Recommended Tee Club: {best4['tee_club']}** "
                    f"(avg total ≈ {round(best4['avg_total'])} yds)"
                )
                st.markdown(
                    f"- Remaining approach distance: **{round(best4['remaining_yards'])} yds**"
                )
                st.markdown(
                    f"- Expected score on this hole: **{best4['expected_score']:.2f}** strokes."
                )
                st.markdown(
                    f"- Strokes gained vs generic baseline: "
                    f"**{best4['sg_vs_baseline']:.2f}**."
                )
                st.markdown(
                    f"- Estimated fairway miss probability: "
                    f"**{best4['miss_prob']*100:.0f}%**."
                )

                st.markdown("#### Alternate Tee Options")
                rows4 = []
                for opt in res4["options"]:
                    rows4.append(
                        {
                            "Tee Club": opt["tee_club"],
                            "Avg Total (yds)": round(opt["avg_total"]),
                            "Remaining (yds)": round(opt["remaining_yards"]),
                            "Expected Score": round(opt["expected_score"], 2),
                            "Fairway Miss %": round(opt["miss_prob"] * 100),
                        }
                    )
                df_par4 = pd.DataFrame(rows4)
                st.dataframe(df_par4, use_container_width=True)

        else:
            st.markdown("### Par 5 Strategy")
            res5 = par5_strategy(
                hole_yards=hole_yards,
                full_bag=full_bag,
                skill_factor=strategy_skill_factor,
                fairway_width_label=fairway_width_label,
                tee_left_trouble_label=trouble_left_label_s,
                tee_right_trouble_label=trouble_right_label_s,
                sg_profile_factor=sg_profile_factor,
            )
            best_tee = res5.get("best_tee")
            if not best_tee:
                st.warning("No Par 5 strategy could be computed for this setup.")
            else:
                st.markdown(
                    f"**Recommended Tee Club: {best_tee['tee_club']}** "
                    f"(avg total ≈ {round(best_tee['avg_total'])} yds)"
                )
                st.markdown(
                    f"- Remaining after tee: **{round(res5['remaining_after_tee'])} yds**"
                )
                st.markdown(
                    f"- Overall strategy: **{res5['strategy']}** "
                    f"(expected score ≈ {res5['expected_score']:.2f} strokes)."
                )
                if res5["layup_score"] is not None:
                    st.markdown(
                        f"- Layup plan: target layup to **{round(res5['layup_target'])} yds**, "
                        f"expected score ≈ **{res5['layup_score']:.2f}**."
                    )
                if res5["go_for_it_score"] is not None:
                    st.markdown(
                        f"- Go-for-it plan: expected score ≈ "
                        f"**{res5['go_for_it_score']:.2f}**."
                    )

                st.caption(
                    "Use this to decide which Par 5s you should attack in two "
                    "versus treat as true three-shot holes."
                )

# ------------------------------------------------------------
# TOURNAMENT PREP TAB
# ------------------------------------------------------------

with tab_prep:
    st.subheader("Tournament Prep: Plays-Like Trainer")

    # Initialize scenario state
    if "prep_raw" not in st.session_state:
        st.session_state.prep_raw = 150.0
        st.session_state.prep_wind_dir = "Into"
        st.session_state.prep_wind_strength = "Medium"
        st.session_state.prep_elevation = "Slight Uphill"
        st.session_state.prep_lie = "Good"
        st.session_state.prep_temp = 75.0
        st.session_state.prep_pin_depth = "Middle"
        st.session_state.prep_green_firmness = "Medium"
        st.session_state.prep_user_estimate = 150.0

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("### Scenario")

        if st.button("Generate Random Scenario 🎲"):
            scen = generate_random_scenario()
            st.session_state.prep_raw = float(scen["raw_yards"])
            st.session_state.prep_wind_dir = scen["wind_dir"]
            st.session_state.prep_wind_strength = scen["wind_strength"]
            st.session_state.prep_elevation = scen["elevation"]
            st.session_state.prep_lie = scen["lie"]
            st.session_state.prep_temp = float(scen["temp_f"])
            st.session_state.prep_pin_depth = scen["pin_depth"]
            st.session_state.prep_green_firmness = scen["green_firmness"]

        raw_yards = st.number_input(
            "Raw (laser) yardage to pin (yards)",
            min_value=10.0,
            max_value=300.0,
            value=st.session_state.prep_raw,
            step=1.0,
            key="prep_raw",
        )

        wind_dir_options = ["None", "Into", "Down", "Cross"]
        wind_dir = st.selectbox(
            "Wind Direction",
            wind_dir_options,
            index=wind_dir_options.index(st.session_state.prep_wind_dir),
            key="prep_wind_dir",
        )

        wind_strength_options = ["None", "Light", "Medium", "Heavy"]
        wind_strength = st.selectbox(
            "Wind Strength",
            wind_strength_options,
            index=wind_strength_options.index(st.session_state.prep_wind_strength),
            key="prep_wind_strength",
        )

        elevation_options = [
            "Flat",
            "Slight Uphill",
            "Moderate Uphill",
            "Slight Downhill",
            "Moderate Downhill",
        ]
        elevation_label = st.selectbox(
            "Elevation",
            elevation_options,
            index=elevation_options.index(st.session_state.prep_elevation),
            key="prep_elevation",
        )

        lie_options = ["Good", "Ok", "Bad"]
        lie_label = st.selectbox(
            "Lie",
            lie_options,
            index=lie_options.index(st.session_state.prep_lie),
            key="prep_lie",
        )

        temp_f = st.slider(
            "Temperature (°F)",
            min_value=40.0,
            max_value=100.0,
            value=st.session_state.prep_temp,
            step=1.0,
            key="prep_temp",
            help="Cooler temps generally make the ball fly shorter; warmer temps slightly longer.",
        )

        pin_depth = st.selectbox(
            "Pin Depth on Green",
            ["Front", "Middle", "Back"],
            index=["Front", "Middle", "Back"].index(st.session_state.prep_pin_depth),
            key="prep_pin_depth",
        )

        green_firmness_prep = st.selectbox(
            "Green Firmness",
            ["Soft", "Medium", "Firm"],
            index=["Soft", "Medium", "Firm"].index(
                st.session_state.prep_green_firmness
            ),
            key="prep_green_firmness",
        )

        st.markdown("### Your Plays-Like Estimate")

        tendency_label = st.session_state.tendency  # same as used elsewhere
        user_estimate = st.number_input(
            "What do *you* think this shot plays as (yards)?",
            min_value=10.0,
            max_value=300.0,
            value=float(st.session_state.prep_user_estimate),
            step=1.0,
            key="prep_user_estimate",
        )

        if st.button("Check My Math ✅"):
            actual_plays_like = calculate_plays_like_yardage(
                raw_yards=raw_yards,
                wind_dir=wind_dir.lower(),
                wind_strength_label=wind_strength.lower(),
                elevation_label=elevation_label,
                lie_label=lie_label,
                tendency_label=tendency_label,
                temp_f=temp_f,
                baseline_temp_f=75.0,
            )

            diff = user_estimate - actual_plays_like
            abs_diff = abs(diff)

            st.markdown(
                f"**Actual plays-like yardage: {actual_plays_like:.1f} yds** "
                f"(you guessed {user_estimate:.1f} yds)"
            )

            if abs_diff <= 2:
                st.success(
                    f"Elite! You were within **{abs_diff:.1f} yds** — tour-level feel."
                )
            elif abs_diff <= 5:
                st.info(
                    f"Very solid. Within **{abs_diff:.1f} yds** — this is excellent for tournament golf."
                )
            elif abs_diff <= 10:
                st.warning(
                    f"Usable but room to tighten: off by **{abs_diff:.1f} yds**. "
                    "Try breaking wind & slope into simpler steps."
                )
            else:
                st.error(
                    f"Off by **{abs_diff:.1f} yds**. This is where decision-making can really cost shots. "
                    "Try re-checking your wind % and elevation rules."
                )

            # Show what Caddy would recommend for training purposes
            skill_label = st.session_state.skill
            skill_norm = skill_label.lower()
            if skill_norm == "recreational":
                prep_skill_factor = 1.3
            elif skill_norm == "highly consistent":
                prep_skill_factor = 0.8
            else:
                prep_skill_factor = 1.0

            ranked_prep = recommend_shots_with_sg(
                target_total=actual_plays_like,
                candidates=all_shots_base,
                short_trouble_label="None",
                long_trouble_label="None",
                left_trouble_label="None",
                right_trouble_label="None",
                green_firmness_label="Medium",
                strategy_label=STRATEGY_BALANCED,
                start_distance_yards=actual_plays_like,
                start_surface="fairway",
                front_yards=0.0,
                back_yards=0.0,
                skill_factor=prep_skill_factor,
                pin_lateral_offset=0.0,
                green_width=0.0,
                n_sim=DEFAULT_N_SIM,
                top_n=3,
                sg_profile_factor=sg_profile_factor,
            )

            st.markdown("### What Golf Caddy Would Recommend (Training Only)")
            if not ranked_prep:
                st.write("No valid recommendations for this distance.")
            else:
                for i, shot in enumerate(ranked_prep, start=1):
                    st.markdown(
                        f"**{i}. {shot['club']} — {shot['shot_type']}** "
                        f"(Carry ≈ {round(shot['carry'])} yds, "
                        f"Total ≈ {round(shot['total'])} yds, "
                        f"SG ≈ {shot['sg']:.3f})"
                    )
                st.caption(
                    "Use this to compare your 'gut feel' with a consistent, data-driven suggestion. "
                    "In real tournaments, Tournament Mode + your brain replaces this."
                )

    with col_right:
        st.markdown("### Cheat Sheet (Train Your Tournament Brain)")

        st.markdown("**Wind (rule-of-thumb)**")
        st.markdown(
            "- Into 5 mph: **+5%**\n"
            "- Into 10 mph: **+8–10%**\n"
            "- Into 15–20 mph: **+12–15%**\n"
            "- Down 10 mph: **−5%**\n"
            "- Down 15–20 mph: **−7–10%**"
        )

        st.markdown("**Elevation**")
        st.markdown(
            "- Slight Uphill: **+5 yds**\n"
            "- Moderate Uphill: **+10 yds**\n"
            "- Slight Downhill: **−5 yds**\n"
            "- Moderate Downhill: **−10 yds**"
        )

        st.markdown("**Lie**")
        st.markdown(
            "- Good (fairway/tee): no change.\n"
            "- Ok (light rough / small slope): often **+½ club** (~+5 yds mid-irons).\n"
            "- Bad (heavy rough / poor stance): **+1 club** (~+10–15 yds) and expect more flyer/variance."
        )

        st.markdown("**Temperature**")
        st.markdown(
            "- Every **10°F colder** than your normal playing temp: ball flies ~**2–3 yds shorter** "
            "on a mid-iron.\n"
            "- Every **10°F warmer**: ~**+2–3 yds**."
        )

        st.markdown("**Tendencies**")
        st.markdown(
            "- If you usually come up **short**, mentally add **+3–5 yds**.\n"
            "- If you often go **long**, subtract **3–5 yds** or favor the shorter club."
        )

        st.info(
            "Use this tab off-course or in casual rounds to drill your mental math. "
            "The goal is that by the time you’re in a tournament, your brain is doing "
            "all of this automatically without needing the app."
        )

# ------------------------------------------------------------
# HOW IT WORKS TAB
# ------------------------------------------------------------

with tab_info:
    st.subheader("How Golf Caddy Works")

    st.markdown(
        """
        **Golf Caddy** combines a simple ball-flight / dispersion model with a 
        strokes-gained style baseline to help you make smarter decisions.

        **Key ideas:**

        - **Plays-Like Yardage** – your raw yardage adjusted for wind, elevation, lie, temperature, and tendencies.
        - **Shot Recommendations** – each option is evaluated on:
          - Distance match to the plays-like yardage  
          - Trouble short/long/left/right  
          - Your skill / consistency profile  
          - A rough strokes-gained model vs. an amateur baseline.
        - **2D Shot Pattern** – simulated distribution of where shots will actually finish
          relative to the target line and plays-like distance.
        - **Par Strategy** – simple tee-club and layup/attack choices on Par 3s, 4s, and 5s
          using your actual bag numbers.
        - **Tournament Prep Mode** – trains your *mental* plays-like calculations so you
          can make great decisions even when tournament rules limit tech.

        This is intentionally **not** a tour-level physics engine, but it is realistic enough
        to guide better club selection and course management for most amateurs.

        Over time, the goal is that you internalize these patterns so your on-course instincts
        and decision making improve—even when you cannot use the full app (tournaments, etc.).
        """
    )
