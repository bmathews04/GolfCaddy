[![codecov](https://codecov.io/github/bmathews04/GolfShotSelector/branch/main/graph/badge.svg?token=NIDVNSLRM2)](https://codecov.io/github/bmathews04/GolfShotSelector)


# GolfShotSelector ⛳

Data-driven shot selector using strokes-gained math, dispersion, wind, elevation, lie, and strategy.

[![Tests](https://github.com/bmathews04/GolfShotSelector/actions/workflows/test.yml/badge.svg)](https://github.com/bmathews04/GolfShotSelector/actions/workflows/test.yml)
[![Coverage](https://codecov.io/gh/bmathews04/GolfShotSelector/branch/main/graph/badge.svg)](https://codecov.io/gh/bmathews04/GolfShotSelector)

Live app → (we’ll deploy in 30 seconds)


Overview

Golf Caddy is a Streamlit-based decision-support tool designed to assist golfers in selecting optimal shots under varying playing conditions.
The application incorporates ball-flight modeling, shot dispersion estimates, environmental adjustments, and strategic weighting to produce recommendations consistent with professional caddie decision-making.

Purpose

Golf Caddy aims to:

Improve on-course decision quality by considering multiple real-world factors.

Provide golfers with a rational, repeatable method for selecting clubs.

Visualize shot dispersion and green interaction to support strategic planning.

Reduce guesswork through a data-informed approach rather than relying solely on intuition.

Key Features
1. Shot Recommendation Engine

Golf Caddy evaluates all relevant shots (full-swing irons, woods, hybrids, and scoring wedges) using a multi-factor scoring model that accounts for:

Expected carry and total distance

Distance deviation from the adjusted target

Trouble short and long of the green

Shot dispersion characteristics

Club category suitability

Shot type (full, partial, choke-down, etc.)

Green firmness and roll behavior

User-selected strategy (Balanced, Conservative, Aggressive)

2. Environmental Adjustment Modeling

The system automatically adjusts the working yardage (“plays as” distance) using:

Wind direction and strength

Elevation change

Lie conditions

Optional safe center-of-green targeting based on front/back yardages

3. Visualization Tools

Golf Caddy includes two primary visual aids:

Dispersion Error-Bar Chart:
Displays expected total distance with ±1 standard deviation for each recommended shot.

Shot Window and Green Mini-Map:
Shows each shot's distance window in relation to:

Pin position

Adjusted target distance

Front and back of the green

Safe center (if enabled)

These visual tools help users quickly evaluate how well each option fits the intended landing zone.

4. User Interface Design

The interface is structured to support rapid decision-making:

Core inputs are immediately visible (distance, wind, lie, elevation, strategy).

Advanced variables (green firmness, trouble areas, safe center logic) are placed in an expandable section.

A situation summary is displayed under the computed target to aid comprehension and confirm inputs.

System Requirements

Python 3.9 or later

Streamlit

Altair

Pandas

Install dependencies using:

pip install streamlit pandas altair

Running the Application

Execute the following command in your terminal:

streamlit run app.py


Replace app.py with the filename containing the Golf Caddy application.

Usage Overview
Step 1. Provide Core Inputs

Users enter:

Pin yardage

Wind direction and strength

Ball lie

Elevation

Desired strategy

Step 2. (Optional) Configure Advanced Inputs

Within the advanced section:

Front/back of green yardages

Green firmness

Trouble short/long of the target

Step 3. Generate Recommendations

Upon selecting “Suggest Shots”, the system:

Calculates adjusted “plays as” distance

Produces a situation summary

Recommends the top three shot options

Provides written explanations for each recommendation

Displays dispersion visualization and green mini-map

Methodological Basis
Distance Scaling

All baseline distances scale proportionally with driver swing speed to approximate individual variance.

Shot Dispersion

Club-category-based dispersion estimates are applied:

Long clubs: larger standard deviation

Scoring wedges: smallest variance

Strategic Weighting

Strategy settings modify how strongly the system penalizes high-risk outcomes:

Conservative increases penalties for dispersion and trouble proximity

Aggressive reduces penalties to favor proximity to the pin

Balanced applies neutral weighting

Safe Center Targeting

When front/back yardages are provided, the system automatically targets the geometric center. This emulates common professional strategy to reduce exposure to front/back hazards.

Future Enhancements (Optional Roadmap)

These ideas are not implemented but may be considered:

Range Mode for calibrating yardages during practice

User-specific dispersion and distance profiles

Persistent profile storage

Course-based GPS integration

Enhanced lateral-dispersion modeling

License

This project is available for personal or research use.
Please include attribution if incorporated into larger systems or publications.
