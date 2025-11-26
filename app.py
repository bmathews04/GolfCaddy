import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

from strokes_gained_engine import (
    build_all_candidate_shots,
    adjust_for_wind,
    apply_elevation,
    apply_lie,
    recommend_shots_with_sg,
    compute_optimal_carry_for_target,
    get_dispersion_sigma,
    get_lateral_sigma,
    STRATEGY_BALANCED,
    STRATEGY_CONSERVATIVE,
    STRATEGY_AGGRESSIVE,
    DEFAULT_N_SIM,
    par3_strategy,
    par4_strategy,
    par5_strategy,
)


# ============================================================
# PAGE CONFIG & DEFAULTS
# ============================================================

st.set_page_config(
    page_title="Golf Caddy",
    layout="wide",
)

DEFAULTS = {
    "driver_speed": 100,
    "mode": "Quick",
    "tendency": "Neutral",
    "skill": "Intermediate",
}


def init_session_state():
    for key, val in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()


# Local helper to categorize clubs for dispersion table
def _category_for_club(club: str) -> str:
    if club in ["PW", "GW", "SW", "LW"]:
        return "scoring_wedge"
    if club in ["9i", "8i"]:
        return "short_iron"
    if club in ["7i", "6i", "5i"]:
        return "mid_iron"
    return "long"


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:
    st.header("Player Profile & Modes")

    # Handicap / scoring baseline -> SG profile factor
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
        help=(
            "When enabled, the Play tab only shows raw yardages (no plays-like or "
            "decision recommendations)."
        ),
    )

    st.markdown("---")
    st.markdown("**About Golf Caddy**")
    st.caption(
        "This is a decision engine, not a rules engine. In non-tournament play, "
        "use all features. In competition, use Tournament Mode to respect rules "
        "around distance-measuring devices and advice."
    )


# ============================================================
# MAIN HEADER & SHARED DATA
# ============================================================

st.title("Golf Caddy")

# Driver speed and precomputed data (shared across tabs)
driver_speed = st.slider(
    "Current Driver Speed (mph)",
    90,
    120,
    st.session_state.driver_speed,
    help="Used to scale your entire bag's distances from a 100 mph baseline.",
)
st.session_state.driver_speed = driver_speed

all_shots_base, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)

# Tabs: Play (caddy), Yardages, Strategy, Info
tab_caddy, tab_yardages, tab_strategy, tab_info = st.tabs(
    ["Play", "Yardages", "Par Strategy", "How it Works"]
)

# ============================================================
# PLAY TAB (CADDY MODE + TOURNAMENT MODE)
# ============================================================

