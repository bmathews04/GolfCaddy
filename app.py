import math
import streamlit as st
import pandas as pd
import numpy as np

import strokes_gained_engine as sge  # <-- your engine module


# ------------------------------------------------------------
# Page config
# ------------------------------------------------------------
st.set_page_config(
    page_title="Golf Caddy",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------
# Session state defaults
# ------------------------------------------------------------

DEFAULTS = {
    "mode": "Quick",              # Quick vs Advanced Caddy mode
    "skill": "Intermediate",      # Ball striking consistency
    "tendency": "Neutral",        # Usually Short / Neutral / Usually Long
    "tournament_mode": False,     # Tournament vs Normal play
    "handicap_factor": 1.0,       # SG / dispersion scaling by handicap
    "driver_speed": 100.0,        # mph, used to scale the bag
}


def init_session_state():
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()


# ------------------------------------------------------------
# Simple helper for club categories in tables
# ------------------------------------------------------------

def _category_for_club(club: str) -> str:
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
# Styling (simple dark-ish theme tweaks)
# ------------------------------------------------------------

st.markdown(
    """
    <style>
    .main {
        background-color: #05070b;
    }
    .stApp {
        background-color: #05070b;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #f5f5f5;
    }
    .stMarkdown, .stText, .stCaption, label {
        color: #e6e6e6 !important;
    }
    div[data-baseweb="input"] input {
        background-color: #11151c !important;
        color: #f5f5f5 !important;
    }
    .stSelectbox, .stNumberInput, .stSlider {
        color: #f5f5f5 !important;
    }
    .stDataFrame {
        background-color: #05070b !important;
    }
    thead tr th {
        background-color: #10151f !important;
    }
    tbody tr {
        background-color: #05070b !important;
    }
    .css-1dp5vir, .e1ewe7hr3 {
        background-color: #05070b !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Sidebar controls
# ------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    st.markdown("**Playing Context**")
    st.session_state.tournament_mode = st.checkbox(
        "Tournament Mode (rules-safe)",
        value=st.session_state.tournament_mode,
        help="When enabled, the main 'Play' tab behaves like a digital yardage book only "
             "— no plays-like yardages or recommendations.",
    )

    st.markdown("---")
    st.markdown("**Handicap / Skill**")
    handicap_label = st.radio(
        "Approximate handicap band",
        ["0–5", "6–12", "13–20", "21+"],
        index=1,  # default 6–12
        help="Used to scale dispersion windows & strokes-gained sensitivity. "
             "Lower handicap = tighter windows.",
    )

    if handicap_label == "0–5":
        st.session_state.handicap_factor = 0.8
    elif handicap_label == "6–12":
        st.session_state.handicap_factor = 1.0
    elif handicap_label == "13–20":
        st.session_state.handicap_factor = 1.2
    else:
        st.session_state.handicap_factor = 1.35

    st.markdown(
        "Smaller factor = tighter windows and more aggressive SG assumptions.\n\n"
        "Larger factor = wider windows and more conservative expectations."
    )

    st.markdown("---")
    st.markdown("**About Tournament Mode**")
    st.caption(
        "In official events that limit electronic advice, you should only use "
        "the Tournament Mode tab and mental calculations (no direct recommendations)."
    )


# ------------------------------------------------------------
# Main title & driver speed
# ------------------------------------------------------------

st.title("Golf Caddy")
st.caption(
    "Enter your conditions and let Golf Caddy suggest shots and strategies based on "
    "distance, dispersion, and strokes-gained style logic."
)

driver_speed = st.slider(
    "Current Driver Speed (mph)",
    min_value=90.0,
    max_value=120.0,
    value=float(st.session_state.driver_speed),
    step=1.0,
    help="Used to scale your entire bag's distances from a 100 mph baseline.",
)
st.session_state.driver_speed = float(driver_speed)

# Build bag & candidates from engine
all_shots_base, scoring_shots, full_bag = sge.build_all_candidate_shots(driver_speed)

# ------------------------------------------------------------
# Tabs
# ------------------------------------------------------------

tab_play, tab_range, tab_yardages, tab_strategy, tab_prep, tab_info = st.tabs(
    ["Play", "Range", "Yardages", "Par Strategy", "Tournament Prep", "Info"]
)

# ============================================================
# PLAY TAB (Caddy + Tournament Mode)
# ============================================================

with tab_play:

    if st.session_state.tournament_mode:
        # ----------------------------------------------------
        # Tournament-safe digital yardage book
        # ----------------------------------------------------
        st.subheader("Tournament Mode: Digital Yardage Book")

        pin_yardage = st.number_input(
            "Pin Yardage (yards)",
            min_value=10.0,
            max_value=350.0,
            value=150.0,
            step=1.0,
            help="Measured distance from your rangefinder or GPS.",
        )

        st.info(
            "In Tournament Mode, Golf Caddy only shows static yardage tables. "
            "No plays-like calculations, strategies, or club recommendations are performed. "
            "Use your own mental adjustments for wind, lie, elevation, and trouble."
        )

        st.markdown("### Full-Bag Yardages (Scaled to Your Driver Speed)")
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(0)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(0)

        dispersion_list = []
        for _, row in df_full.iterrows():
            club = row["Club"]
            category = _category_for_club(club)
            sigma = sge.get_dispersion_sigma(category)
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

        st.markdown("### Scoring Wedge / Partial Shot Yardages")
        df_score = pd.DataFrame(scoring_shots)
        df_score = df_score[["carry", "club", "shot_type", "trajectory"]]
        df_score.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
        df_score["Carry (yds)"] = df_score["Carry (yds)"].round(0)
        df_score = df_score.sort_values("Carry (yds)", ascending=False).reset_index(
            drop=True
        )
        st.dataframe(df_score, use_container_width=True)

    else:
        # ----------------------------------------------------
        # Normal Caddy Mode (Quick vs Advanced)
        # ----------------------------------------------------
        st.subheader("On-Course Caddy Mode")

        mode = st.radio(
            "Mode",
            ["Quick", "Advanced"],
            index=0 if st.session_state.mode == "Quick" else 1,
            horizontal=True,
            help="Quick keeps inputs minimal; Advanced lets you describe trouble, "
                 "pin position, and tendencies in detail.",
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
                st.markdown("**Strategy & Player Profile**")
                use_auto_strategy = st.checkbox(
                    "Auto-select strategy based on situation",
                    value=True,
                )
                manual_strategy = st.radio(
                    "Strategy (if not auto)",
                    [sge.STRATEGY_BALANCED, sge.STRATEGY_CONSERVATIVE, sge.STRATEGY_AGGRESSIVE],
                    index=0,
                    help="Conservative favors safety, Aggressive chases pins, Balanced is in between.",
                )
                strategy_label = manual_strategy
            else:
                use_auto_strategy = True
                strategy_label = sge.STRATEGY_BALANCED
                st.markdown("**Strategy**")
                st.caption(
                    "Quick mode uses a balanced strategy with moderate risk/reward."
                )

        # Advanced-only extras
        if mode == "Advanced":
            with st.expander("Advanced: Trouble, Green, Tendencies (Optional)"):
                st.markdown("**Trouble Short / Long & Green Firmness**")
                tcol1, tcol2, tcol3 = st.columns(3)
                with tcol1:
                    trouble_short_label = st.selectbox(
                        "Trouble Short?",
                        ["None", "Mild", "Severe"],
                    )
                with tcol2:
                    trouble_long_label = st.selectbox(
                        "Trouble Long?",
                        ["None", "Mild", "Severe"],
                    )
                with tcol3:
                    green_firmness_label = st.selectbox(
                        "Green Firmness",
                        ["Soft", "Medium", "Firm"],
                    )

                st.markdown("---")
                st.markdown("**Player Tendencies**")
                tendency = st.radio(
                    "Usual Miss (Distance)",
                    ["Neutral", "Usually Short", "Usually Long"],
                    horizontal=True,
                    index=["Neutral", "Usually Short", "Usually Long"].index(
                        st.session_state.tendency
                    ),
                    help="If you typically come up short or long, the target can be biased slightly.",
                )
                st.session_state.tendency = tendency

                skill = st.radio(
                    "Ball Striking Consistency",
                    ["Recreational", "Intermediate", "Highly Consistent"],
                    index=["Recreational", "Intermediate", "Highly Consistent"].index(
                        st.session_state.skill
                    ),
                    help="Used to scale dispersion windows and strokes-gained simulations.",
                )
                st.session_state.skill = skill

        else:
            # Quick defaults
            trouble_short_label = "None"
            trouble_long_label = "None"
            green_firmness_label = "Medium"
            tendency = "Neutral"
            skill = "Intermediate"

        # Skill factor (used for SG and dispersion scaling)
        skill_norm = skill.lower()
        if skill_norm == "recreational":
            skill_factor = 1.3
        elif skill_norm == "highly consistent":
            skill_factor = 0.8
        else:
            skill_factor = 1.0

        # Combine with handicap factor
        sg_profile_factor = st.session_state.handicap_factor
        skill_factor *= st.session_state.handicap_factor

        # Normalize for logic
        wind_dir = wind_dir_label.lower()
        wind_strength = wind_strength_label.lower()
        lie = lie_label.lower()

        if st.button("Suggest Shots ✅"):
            with st.spinner("Crunching the numbers..."):

                # Plays-like yardage using shared engine helpers
                target_after_wind = sge.adjust_for_wind(
                    target_pin, wind_dir, wind_strength
                )
                target_after_elev = sge.apply_elevation(
                    target_after_wind, elevation_label
                )
                target_final = sge.apply_lie(target_after_elev, lie)

                # Tendency bias
                if tendency == "Usually Short":
                    target_final += 3.0
                elif tendency == "Usually Long":
                    target_final -= 3.0

                st.markdown(
                    f"### Adjusted Target (plays as): **{target_final:.1f} yds**"
                )

                if use_auto_strategy:
                    # crude auto-strategy: longer shots & heavy trouble → conservative
                    if target_final > 190 or trouble_long_label == "Severe":
                        strategy_label = sge.STRATEGY_CONSERVATIVE
                    elif target_final < 130 and trouble_short_label == "None":
                        strategy_label = sge.STRATEGY_AGGRESSIVE
                    else:
                        strategy_label = sge.STRATEGY_BALANCED

                st.caption(f"Using Strategy: **{strategy_label}**")

                ranked = sge.recommend_shots_with_sg(
                    target_total=target_final,
                    candidates=all_shots_base,
                    short_trouble_label=trouble_short_label,
                    long_trouble_label=trouble_long_label,
                    left_trouble_label="None",
                    right_trouble_label="None",
                    green_firmness_label=green_firmness_label,
                    strategy_label=strategy_label,
                    start_distance_yards=target_pin,
                    start_surface="fairway",
                    front_yards=0.0,
                    back_yards=0.0,
                    skill_factor=skill_factor,
                    pin_lateral_offset=0.0,
                    green_width=0.0,
                    n_sim=sge.DEFAULT_N_SIM,
                    top_n=5,
                    sg_profile_factor=sg_profile_factor,
                )

                if not ranked:
                    st.warning(
                        "No reasonable candidate shots found near this plays-like yardage."
                    )
                else:
                    st.subheader("Recommended Options")
                    for i, s in enumerate(ranked, start=1):
                        st.markdown(
                            f"**{i}. {s['club']} — {s['shot_type']}**  "
                            f"(Carry ≈ {s['carry']:.1f} yds, Total ≈ {s['total']:.1f} yds, "
                            f"SG ≈ {s['sg']:.3f})"
                        )
                        st.caption(s["reason"])

# ============================================================
# RANGE TAB
# ============================================================

with tab_range:
    st.subheader("Range Mode: Stock Yardages by Club")

    club_options = [row["Club"] for row in full_bag]
    selected_club = st.selectbox("Select club", club_options)

    use_scoring = st.checkbox(
        "Show wedge scoring/partial shots for this club (if available)",
        value=True,
    )

    df = pd.DataFrame(full_bag)
    df["Carry (yds)"] = df["Carry (yds)"].round(0)
    df["Total (yds)"] = df["Total (yds)"].round(0)

    st.markdown("### Full-Swing Distances")
    st.dataframe(
        df[df["Club"] == selected_club].reset_index(drop=True),
        use_container_width=True,
    )

    if use_scoring:
        df_s = pd.DataFrame(scoring_shots)
        df_s = df_s[df_s["club"] == selected_club]
        if not df_s.empty:
            df_s = df_s[["carry", "club", "shot_type", "trajectory"]]
            df_s.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
            df_s["Carry (yds)"] = df_s["Carry (yds)"].round(0)
            df_s = df_s.sort_values("Carry (yds)", ascending=False).reset_index(
                drop=True
            )
            st.markdown("### Scoring / Partial Shots")
            st.dataframe(df_s, use_container_width=True)
        else:
            st.info("No scoring/partial shots defined for this club.")


# ============================================================
# YARDAGES TAB
# ============================================================

with tab_yardages:
    st.subheader("Full Bag Yardages")

    df_full = pd.DataFrame(full_bag)
    df_full["Carry (yds)"] = df_full["Carry (yds)"].round(0)
    df_full["Total (yds)"] = df_full["Total (yds)"].round(0)
    df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)

    dispersion_list = []
    for _, row in df_full.iterrows():
        cat = _category_for_club(row["Club"])
        dispersion_list.append(sge.get_dispersion_sigma(cat))

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

    st.markdown("### Scoring / Partial Shot Yardages")
    df_score = pd.DataFrame(scoring_shots)
    df_score = df_score[["carry", "club", "shot_type", "trajectory"]]
    df_score.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
    df_score["Carry (yds)"] = df_score["Carry (yds)"].round(0)
    df_score = df_score.sort_values("Carry (yds)", ascending=False).reset_index(
        drop=True
    )
    st.dataframe(df_score, use_container_width=True)


# ============================================================
# PAR STRATEGY TAB (Hole Strategy)
# ============================================================

with tab_strategy:
    st.subheader("Hole Strategy (Par 3 / 4 / 5)")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        par_type = st.selectbox("Hole type", ["Par 3", "Par 4", "Par 5"])
        hole_yards = st.number_input(
            "Hole yardage (tee to green center)",
            min_value=60.0,
            max_value=650.0,
            value=420.0 if par_type == "Par 4" else (180.0 if par_type == "Par 3" else 520.0),
            step=1.0,
        )
    with col_s2:
        fairway_width_label = st.selectbox(
            "Fairway width (for tee shot)",
            ["Narrow", "Medium", "Wide"],
            index=1,
        )
        tee_left_trouble = st.selectbox("Trouble left off tee?", ["None", "Mild", "Severe"])
        tee_right_trouble = st.selectbox("Trouble right off tee?", ["None", "Mild", "Severe"])

    skill_factor = 1.0 * st.session_state.handicap_factor

    if st.button("Run Hole Strategy"):
        if par_type == "Par 3":
            res = sge.par3_strategy(
                hole_yards=hole_yards,
                candidates=all_shots_base,
                skill_factor=skill_factor,
                green_width=0.0,
                short_trouble_label="None",
                long_trouble_label="None",
                left_trouble_label="None",
                right_trouble_label="None",
                strategy_label=sge.STRATEGY_BALANCED,
                sg_profile_factor=st.session_state.handicap_factor,
            )
            best = res.get("best")
            if best is None:
                st.warning("No suitable Par 3 strategy found.")
            else:
                st.markdown(
                    f"**Recommended tee shot:** {best['club']} — {best['shot_type']}  "
                    f"(Total ≈ {best['total']:.0f} yds, SG vs baseline ≈ {best['sg']:.3f})"
                )
                st.caption(
                    f"Approx. probability on/near green: within 10 yds ≈ {best['p_within_10']*100:.0f}%, "
                    f"within 5 yds ≈ {best['p_within_5']*100:.0f}%."
                )

        elif par_type == "Par 4":
            res = sge.par4_strategy(
                hole_yards=hole_yards,
                full_bag=full_bag,
                skill_factor=skill_factor,
                fairway_width_label=fairway_width_label,
                tee_left_trouble_label=tee_left_trouble,
                tee_right_trouble_label=tee_right_trouble,
                sg_profile_factor=st.session_state.handicap_factor,
            )
            best = res.get("best")
            if best is None:
                st.warning("No suitable Par 4 strategy found.")
            else:
                st.markdown(
                    f"**Tee club:** {best['tee_club']} "
                    f"(Avg total ≈ {best['avg_total']:.0f} yds, "
                    f"remaining ≈ {best['remaining_yards']:.0f} yds)"
                )
                st.caption(
                    f"Expected score ≈ {best['expected_score']:.2f} "
                    f"(SG vs baseline ≈ {best['sg_vs_baseline']:.3f})."
                )

        else:  # Par 5
            res = sge.par5_strategy(
                hole_yards=hole_yards,
                full_bag=full_bag,
                skill_factor=skill_factor,
                fairway_width_label=fairway_width_label,
                tee_left_trouble_label=tee_left_trouble,
                tee_right_trouble_label=tee_right_trouble,
                sg_profile_factor=st.session_state.handicap_factor,
            )
            best_tee = res.get("best_tee")
            if best_tee is None:
                st.warning("No suitable Par 5 strategy found.")
            else:
                st.markdown(
                    f"**Tee club:** {best_tee['tee_club']} "
                    f"(Avg total ≈ {best_tee['avg_total']:.0f} yds, "
                    f"remaining ≈ {res['remaining_after_tee']:.0f} yds)"
                )
                st.markdown(f"**Plan:** {res['strategy']}")

                st.caption(f"""
                Expected score ≈ {res['expected_score']:.2f}  
                (Layup plan ≈ {res['layup_score']:.2f}, 
                Go-for-it plan ≈ {res['go_for_it_score']:.2f} if available).
                """)



# ============================================================
# TOURNAMENT PREP TAB
# ============================================================

with tab_prep:
    st.header("Tournament Prep: Mental Adjustments Practice")

    # --- Buttons / scenario control ---
    col_gen, col_info = st.columns([2, 3])
    with col_gen:
        if st.button("Generate Random Scenario 🎯"):
            st.session_state.prep_scenario = sge.generate_random_scenario()
            st.session_state.prep_revealed = False

    with col_info:
        st.caption(
            "Use this to **train your brain** to do legal on-course adjustments "
            "(wind, lie, elevation, temperature) **without** depending on the app during play."
        )

    scenario = st.session_state.get("prep_scenario", None)

    # If no scenario yet, create one on first load
    if scenario is None:
        scenario = sge.generate_random_scenario()
        st.session_state.prep_scenario = scenario
        st.session_state.prep_revealed = False

    st.markdown("**Raw scenario:**")
    st.json(scenario)

    # --- Engine plays-like (hidden until reveal) ---
    # You can choose to include your personal tendency here; for now we keep it Neutral
    engine_plays_like = sge.calculate_plays_like_yardage(
        raw_yards=scenario["raw_yards"],
        wind_dir=scenario["wind_dir"],
        wind_strength_label=scenario["wind_strength"],
        elevation_label=scenario["elevation"],
        lie_label=scenario["lie"],
        tendency_label="Neutral",      # or st.session_state.tendency if you prefer
        temp_f=scenario["temp_f"],
        baseline_temp_f=75.0,
    )

    # --- User guess input ---
    st.markdown("### Your Mental Adjustment")

    guess = st.number_input(
        "What yardage do you think this plays as? (yards)",
        min_value=50.0,
        max_value=260.0,
        step=1.0,
        key="prep_guess",
        help=(
            "Look only at the raw scenario above and apply your own mental rules of thumb "
            "for wind, lie, elevation, and temperature. Then enter your best estimate here."
        ),
    )

    reveal = st.button("Reveal Answer ✅")

    if reveal:
        st.session_state.prep_revealed = True

    if st.session_state.get("prep_revealed", False):
        # Use last guess from session_state to keep it stable across reruns
        user_guess = float(st.session_state.get("prep_guess", guess or 0.0))
        diff = user_guess - engine_plays_like
        diff_abs = abs(diff)

        if diff_abs < 0.5:
            qualitative = "Spot on. That’s tour-level adjustment."
        elif diff_abs <= 2:
            qualitative = "Excellent. Within 2 yards of the engine."
        elif diff_abs <= 5:
            qualitative = "Solid. Within 5 yards—very playable on course."
        else:
            qualitative = "Big gap. Try walking through each factor more deliberately."

        direction = "longer than" if diff > 0 else "shorter than" if diff < 0 else "exactly equal to"

        st.markdown("### Results")

        col_l, col_r = st.columns(2)
        with col_l:
            st.metric("Your plays-like estimate", f"{user_guess:.1f} yds")
        with col_r:
            st.metric("Engine plays-like (for practice)", f"{engine_plays_like:.1f} yds")

        st.markdown(
            f"- Difference: **{diff_abs:.1f} yds** ({'you played it ' if diff != 0 else ''}"
            f"{direction} the engine).\n\n"
            f"- {qualitative}"
        )

        st.info(
            "Use this only when **practicing**. In real tournament play, you’d make these "
            "adjustments in your head using your own rules of thumb (and keep the app in "
            "Tournament Mode / yardage-book only)."
        )

    st.markdown("---")
    st.markdown("#### Suggested Mental Rules of Thumb (Practice Only)")
    st.markdown(
        "- Into wind: add ~1 yard per mph of wind for a 150-yard shot (scale a bit for longer/shorter).  \n"
        "- Downwind: subtract ~0.5 yard per mph of wind.  \n"
        "- Slight uphill: add ~5 yards.  \n"
        "- Moderate uphill: add ~10 yards.  \n"
        "- Slight downhill: subtract ~5 yards.  \n"
        "- Moderate downhill: subtract ~10 yards.  \n"
        "- Cold (10°F below 75°F): lose ~2–3 yards at 150y; hot (10°F above) gain ~2–3 yards.  \n"
        "- Bad lie (thick rough / buried): expect it to come out shorter; good lie: normal."
    )



# ============================================================
# INFO TAB
# ============================================================

with tab_info:
    st.subheader("How Golf Caddy Works")

    st.markdown(
        """
        **Golf Caddy** combines a simple distance model, dispersion windows, and a
        strokes-gained style engine to help you choose smarter shots on the course.

        ### Modes

        - **Play / Caddy Mode**
          - Quick: minimal inputs for on-course speed.
          - Advanced: describe trouble, tendencies, and strategy to get richer recommendations.

        - **Tournament Mode**
          - Turns the Play tab into a digital yardage book only.
          - No plays-like calculations or recommendations are displayed.

        - **Range Mode**
          - Explore your scaled bag distances and scoring shots by club.

        - **Yardages**
          - Full-bag and scoring-shot tables, including a rough dispersion estimate.

        - **Par Strategy**
          - High-level guidance for Par 3, 4, and 5 holes using tee-club choices,
            three-shot vs two-shot plans, and expected score comparisons.

        - **Tournament Prep**
          - Random practice scenarios for training your own 'mental caddy' to make
            plays-like adjustments without violating tournament rules.

        ### Disclaimer

        All models are approximate and based on simplified physics and amateur
        strokes-gained curves. Always use your judgment, local rules, and competition
        conditions when making decisions on the golf course.
        """
    )
