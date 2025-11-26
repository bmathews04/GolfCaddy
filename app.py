import math
from typing import List, Dict

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

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
    compute_optimal_carry_for_target,
)

# ============================================================
# PAGE CONFIG & THEME
# ============================================================

st.set_page_config(
    page_title="Golf Caddy",
    page_icon="⛳",
    layout="wide",
)

# ============================================================
# SESSION STATE DEFAULTS
# ============================================================

if "driver_speed" not in st.session_state:
    st.session_state.driver_speed = 100

if "mode" not in st.session_state:
    st.session_state.mode = "Quick"

if "tournament_mode" not in st.session_state:
    st.session_state.tournament_mode = False

if "tendency" not in st.session_state:
    st.session_state.tendency = "Neutral"

if "skill" not in st.session_state:
    st.session_state.skill = "Intermediate"

if "range_actual_carries" not in st.session_state:
    # store user-input range averages by club
    st.session_state.range_actual_carries = {}

# ============================================================
# HELPERS
# ============================================================

def get_club_category_for_table(club: str) -> str:
    """Public mapping of club → category (sync with engine)."""
    if club in ["PW", "GW", "SW", "LW"]:
        return "Scoring wedge"
    if club in ["9i", "8i"]:
        return "Short iron"
    if club in ["7i", "6i", "5i"]:
        return "Mid iron"
    return "Long / wood / driver"


def skill_to_factor(skill: str) -> float:
    s = (skill or "Intermediate").lower()
    if s == "recreational":
        return 1.3
    if s == "highly consistent":
        return 0.8
    return 1.0

def ui_surface_to_engine_lie(surface_label: str) -> str:
    """
    Map the human-facing 'Surface' selector to the lie types
    used by the strokes-gained engine.
    """
    s = (surface_label or "Fairway").lower()
    if "fairway" in s:
        return "fairway"
    if "light" in s and "rough" in s:
        return "rough"
    if "heavy" in s and "rough" in s:
        # You can change this to 'recovery' if you want to treat heavy rough as jail
        return "rough"
    if "sand" in s or "bunker" in s:
        return "sand"
    if "recovery" in s:
        return "recovery"
    return "fairway"

def simulate_dispersion_samples(
    center_total: float,
    category: str,
    skill_factor: float,
    n: int = 400,
) -> np.ndarray:
    """Generate 1D dispersion samples around center_total for charting."""
    sigma = get_dispersion_sigma(category)
    sigma_eff = max(0.1, sigma * skill_factor)
    return np.random.normal(loc=center_total, scale=sigma_eff, size=n)


# ============================================================
# SIDEBAR: GLOBAL CONTROLS
# ============================================================

st.sidebar.title("Golf Caddy Settings")

driver_speed = st.sidebar.slider(
    "Current Driver Speed (mph)",
    min_value=90,
    max_value=120,
    value=st.session_state.driver_speed,
    help="Used to scale your entire bag's distances from a 100 mph baseline.",
)
st.session_state.driver_speed = driver_speed

tournament_mode = st.sidebar.checkbox(
    "Tournament Mode (USGA / R&A Legal)",
    value=st.session_state.tournament_mode,
    help=(
        "When enabled, Golf Caddy acts like a digital yardage book: "
        "raw distances only, no plays-like math or club recommendations."
    ),
)
st.session_state.tournament_mode = tournament_mode

st.sidebar.markdown("---")
st.sidebar.caption(
    "Quick tip: Use **Quick** mode on-course for fast decisions, "
    "then **Range** and **Combine** tabs on the practice tee to dial in your game."
)

# ---- Strokes-Gained Baseline (Handicap Profile) ---- #
if "sg_profile" not in st.session_state:
    st.session_state.sg_profile = "Tour / Scratch"