with tab_caddy:
    if tournament_mode:
        # ---------------- TOURNAMENT MODE ---------------- #
        st.subheader("Tournament Mode: Raw Yardages Only")

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
                "Use this screen as a digital yardage book during play. "
                "No plays-like recommendations or calculations are shown."
            )

        # Raw full-bag yardages
        st.markdown("### Raw Full-Bag Yardages")

        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(0).astype(int)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(0).astype(int)

        # Dispersion column
        dispersion_list = []
        for _, row in df_full.iterrows():
            club = row["Club"]
            cat = _category_for_club(club)
            sigma = get_dispersion_sigma(cat)
            dispersion_list.append(sigma)

        df_full["Dispersion (±yds)"] = [round(x) for x in dispersion_list]
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
        # ---------------- ON-COURSE CADDY MODE ---------------- #
        st.subheader("On-Course Caddy Mode")

        # Mode selector (Quick vs Advanced)
        mode = st.radio(
            "Mode",
            ["Quick", "Advanced"],
            horizontal=True,
            index=0 if st.session_state.mode == "Quick" else 1,
            help=(
                "Quick mode keeps inputs minimal for fast on-course use. "
                "Advanced mode lets you tweak everything (green layout, trouble, tendencies)."
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
                use_auto_strategy = True
                strategy_label = STRATEGY_BALANCED
                st.markdown("**Strategy**")
                st.caption("Quick mode uses auto-selected strategy based on distance and situation.")

        # Advanced options
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
                st.markdown("**Trouble & Green Firmness (Around the Green)**")
                tcol1, tcol2, tcol3, tcol4 = st.columns(4)
                with tcol1:
                    trouble_short_label = st.selectbox(
                        "Trouble Short?",
                        ["None", "Mild", "Severe"],
                        help="How penal is a miss that finishes short of the green?",
                    )
                with tcol2:
                    trouble_long_label = st.selectbox(
                        "Trouble Long?",
                        ["None", "Mild", "Severe"],
                        help="How penal is a miss that finishes long of the green?",
                    )
                with tcol3:
                    trouble_left_label = st.selectbox(
                        "Trouble Left?",
                        ["None", "Mild", "Severe"],
                        help="Lateral hazards or bad rough left of the green.",
                    )
                with tcol4:
                    trouble_right_label = st.selectbox(
                        "Trouble Right?",
                        ["None", "Mild", "Severe"],
                        help="Lateral hazards or bad rough right of the green.",
                    )

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
                    index=["Neutral", "Usually Short", "Usually Long"].index(st.session_state.tendency),
                    help="If you typically come up short or long, Golf Caddy can bias the target slightly to compensate.",
                )
                st.session_state.tendency = tendency

                skill = st.radio(
                    "Ball Striking Consistency",
                    ["Recreational", "Intermediate", "Highly Consistent"],
                    index=["Recreational", "Intermediate", "Highly Consistent"].index(st.session_state.skill),
                    help="Used to scale dispersion windows and strokes-gained simulations.",
                )
                st.session_state.skill = skill

        else:
            # Quick mode defaults
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
            tendency = "Neutral"
            skill = st.session_state.skill

        # Skill factor
        skill_norm = skill.lower()
        if skill_norm == "recreational":
            skill_factor = 1.3
        elif skill_norm == "highly consistent":
            skill_factor = 0.8
        else:
            skill_factor = 1.0

        # Normalize for logic
        wind_dir = wind_dir_label.lower()
        wind_strength = wind_strength_label.lower()
        lie = lie_label.lower()

        # Apply tendency as a small adjustment to target
        tendency_adj = 0.0
        if tendency == "Usually Short":
            tendency_adj = 3.0
        elif tendency == "Usually Long":
            tendency_adj = -3.0

        if st.button("Suggest Shots ✅"):
            with st.spinner("Crunching the numbers..."):
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

                after_wind = adjust_for_wind(raw_target, wind_dir, wind_strength)
                after_elev = apply_elevation(after_wind, elevation_label)
                final_target = apply_lie(after_elev, lie) + tendency_adj
                plays_like = final_target

                st.markdown(
                    f"### Plays-Like Yardage: **{round(plays_like)} yds** "
                    f"({'center of green' if using_center else 'to pin'})"
                )

                # Auto-strategy tweak (very simple for now)
                if use_auto_strategy:
                    dist = plays_like
                    if any(lbl == "Severe" for lbl in [trouble_short_label, trouble_long_label,
                                                       trouble_left_label, trouble_right_label]):
                        strategy_label = STRATEGY_CONSERVATIVE
                    elif dist < 120 and all(lbl == "None" for lbl in [trouble_short_label,
                                                                      trouble_long_label,
                                                                      trouble_left_label,
                                                                      trouble_right_label]):
                        strategy_label = STRATEGY_AGGRESSIVE
                    else:
                        strategy_label = STRATEGY_BALANCED

                start_surface = "fairway"

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
                    start_surface=start_surface,
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

                    # ---- Shot Pattern Preview (Top Recommendation) ---- #
                    if ranked:
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
                            {
                                "Depth (yds)": depth_errors,
                                "Lateral (yds)": lat_errors,
                            }
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
                                    title="Short (-) / Long (+) relative to plays-like yardage",
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

                        shot_pattern_chart = alt.layer(*charts).properties(
                            width="container",
                            height=320,
                            title=f"{top['club']} — {top['shot_type']} (simulated pattern)",
                        )

                        with st.expander("Show 2D shot dispersion (simulation)"):
                            st.altair_chart(shot_pattern_chart, use_container_width=True)

                            # Text summary
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
                                    f"- ~{pct_on_green:.0f}% of shots fall inside the **green area** "
                                    f"(±5 yds depth, ±{half_w:.1f} yds lateral)."
                                )

                            if abs(avg_depth) >= 0.5:
                                depth_dir = "long" if avg_depth > 0 else "short"
                                summary_lines.append(
                                    f"- Average depth bias: **{abs(avg_depth):.1f} yds {depth_dir}** "
                                    f"of the plays-like yardage."
                                )
                            else:
                                summary_lines.append(
                                    "- Average depth bias: essentially **pin high** on average."
                                )

                            if abs(avg_lat) >= 0.5:
                                lat_dir = "right" if avg_lat > 0 else "left"
                                summary_lines.append(
                                    f"- Average lateral bias: **{abs(avg_lat):.1f} yds {lat_dir}** "
                                    f"of the target line."
                                )
                            else:
                                summary_lines.append(
                                    "- Average lateral bias: essentially **straight at the target line**."
                                )

                            st.markdown("#### Pattern Summary")
                            st.markdown("\n".join(summary_lines))


