# ⛳ Golf Caddy

Data-driven on-course shot selector that beats gut feel.  
Uses real strokes-gained math, dispersion modeling, wind, elevation, lie penalties, temperature, and your chosen risk strategy.

**Live App** → [golfshotselector.streamlit.app](https://golf-caddy-bryanmathews.streamlit.app/)

[![Tests](https://github.com/bmathews04/GolfShotSelector/actions/workflows/test.yml/badge.svg)](https://github.com/bmathews04/GolfShotSelector/actions/workflows/test.yml)
[![Coverage](https://codecov.io/gh/bmathews04/GolfShotSelector/branch/main/graph/badge.svg)](https://codecov.io/gh/bmathews04/GolfShotSelector)
[![Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://golf-caddy-bryanmathews.streamlit.app/)

![demo](https://raw.githubusercontent.com/bmathews04/GolfShotSelector/main/screenshot.png)  
*150 yd into the wind → instantly see why 6i beats 5i*

### Features
- Full-bag + partial-swing recommendations
- Monte-Carlo dispersion simulation (400 shots)
- Safe-center aiming when you give front/pin/back yardages
- Left/right trouble penalties
- Aggressive / Balanced / Conservative strategies

### Quick start
```bash
git clone https://github.com/bmathews04/GolfShotSelector.git
cd GolfShotSelector
pip install -r requirements.txt
streamlit run app.py