def scoring_profile_to_factor(label: str) -> float:
    lab = (label or "").lower()
    if "tour" in lab and "scratch" in lab:
        return 1.0           # Tour / scratch
    if "5–9" in lab or "5-9" in lab:
        return 1.08          # Slightly higher expected strokes
    if "10–14" in lab or "10-14" in lab:
        return 1.15
    if "15+" in lab:
        return 1.22
    return 1.0

sg_profile_label = st.sidebar.selectbox(
    "Strokes-Gained Baseline",
    ["Tour / Scratch", "5–9 Handicap", "10–14 Handicap", "15+ Handicap"],
    index=["Tour / Scratch", "5–9 Handicap", "10–14 Handicap", "15+ Handicap"].index(
        st.session_state.sg_profile
    ),
    help="Choose who you want SG to be relative to: tour-level or your handicap band.",
)
st.session_state.sg_profile = sg_profile_label
sg_profile_factor = scoring_profile_to_factor(sg_profile_label)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Quick tip: Use Quick mode on-course, then Range & Combine off-course "
    "to train your distance control and SG over time."
)


# Precompute bag for current driver speed
all_shots_base, scoring_shots, full_bag = build_all_candidate_shots(driver_speed)


# ============================================================
# MAIN TITLE & TABS
# ============================================================

st.title("Golf Caddy")

tab_caddy, tab_range, tab_yardages, tab_combine, tab_info = st.tabs(
    ["Play (Caddy)", "Range Mode", "Yardages", "Combine / Practice", "How it Works"]
)

# ============================================================
# ---------- CADDY TAB ----------
# ============================================================