# ============================================================
# YARDAGES TAB
# ============================================================

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
            club = row["Club"]
            cat = _category_for_club(club)
            sigma = get_dispersion_sigma(cat)
            dispersion_list.append(sigma)

        df_full["Dispersion (±yds)"] = [round(x) for x in dispersion_list]
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


# ============================================================
# PAR STRATEGY TAB
# ============================================================

with tab_strategy:
    st.subheader("Tee-to-Green Par Strategy")

    # Hole setup
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
            help="Used to estimate how often your tee shot misses the fairway.",
        )
    with col_s2:
        green_width_strategy = st.slider(
            "Green Width (yards, left-to-right)",
            min_value=0.0,
            max_value=50.0,
            value=25.0,
            step=1.0,
            help="Optional. Used for hit-green probability and dispersion modeling.",
        )
    with col_s3:
        st.caption(
            "Narrow fairways with severe left/right trouble usually reward "
            "a more conservative tee club."
        )

    st.markdown("**Trouble Severity Around the Hole**")
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        trouble_short_label_s = st.selectbox(
            "Trouble Short",
            ["None", "Mild", "Severe"],
            help="Penalties (bunkers, water, deep rough) if you come up short.",
        )
    with col_t2:
        trouble_long_label_s = st.selectbox(
            "Trouble Long",
            ["None", "Mild", "Severe"],
            help="Penalties if you go long past the green or fairway.",
        )
    with col_t3:
        trouble_left_label_s = st.selectbox(
            "Trouble Left",
            ["None", "Mild", "Severe"],
            help="OB, penalty areas, or bad rough to the left.",
        )
    with col_t4:
        trouble_right_label_s = st.selectbox(
            "Trouble Right",
            ["None", "Mild", "Severe"],
            help="OB, penalty areas, or bad rough to the right.",
        )

    # Skill factor: reuse skill from session
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
                    f"- Expected strokes from tee: **{best['expected_strokes']:.2f}** "
                    f"(vs. baseline for this length)."
                )
                st.markdown(
                    f"- Hit-green probability (approx): "
                    f"**{best['p_on_green']*100:.0f}%** "
                    f"(inside ±5 yds depth and within green width)."
                )
                st.markdown(
                    f"- ~{best['p_within_5']*100:.0f}% of shots finish within 5 yds; "
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
                    f"- Strokes gained vs generic baseline from this length: "
                    f"**{best4['sg_vs_baseline']:.2f}**"
                )
                st.markdown(
                    f"- Estimated fairway miss probability: "
                    f"**{best4['miss_prob']*100:.0f}%**"
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

        else:  # Par 5
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
                        f"- Layup plan (3-shot route): Target layup to "
                        f"**{round(res5['layup_target'])} yds**, "
                        f"expected score ≈ **{res5['layup_score']:.2f}**."
                    )
                if res5["go_for_it_score"] is not None:
                    st.markdown(
                        f"- Go-for-it plan (2-shot route): expected score ≈ "
                        f"**{res5['go_for_it_score']:.2f}**."
                    )

                st.markdown("#### Summary")
                st.caption(
                    "Use this screen for pre-round prep: decide which Par 5s you should "
                    "attack in two versus play as true three-shot holes."
                )


# ============================================================
# HOW IT WORKS TAB
# ============================================================

with tab_info:
    st.subheader("How Golf Caddy Works")

    st.markdown(
        """
        **Golf Caddy** uses a simple ball-flight and dispersion model combined with 
        strokes-gained style expectations to help you:

        - Turn raw yardages into **plays-like** yardages (wind, elevation, lie, tendency).
        - Compare different clubs and shot types using **simulated outcomes**.
        - Respect **trouble short/long/left/right** when ranking shots.
        - Provide **Par 3, Par 4, and Par 5 strategy** based on your bag and skill level.

        ### Interpreting the Recommendations

        - **Plays-Like Yardage**: The distance the shot effectively plays after all adjustments.
        - **SG (Strokes Gained)**: How much better or worse a choice is compared with a 
          typical shot from that distance.
        - **2D Shot Pattern**: Shows where your misses are likely to cluster around the target line.

        ### Modes

        - **Play (Caddy Mode)**: On-course assistant that suggests clubs and shots.
        - **Yardages**: Reference tables for your bag and wedge partials.
        - **Par Strategy**: Pre-round hole planning for Par 3s, 4s, and 5s.
        - **Tournament Mode**: Turns the Play tab into a raw yardage book for rules-sensitive play.

        This is not a perfect physics simulator or tour-grade SG model, 
        but it is designed to be realistic enough to guide better decisions 
        for most amateur golfers while keeping the interface simple and fast to use.
        """
    )
