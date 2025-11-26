import math
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

from strokes_gained_engine import (
    build_all_candidate_shots,
    recommend_shots_with_sg,
    get_dispersion_sigma,
    adjust_for_wind,
    apply_elevation,
    apply_lie,
    STRATEGY_BALANCED,
    STRATEGY_CONSERVATIVE,
    STRATEGY_AGGRESSIVE,
    DEFAULT_N_SIM,
)

# ------------ ALTair & THEME SETUP ------------ #

alt.data_transformers.disable_max_rows()

# Augusta-aligned dark chart theme
alt.themes.register(
    "golf_augusta_dark",
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
alt.themes.enable("golf_augusta_dark")


# ------------ SMALL HELPERS ------------ #

def bias_for_tendency(target: float, tendency: str) -> float:
    """
    Adjust the plays-like target slightly based on user's typical miss.
    Neutral: no change.
    Usually Short: add a few yards.
    Usually Long: subtract a few yards.
    """
    t = tendency.lower()
    if t == "usually short":
        return target + 4.0
    if t == "usually long":
        return target - 4.0
    return target


def build_dispersion_chart(recommended_shots, target_distance: float):
    """
    Simple 1D dispersion chart showing recommended shots vs plays-like target.
    """
    if not recommended_shots:
        return None

    data = []
    for s in recommended_shots:
        data.append(
            {
                "Club / Shot": f"{s['club']} {s['shot_type']}",
                "Total (yds)": s["total"],
            }
        )

    df = pd.DataFrame(data)

    base = alt.Chart(df).encode(
        y=alt.Y("Club / Shot:N", sort="-x", title="Recommended Options"),
    )

    points = base.mark_point(filled=True, size=80).encode(
        x=alt.X("Total (yds):Q", title="Plays-to Distance (yds)"),
        tooltip=["Club / Shot", "Total (yds)"],
    )

    target_line = (
        alt.Chart(pd.DataFrame({"x": [target_distance]}))
        .mark_rule(strokeDash=[4, 4])
        .encode(x="x:Q")
    )

    return (points + target_line).properties(height=140)


def get_club_category_for_table(club: str) -> str:
    """Map club name to the same high-level category used in dispersion logic."""
    if club in ["PW", "GW", "SW", "LW"]:
        return "scoring_wedge"
    if club in ["9i", "8i"]:
        return "short_iron"
    if club in ["7i", "6i", "5i"]:
        return "mid_iron"
    return "long"


# ------------ MAIN APP ------------ #

def main():
    st.set_page_config(
        page_title="Golf Caddy",
        layout="centered",
    )

    # --- Global CSS Theme Polish (Augusta) ---
    st.markdown(
        """
        <style>
        /* Overall padding */
        section.main > div {
            padding-top: 1.2rem;
        }

        /* Title styling */
        h1 {
            font-size: 2.3rem !important;
            margin-bottom: 0.2rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.02em;
        }

        /* Subheaders spacing */
        h3 {
            margin-top: 1.4rem !important;
            margin-bottom: 0.45rem !important;
            font-weight: 600 !important;
        }

        /* DataFrame font size */
        .stDataFrame tbody, .stDataFrame th {
            font-size: 0.92rem !important;
        }

        /* Buttons: Augusta green with cream text */
        .stButton>button {
            border-radius: 999px;
            padding: 0.4rem 1.3rem;
            border: 1px solid rgba(248, 250, 252, 0.1);
            background: linear-gradient(135deg, #166534, #15803d);
            color: #fefce8;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        .stButton>button:hover {
            border-color: #fbbf24;
            background: linear-gradient(135deg, #15803d, #166534);
            color: #fefce8;
        }

        .stRadio>div>label, .stCheckbox>label {
            font-size: 0.93rem;
        }

        .streamlit-expanderHeader {
            font-weight: 600 !important;
        }

        [data-testid="stExpander"] {
            border-radius: 0.75rem;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Golf Caddy")

    # --- Session defaults ---
    defaults = st.session_state
    defaults.setdefault("driver_speed", 100)
    defaults.setdefault("mode", "Quick")
    defaults.setdefault("tendency", "Neutral")
    defaults.setdefault("skill", "Intermediate")
    defaults.setdefault("tournament_mode", False)
    if "shot_log" not in st.session_state:
        st.session_state.shot_log = []

    # Tournament Mode toggle + banner
    tournament_mode = st.checkbox(
        "Tournament Mode (USGA-legal info only)",
        value=st.session_state.tournament_mode,
        help=(
            "When enabled, Golf Caddy only shows raw yardages and removes plays-like "
            "calculations, club recommendations, and strokes-gained to comply with Rule 4.3."
        ),
    )
    st.session_state.tournament_mode = tournament_mode

    if tournament_mode:
        st.markdown(
            """
            <div style="
                border-radius: 0.75rem;
                padding: 0.6rem 0.9rem;
                margin-top: 0.4rem;
                margin-bottom: 0.3rem;
                background: rgba(34,197,94,0.10);
                border: 1px solid rgba(34,197,94,0.5);
                font-size: 0.9rem;
            ">
                <strong>Tournament Mode is active.</strong>
                Golf Caddy is only displaying raw, unadjusted yardages and non-recommendation
                information consistent with USGA/R&A Rule 4.3. No plays-like distances,
                club suggestions, or strokes-gained are shown.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "Tip: Turn on Tournament Mode if you're playing in a rules-governed event. "
            "It will hide recommendations and only show legal yardage information."
        )

    # Driver speed & bag model
    driver_speed = st.slider(
        "Current Driver Speed (mph)",
        90,
        120,
        defaults["driver_speed"],
        help="Used to scale your entire bag's distances from a 100 mph baseline.",
    )
    st.session_state.driver_speed = driver_speed

    # Build all shots & full bag once
    all_shots_base, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)

    # Tabs
    tab_caddy, tab_range, tab_yardages, tab_info = st.tabs(
        ["Play", "Range", "Yardages", "How it Works"]
    )

    # ---------- CADDY TAB (ON-COURSE) ---------- #
    with tab_caddy:
        if tournament_mode:
            # --- TOURNAMENT-LEGAL VIEW ---
            st.subheader("Tournament Mode (USGA-legal)")

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
                st.markdown("**How to Use This**")
                st.caption(
                    "Use this pin yardage with your raw bag yardages below or in the Yardages tab. "
                    "Golf Caddy does not adjust for wind, slope, or recommend a club in Tournament Mode."
                )

            st.markdown(
                f"""
                <div style="
                    border-radius: 0.8rem;
                    padding: 0.65rem 0.9rem;
                    margin-top: 0.5rem;
                    margin-bottom: 0.3rem;
                    background: radial-gradient(circle at top left, rgba(34,197,94,0.12), rgba(15,23,42,0.9));
                    border: 1px solid rgba(34,197,94,0.45);
                ">
                    <div style="font-size: 0.8rem; text-transform: uppercase; opacity: 0.8; letter-spacing: 0.14em;">
                        Pin Yardage (raw)
                    </div>
                    <div style="font-size: 1.5rem; font-weight: 650; margin-top: 0.1rem;">
                        {target_pin:.1f} yds
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("### Raw Full-Bag Yardages")

            df_full = pd.DataFrame(full_bag)
            df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
            df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
            df_full["Total (yds)"] = df_full["Total (yds)"].round(1)

            dispersion_list = []
            for _, row in df_full.iterrows():
                club = row["Club"]
                category = get_club_category_for_table(club)
                sigma = get_dispersion_sigma(category)
                dispersion_list.append(sigma)

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

            st.info(
                "In Tournament Mode, Golf Caddy acts like a digital yardage book. "
                "No plays-like calculations, strategy suggestions, or club recommendations are used."
            )

        else:
            # --- FULL CADDY MODE (NON-TOURNAMENT) ---
            mode = st.radio(
                "Mode",
                ["Quick", "Advanced"],
                horizontal=True,
                index=0 if st.session_state.mode == "Quick" else 1,
                help=(
                    "Quick mode keeps inputs minimal for fast on-course use. "
                    "Advanced mode lets you tweak every detail (trouble, green layout, pin side, tendencies)."
                ),
            )
            st.session_state.mode = mode

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
                    strategy_label = manual_strategy
                else:
                    use_auto_strategy = True
                    strategy_label = STRATEGY_BALANCED
                    st.markdown("**Strategy**")
                    st.caption("Quick mode uses auto-selected strategy based on distance and situation.")

            # Advanced-only options
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
                        index=["Neutral", "Usually Short", "Usually Long"].index(
                            st.session_state.tendency
                        ),
                        help="If you typically come up short or long, Golf Caddy can bias the target slightly to compensate.",
                    )
                    st.session_state.tendency = tendency

                    skill = st.radio(
                        "Ball Striking Consistency",
                        ["Recreational", "Intermediate", "Highly Consistent"],
                        index=[
                            "Recreational",
                            "Intermediate",
                            "Highly Consistent",
                        ].index(st.session_state.skill),
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
                green_firmness_label = "Medium"
                green_width = 0.0
                pin_lateral_offset = 0.0
                tendency = "Neutral"
                skill = "Intermediate"

            # Skill factor
            skill_norm = skill.lower()
            if skill_norm == "recreational":
                skill_factor = 1.3
            elif skill_norm == "highly consistent":
                skill_factor = 0.8
            else:
                skill_factor = 1.0

            all_shots = all_shots_base  # keep base immutable

            # Normalize for logic
            wind_dir = wind_dir_label.lower()
            wind_strength = wind_strength_label.lower()
            lie = lie_label.lower()

            show_sg_debug = st.checkbox(
                "Show strokes-gained ranking table (debug)",
                value=False,
                help="For testing: shows strokes-gained ranking for the top candidate shots.",
            )

            if st.button("Suggest Shots ✅"):
                with st.spinner("Crunching the numbers..."):
                    # Decide raw target (pin vs center)
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

                    # Wind / elevation / lie adjustments
                    after_wind = adjust_for_wind(raw_target, wind_dir, wind_strength)
                    after_elev = apply_elevation(after_wind, elevation_label)
                    after_lie = apply_lie(after_elev, lie_label)
                    final_target = after_lie

                    # Bias for player tendency
                    final_target_biased = bias_for_tendency(final_target, tendency)

                    # SG uses plays-as distance as starting distance
                    start_distance_yards = final_target_biased
                    start_surface = "fairway"

                    if mode == "Advanced" and use_center and front_yards > 0 and back_yards > front_yards:
                        front_for_sg = front_yards
                        back_for_sg = back_yards
                    else:
                        front_for_sg = 0.0
                        back_for_sg = 0.0

                    # Let engine auto-override strategy if requested
                    # (we still pass current strategy_label; engine may refine based on risk)
                    ranked_candidates = recommend_shots_with_sg(
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
                        top_n=10,
                    )

                    best3 = ranked_candidates[:3]

                    # --- Adjusted Target Card ---
                    st.markdown(
                        f"""
                        <div style="
                            border-radius: 0.9rem;
                            padding: 0.9rem 1.1rem;
                            margin-top: 0.75rem;
                            margin-bottom: 0.35rem;
                            background: radial-gradient(circle at top left, rgba(34,197,94,0.12), rgba(15,23,42,0.9));
                            border: 1px solid rgba(34,197,94,0.45);
                        ">
                            <div style="font-size: 0.8rem; text-transform: uppercase; opacity: 0.8; letter-spacing: 0.14em;">
                                Adjusted Target · plays as
                            </div>
                            <div style="font-size: 1.7rem; font-weight: 650; margin-top: 0.1rem;">
                                {final_target_biased:.1f} yds
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # Situation summary
                    st.markdown("**Situation Summary**")
                    summary_parts = [
                        f"Pin: {target_pin:.0f} yds",
                        f"Wind: {wind_dir_label} / {wind_strength_label}",
                        f"Lie: {lie_label}",
                        f"Elevation: {elevation_label}",
                    ]
                    if mode == "Advanced":
                        summary_parts.append(f"Strategy: {strategy_label}")
                        if using_center:
                            summary_parts.append("Target: center of green")
                    st.write(" · ".join(summary_parts))

                    # Recommendations
                    st.subheader("Shot Recommendations")

                    for i, s in enumerate(best3, start=1):
                        st.markdown(
                            f"**{i}. {s['club']} — {s['shot_type']}** "
                            f"(carry ≈ {s['carry']:.1f} yds, plays to ≈ {s['total']:.1f} yds, "
                            f"SG ≈ {s['sg']:.3f})"
                        )
                        reason = s.get("reason", "")
                        if reason:
                            st.caption(reason)

                    # SG debug table
                    if show_sg_debug:
                        st.subheader("Strokes-Gained Ranking (Debug)")
                        debug_rows = []
                        for s in ranked_candidates:
                            debug_rows.append(
                                {
                                    "Club": s["club"],
                                    "Shot Type": s["shot_type"],
                                    "Category": s.get("category", ""),
                                    "Carry (yds)": round(s["carry"], 1),
                                    "Plays To (yds)": round(s["total"], 1),
                                    "Diff vs Target (yds)": round(s["diff"], 1),
                                    "Legacy Score": round(s["score"], 2),
                                    "Strokes Gained": round(s["sg"], 3),
                                }
                            )
                        df_debug = pd.DataFrame(debug_rows)
                        st.dataframe(df_debug, use_container_width=True)
                        st.caption(
                            "Sorted by strokes gained (descending). "
                            "Primarily for testing and tuning—on-course you can just trust the top recommendations."
                        )

                    st.divider()

                    # Dispersion preview chart
                    st.subheader("Dispersion Preview (Recommended Shots)")
                    chart = build_dispersion_chart(best3, final_target_biased)
                    if chart is not None:
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.caption("No dispersion preview available for this situation.")

                    st.divider()

                    # Shot logging
                    st.subheader("Log Shot (Optional)")

                    shot_labels = [f"{s['club']} {s['shot_type']}" for s in best3]
                    chosen = st.selectbox(
                        "Which option did you actually hit?",
                        ["(I chose something else)"] + shot_labels,
                    )

                    result_distance = st.number_input(
                        "How many yards did it actually travel? (carry or total, your choice)",
                        min_value=0.0,
                        max_value=400.0,
                        value=0.0,
                        step=1.0,
                    )

                    if st.button("Add to Shot Log"):
                        entry = {
                            "Mode": mode,
                            "Timestamp": pd.Timestamp.now().isoformat(timespec="seconds"),
                            "Pin (yds)": target_pin,
                            "Plays As (yds)": final_target_biased,
                            "Wind Dir": wind_dir_label,
                            "Wind Strength": wind_strength_label,
                            "Lie": lie_label,
                            "Elevation": elevation_label,
                            "Strategy": strategy_label,
                            "Chosen Shot": chosen,
                            "Result Distance (yds)": result_distance,
                        }
                        st.session_state.shot_log.append(entry)
                        st.success("Shot logged.")

                    with st.expander("Shot Log (this session)"):
                        if st.session_state.shot_log:
                            df_log = pd.DataFrame(st.session_state.shot_log)
                            st.dataframe(df_log, use_container_width=True)
                            csv = df_log.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "Download log as CSV",
                                data=csv,
                                file_name="golf_caddy_shot_log.csv",
                                mime="text/csv",
                            )
                        else:
                            st.caption("No shots logged yet.")

    # ---------- RANGE TAB (PRACTICE) ---------- #
    with tab_range:
        st.subheader("Range Mode")

        st.markdown(
            "Use Range Mode on the practice tee to calibrate your real distances "
            "against Golf Caddy's modeled yardages."
        )

        df_full = pd.DataFrame(full_bag)
        clubs = df_full["Club"].tolist()
        selected_club = st.selectbox("Select Club to Practice", clubs)

        club_row = df_full[df_full["Club"] == selected_club].iloc[0]
        club_category = get_club_category_for_table(selected_club)
        sigma = get_dispersion_sigma(club_category)

        st.markdown("**Modeled Yardage for This Club (full swing)**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Carry (yds)", f"{club_row['Carry (yds)']:.1f}")
        with c2:
            st.metric("Total (yds)", f"{club_row['Total (yds)']:.1f}")
        with c3:
            st.metric("Dispersion (±yds)", f"{sigma:.1f}")

        st.markdown("---")
        st.markdown("**Log Your Range Shots (optional)**")
        st.caption(
            "Enter the carry distances you observed on the range for this club. "
            "Separate values with commas, e.g. `154, 150, 158, 152`."
        )

        shot_text = st.text_area("Observed carries (yards)", height=80)

        if shot_text.strip():
            # Parse numbers safely
            parts = [p.strip() for p in shot_text.replace("\n", ",").split(",") if p.strip()]
            values = []
            for p in parts:
                try:
                    values.append(float(p))
                except ValueError:
                    pass

            if values:
                arr = np.array(values)
                avg = arr.mean()
                std = arr.std(ddof=1) if len(arr) > 1 else 0.0

                st.markdown("**Your Range Stats**")
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.metric("Shots Logged", len(values))
                with rc2:
                    st.metric("Avg Carry (yds)", f"{avg:.1f}")
                with rc3:
                    st.metric("Std Dev (yds)", f"{std:.1f}")

                # Compare modeled vs actual
                compare_df = pd.DataFrame(
                    {
                        "Type": ["Model", "You"],
                        "Carry (yds)": [club_row["Carry (yds)"], avg],
                    }
                )
                chart = (
                    alt.Chart(compare_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("Type:N", title=""),
                        y=alt.Y("Carry (yds):Q", title="Average Carry (yds)"),
                        tooltip=["Type", "Carry (yds)"],
                    )
                    .properties(height=220)
                )
                st.altair_chart(chart, use_container_width=True)

            else:
                st.caption("No valid numeric values found yet.")
        else:
            st.caption("Log a few shots to see how your real numbers compare to the model.")

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

        dispersion_list = []
        for _, row in df_full.iterrows():
            club = row["Club"]
            category = get_club_category_for_table(club)
            sigma = get_dispersion_sigma(category)
            dispersion_list.append(sigma)

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

    # ---------- INFO TAB ---------- #
    with tab_info:
        st.subheader("Tournament Mode & Rules Compliance")

        st.markdown(
            "Golf Caddy includes an optional **Tournament Mode** designed to comply with "
            "USGA/R&A Rule 4.3 regarding distance-measuring devices."
        )

        st.markdown("### What Tournament Mode Shows")
        st.markdown(
            "- Raw yardage to the pin (as entered by you).\n"
            "- Your full-bag carry and total distances.\n"
            "- Optional dispersion ranges by club (distance spread).\n"
            "- Shot logging tools, if you choose to use them.\n\n"
            "In Tournament Mode, Golf Caddy functions like a digital yardage book. "
            "You must make all club and strategy decisions yourself."
        )

        st.markdown("### What Tournament Mode Hides")
        st.markdown(
            "- Adjusted or 'plays-like' yardages (wind, slope, temperature, etc.).\n"
            "- Automatic club recommendations.\n"
            "- Strategy labels (Conservative, Balanced, Aggressive) based on calculations.\n"
            "- Strokes-gained simulations or rankings between shots.\n"
            "- Any computed advice that would influence decision-making beyond raw information."
        )

        st.markdown(
            "Outside of Tournament Mode, Golf Caddy uses a decision engine that considers "
            "wind, lie, elevation, dispersion, and strokes-gained modeling to recommend shots. "
            "These advanced features are intended for practice, casual rounds, and training "
            "your course management—not for use during formal competition rounds."
        )

        st.divider()

        st.subheader("How Golf Caddy Thinks (High Level)")
        st.markdown(
            "1. **You provide the situation** – pin yardage, wind, lie, elevation, and (optionally) "
            "green shape, trouble, and your tendencies.\n"
            "2. **Golf Caddy converts that into a plays-like distance** – adjusting for wind, "
            "slope, and lie, then nudging for your usual miss pattern.\n"
            "3. **It simulates your shot pattern** – using club-specific dispersion and your "
            "consistency level to estimate where shots will finish on average.\n"
            "4. **It evaluates the outcome in strokes-gained terms** – closer, safer outcomes get "
            "higher SG; penalties or short-siding get punished.\n"
            "5. **It recommends the best options** – usually 2–3 shots that balance scoring "
            "potential and risk, along with a plain-language explanation."
        )

        st.markdown(
            "Over time, using Golf Caddy in Quick mode helps you internalize these patterns. "
            "Tournament Mode then becomes a simple, rules-safe extension of the same decision "
            "process, based on your improved instincts."
        )


if __name__ == "__main__":
    main()