with tab_caddy:
    if tournament_mode:
        # ---------- TOURNAMENT MODE: MINIMAL UI ---------- #
        st.subheader("Tournament Mode")

        # Pin input + big display
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
            st.markdown("")
            st.markdown("")
            st.markdown(
                f"<div style='text-align:right; font-size:22px;'>"
                f"<b>Pin: {pin_yardage:.0f} yds</b>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.caption(
            "Tournament Mode behaves like a digital yardage book: "
            "raw distances only, no plays-like math, no club recommendations, "
            "and no strokes-gained calculations."
        )

        # ---- Minimal Full-Bag Table ---- #
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(1)

        # Add dispersion estimate per club
        dispersion_list = []
        for _, row in df_full.iterrows():
            club = row["Club"]
            category = get_club_category_for_table(club)
            sigma = get_dispersion_sigma(
                "scoring_wedge"
                if "wedge" in category.lower()
                else "short_iron" if "short" in category.lower()
                else "mid_iron" if "mid" in category.lower()
                else "long"
            )
            dispersion_list.append(sigma)

        df_full["Dispersion (±yds)"] = dispersion_list

        # Minimal view
        df_basic = df_full[
            ["Club", "Carry (yds)", "Total (yds)", "Dispersion (±yds)"]
        ].reset_index(drop=True)

        st.markdown("### Raw Full-Bag Yardages")
        st.dataframe(df_basic, use_container_width=True)

        # Optional advanced numbers
        with st.expander("Show advanced ball data (ball speed, launch, spin)"):
            df_adv = df_full[
                [
                    "Club",
                    "Ball Speed (mph)",
                    "Launch (°)",
                    "Spin (rpm)",
                    "Carry (yds)",
                    "Total (yds)",
                    "Dispersion (±yds)",
                ]
            ].reset_index(drop=True)
            st.dataframe(df_adv, use_container_width=True)

        # Optional scoring wedge table
        with st.expander("Show scoring wedge / partial shot yardages"):
            df_score = pd.DataFrame(scoring_shots)
            df_score = df_score[["carry", "club", "shot_type", "trajectory"]]
            df_score.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
            df_score = df_score.sort_values("Carry (yds)", ascending=False).reset_index(
                drop=True
            )
            st.dataframe(df_score, use_container_width=True)

        st.info(
            "Use this screen during events where only distance information is allowed. "
            "All decision logic (plays-like, strategy, strokes gained) is disabled."
        )

    else:

        # Mode selector: Quick vs Advanced
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
            surface_label = st.selectbox(
                "Surface (Current Lie)",
                ["Fairway", "Light Rough", "Heavy Rough", "Sand", "Recovery"],
                help="Where the ball is currently sitting.",
            )
            strike_label = st.radio(
                "Strike Quality",
                ["Good", "Ok", "Bad"],
                horizontal=True,
                help="Good = solid contact, Ok = slight mishit, Bad = heavy / thin / poor strike.",
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
                    index=["Recreational", "Intermediate", "Highly Consistent"].index(
                        st.session_state.skill
                    ),
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

        # Skill factor for dispersion scaling (used in SG + charts)
        skill_factor = skill_to_factor(skill)

        all_shots = all_shots_base  # don't mutate cached shots

        # Normalize for logic
        wind_dir = wind_dir_label.lower()
        wind_strength = wind_strength_label.lower()
        strike_quality = strike_label.lower()
        start_surface = ui_surface_to_engine_lie(surface_label)

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

                # Apply tendency (distance bias) lightly
                if tendency == "Usually Short":
                    raw_target += 3.0
                elif tendency == "Usually Long":
                    raw_target -= 3.0

                # Plays-like pipeline
                after_wind = adjust_for_wind(raw_target, wind_dir, wind_strength)
                after_elev = apply_elevation(after_wind, elevation_label)
                # apply_lie is now effectively "apply strike quality" to distance
                plays_like = apply_lie(after_elev, strike_quality)

                st.markdown(
                    f"### Plays-like Yardage: **{plays_like:.1f} yds** "
                    f"{'(to safe center)' if using_center else '(to pin)'}"
                )

                # Auto strategy heuristic (can be refined later)
                if use_auto_strategy:
                    if trouble_short_label == "Severe" or trouble_long_label == "Severe":
                        strategy_label = STRATEGY_CONSERVATIVE
                    elif plays_like < 110 and skill_factor <= 1.0:
                        strategy_label = STRATEGY_AGGRESSIVE
                    else:
                        strategy_label = STRATEGY_BALANCED

                st.caption(f"Selected strategy: **{strategy_label}**")

                all_shots = all_shots_base  # do not mutate base

                # Recommend shots
                ranked = recommend_shots_with_sg(
                    target_total=plays_like,
                    candidates=all_shots,
                    short_trouble_label=trouble_short_label,
                    long_trouble_label=trouble_long_label,
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
                    st.warning("No reasonable candidate shots found near this plays-like yardage.")
                else:
                    best = ranked[0]

                    st.subheader("Recommended Options")
                    for i, s in enumerate(ranked, start=1):
                        st.markdown(
                            f"**{i}. {s['club']} — {s['shot_type']}** "
                            f"(Carry ≈ {s['carry']:.1f} yds, Total ≈ {s['total']:.1f} yds, "
                            f"SG ≈ {s['sg']:.3f})"
                        )
                        st.caption(s["reason"])

                    # Dispersion visualization for best option
                    st.markdown("### Dispersion Preview (Best Option)")

                    samples = simulate_dispersion_samples(
                        center_total=best["total"],
                        category=best["category"],
                        skill_factor=skill_factor,
                        n=400,
                    )
                    df_disp = pd.DataFrame({"Total (yds)": samples})
                    df_disp["Index"] = np.arange(len(df_disp))

                    chart = (
                        alt.Chart(df_disp)
                        .mark_circle(size=30, opacity=0.5)
                        .encode(
                            x=alt.X("Total (yds):Q", title="End Distance (yds)"),
                            y=alt.Y("Index:Q", axis=None),
                            tooltip=["Total (yds)"],
                        )
                        .properties(height=150)
                    )

                    target_rule = alt.Chart(
                        pd.DataFrame({"x": [plays_like]})
                    ).mark_rule(strokeDash=[6, 3]).encode(x="x:Q")

                    st.altair_chart(chart + target_rule, use_container_width=True)


# ============================================================
# ---------- RANGE MODE TAB ----------
# ============================================================

with tab_range:
    st.subheader("Range Mode: Validate & Tune Your Yardages")

    st.caption(
        "Use this tab on the practice tee: pick a club, hit a few shots, "
        "and enter your **actual average carry** to compare against the model."
    )

    clubs = [row["Club"] for row in full_bag]
    selected_club = st.selectbox("Club", clubs)

    # Find modeled values
    row = next((r for r in full_bag if r["Club"] == selected_club), None)

    if row:
        modeled_carry = row["Carry (yds)"]
        modeled_total = row["Total (yds)"]

        st.markdown(
            f"**Modeled Carry:** {modeled_carry:.1f} yds &nbsp;&nbsp; "
            f"**Modeled Total:** {modeled_total:.1f} yds"
        )

        actual = st.number_input(
            "Your observed average carry (range or launch monitor)",
            min_value=0.0,
            max_value=400.0,
            value=float(
                st.session_state.range_actual_carries.get(selected_club, modeled_carry)
            ),
            step=1.0,
        )

        st.session_state.range_actual_carries[selected_club] = actual

        diff = actual - modeled_carry
        st.markdown(
            f"- Difference (Actual − Modeled): **{diff:+.1f} yds** "
            f"({'longer' if diff > 0 else 'shorter' if diff < 0 else 'match'})"
        )

        # Simple comparison chart
        df_range = pd.DataFrame(
            {
                "Type": ["Modeled", "Actual"],
                "Carry (yds)": [modeled_carry, actual],
            }
        )

        chart_range = (
            alt.Chart(df_range)
            .mark_bar()
            .encode(
                x=alt.X("Type:N", title=""),
                y=alt.Y("Carry (yds):Q"),
                tooltip=["Type", "Carry (yds)"],
            )
            .properties(height=250)
        )

        st.altair_chart(chart_range, use_container_width=True)


# ============================================================
# ---------- YARDAGES TAB ----------
# ============================================================

with tab_yardages:
    st.subheader("Scoring & Full-Bag Yardages")

    col_y1, col_y2 = st.columns(2)

    with col_y1:
        st.markdown("### Scoring Shot Yardage Table")
        df_scoring = pd.DataFrame(scoring_shots)
        df_scoring = df_scoring[["carry", "club", "shot_type", "trajectory"]]
        df_scoring.columns = ["Carry (yds)", "Club", "Shot Type", "Trajectory"]
        df_scoring = df_scoring.sort_values("Carry (yds)", ascending=False).reset_index(
            drop=True
        )
        st.dataframe(df_scoring, use_container_width=True)

    with col_y2:
        st.markdown("### Full Bag Yardages")
        df_full = pd.DataFrame(full_bag)
        df_full["Ball Speed (mph)"] = df_full["Ball Speed (mph)"].round(1)
        df_full["Carry (yds)"] = df_full["Carry (yds)"].round(1)
        df_full["Total (yds)"] = df_full["Total (yds)"].round(1)

        dispersion_list = []
        for _, row in df_full.iterrows():
            club = row["Club"]
            category = get_club_category_for_table(club)
            sigma = get_dispersion_sigma(
                "scoring_wedge"
                if "wedge" in category.lower()
                else "short_iron" if "short" in category.lower()
                else "mid_iron" if "mid" in category.lower()
                else "long"
            )
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

    st.markdown("### Gapping Chart (Carry vs Club)")

    df_gap = df_full.copy()
    df_gap["Order"] = df_gap.index  # already sorted by carry in desc/asc previously
    # For chart, sort from shortest to longest
    df_gap = df_gap.sort_values("Carry (yds)", ascending=True).reset_index(drop=True)
    df_gap["Index"] = df_gap.index

    chart_gap = (
        alt.Chart(df_gap)
        .mark_line(point=True)
        .encode(
            x=alt.X("Index:O", title="Club (short → long)", axis=alt.Axis(labels=False)),
            y=alt.Y("Carry (yds):Q"),
            tooltip=["Club", "Carry (yds)", "Total (yds)", "Dispersion (±yds)"],
        )
        .properties(height=300)
    )
    text = (
        alt.Chart(df_gap)
        .mark_text(dy=-10, size=11)
        .encode(
            x="Index:O",
            y="Carry (yds):Q",
            text="Club",
        )
    )

    st.altair_chart(chart_gap + text, use_container_width=True)


# ============================================================
# ---------- COMBINE / PRACTICE TAB ----------
# ============================================================

with tab_combine:
    st.subheader("Combine / Practice (Perfect Carry Helper)")

    st.caption(
        "This tab helps you design a TrackMan-style practice: choose a target distance, "
        "and Golf Caddy will suggest which club/shot and carry window should score best "
        "based on your modeled dispersion and strokes-gained engine."
    )

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        combine_target = st.slider(
            "Target Pin Distance (yards)",
            min_value=40,
            max_value=220,
            value=100,
            step=5,
        )
    with col_c2:
        combine_skill = st.radio(
            "Your current ball-striking level (for this combine)",
            ["Recreational", "Intermediate", "Highly Consistent"],
            index=["Recreational", "Intermediate", "Highly Consistent"].index(
                st.session_state.skill
            ),
        )
        combine_skill_factor = skill_to_factor(combine_skill)

    st.markdown(
        f"**Target distance for this station:** {combine_target} yds "
        "(you can treat this like the pin number on a real combine)."
    )

    # Filter candidates: ignore driver/3W for short targets
    candidates = []
    for c in all_shots_base:
        # Keep candidates within a broad band around target
        if 0.5 * combine_target <= c["total"] <= 1.6 * combine_target:
            candidates.append(c)

    if st.button("Compute Optimal Carry Window 🎯"):
        if not candidates:
            st.warning(
                "No candidate shots near that distance. Try a different target or adjust driver speed."
            )
        else:
            best_cfg = compute_optimal_carry_for_target(
                target_pin_yards=combine_target,
                candidates=candidates,
                skill_factor=combine_skill_factor,
                short_trouble_label="None",
                long_trouble_label="None",
                start_surface="fairway",
                green_firmness_label="Medium",
                n_sim=500,
                carry_search_window=10.0,
                sg_profile_factor=sg_profile_factor,
            )

            if not best_cfg:
                st.warning("Could not find a stable optimal carry configuration.")
            else:
                b_club = best_cfg["club"]
                b_shot = best_cfg["shot_type"]
                aim_total = best_cfg["aim_total"]
                sg_val = best_cfg["sg"]

                st.markdown(
                    f"### Suggested Combine Plan\n"
                    f"- **Club / Shot:** {b_club} — {b_shot}\n"
                    f"- **Plays-to (aimed carry/total):** ≈ **{aim_total:.1f} yds**\n"
                    f"- **Modeled SG from this station:** ≈ **{sg_val:.3f}** per shot\n\n"
                    f"When you run a station at {combine_target} yds, "
                    f"try to land shots around {aim_total:.1f} yds on average."
                )

                # For visualization, also compute SG for each candidate around this target
                ranked_for_chart = recommend_shots_with_sg(
                    target_total=combine_target,
                    candidates=candidates,
                    short_trouble_label="None",
                    long_trouble_label="None",
                    green_firmness_label="Medium",
                    strategy_label=STRATEGY_BALANCED,
                    start_distance_yards=combine_target,
                    start_surface="fairway",
                    front_yards=0.0,
                    back_yards=0.0,
                    skill_factor=combine_skill_factor,
                    pin_lateral_offset=0.0,
                    green_width=0.0,
                    n_sim=400,
                    top_n=15,
                    sg_profile_factor=sg_profile_factor,
                )

                if ranked_for_chart:
                    df_combine = pd.DataFrame(ranked_for_chart)
                    df_combine["Label"] = (
                        df_combine["club"] + " - " + df_combine["shot_type"]
                    )

                    chart_sg = (
                        alt.Chart(df_combine)
                        .mark_bar()
                        .encode(
                            x=alt.X("Label:N", sort=None, title="Club / Shot"),
                            y=alt.Y("sg:Q", title="Modeled SG per shot"),
                            tooltip=[
                                "club",
                                "shot_type",
                                "carry",
                                "total",
                                "sg",
                                "expected_strokes",
                            ],
                        )
                        .properties(height=320)
                    )

                    st.markdown("#### SG Comparison Across Candidate Shots")
                    st.altair_chart(chart_sg, use_container_width=True)

                st.info(
                    "Combine tip: pick 4–6 distances (e.g., 55, 75, 95, 115, 135, 155) "
                    "and use this tab to choose your club/shot and aim window for each station. "
                    "Then track how close your actual averages are to the suggested carries."
                )

# ============================================================
# ---------- HOW IT WORKS TAB ----------
# ============================================================

with tab_info:
    st.subheader("How Golf Caddy Thinks")

    st.markdown(
        """
### 1. Baseline Bag & Wedge Model

Golf Caddy starts from a 100 mph driver baseline and scales your entire bag
based on your current driver speed. For wedges, it also models partial swings
(3/4, 1/2, 1/4) with their own carry multipliers and slightly tighter dispersion
than full swings.

### 2. Plays-like Yardage

In Caddy mode (non-tournament), your entered pin or center-of-green distance is
converted into a **plays-like yardage** using:

- **Wind**: Headwinds hurt more than tailwinds help, crosswind adds a small safety bump
- **Elevation**: Uphill adds yardage, downhill subtracts yardage
- **Lie**: Good / Ok / Bad alters how efficient your contact is

### 3. Dispersion & Skill

Each club type (scoring wedge, short iron, mid iron, long club) has a modeled
**distance dispersion window**. Your selected skill level:

- Recreational → larger dispersion
- Intermediate → baseline
- Highly Consistent → tighter windows

These dispersion windows drive both the **dispersion charts** and the
**strokes-gained simulations**.

### 4. Strokes-Gained Engine

Golf Caddy uses a simplified but tour-informed strokes-gained model:

- Different **expected strokes tables** for fairway, rough, sand, and recovery
- From your starting distance, it:
  - Simulates many possible outcomes for each candidate shot
  - Applies **trouble penalties** for big misses short or long
  - Computes expected strokes after the shot and compares this to a baseline
- The result is a **strokes-gained value (SG)**: positive is good, negative is costly.

### 5. Strategy

Caddy mode supports:

- **Balanced**: Valuing both scoring and safety
- **Conservative**: Extra penalty for bringing trouble into play
- **Aggressive**: Slightly softened penalties to allow more flag-hunting

Short severe trouble, longer shots, and higher dispersion push the engine
toward more conservative plays when auto-strategy is enabled.

### 6. Tournament Mode

Tournament Mode removes:

- Plays-like calculations
- Club recommendations
- Strategy / SG logic

It becomes a digital yardage book: full-bag and scoring-wedge tables with
modeled carry, total, and dispersion only. This aligns with current USGA / R&A
guidance for allowed distance information.

### 7. Range & Combine

- **Range Mode** lets you compare modeled vs actual carry by club, so you can
  calibrate your expectations and see where your modeled yardages might need
  adjustment.

- **Combine / Practice** uses the SG engine to suggest the **best club/shot and aim
  window** for a specific target distance, similar to a TrackMan Combine
  station. Over time, this helps you build better distance control and course
  management instincts.

---

Use this tool as both a **learning engine** and a **decision aid**. The more
you practice with Range and Combine, the more confidently you can trust your
instincts (and Tournament Mode) when the pressure is on.
"""
    )
