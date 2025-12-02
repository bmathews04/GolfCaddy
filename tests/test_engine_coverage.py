import strokes_gained_engine as sge

# 1. Cover the full club scoring loop + ranking (hits lines 378–401, 839–890)
def test_full_club_scoring_and_ranking():
    recs = sge.get_recommendations(
        raw_yards=165,
        wind_dir="into",
        wind_strength="medium",
        elevation="uphill",
        lie="fairway",
        strategy="Balanced",
        temp_f=75
    )
    assert len(recs) >= 5
    assert recs[0]["club"] in sge.FULL_BAG_BASE.index
    assert recs[0]["total_score"] > recs[-1]["total_score"]  # best > worst

# 2. Cover hybrid / partial swing fallback path (lines 910–979)
def test_hybrid_and_partial_swing_logic():
    # Force a distance where no full club fits perfectly
    recs = sge.get_recommendations(138, "calm", "none", "flat", "fairway", "Balanced", 75)
    clubs_used = [r["club"] for r in recs[:3]]
    # Should suggest hybrid or choked wedge
    assert any("hybrid" in c.lower() or "pw" in c.lower() or "gw" in c.lower() for c in clubs_used)

# 3. Cover extreme environmental scaling (hits 462–534, 621–637)
def test_extreme_conditions_scaling():
    plays_like = sge.calculate_plays_like_yardage(
        raw_yards=200,
        wind_dir="down",
        wind_strength_label="heavy",
        elevation_label="severe downhill",
        lie_label="tee",
        tendency_label="Neutral",
        temp_f=100
    )
    # Should be WAY shorter than 200
    assert plays_like < 160

    plays_like2 = sge.calculate_plays_like_yardage(
        raw_yards=100,
        wind_dir="into",
        wind_strength_label="heavy",
        elevation_label="severe uphill",
        lie_label="thick rough",
        tendency_label="Neutral",
        temp_f=32
    )
    # Should be WAY longer than 100
    assert plays_like2 > 140

# 4. Cover green interaction / safe-center logic (lines 1000–1049)
def test_safe_center_aim_point():
    recs = sge.get_recommendations(
        raw_yards=150,
        wind_dir="calm",
        wind_strength="none",
        elevation="flat",
        lie="fairway",
        strategy="Conservative",
        temp_f=75,
        front_yards=18,
        pin_yards=25,
        back_yards=35
    )
    top = recs[0]
    # Conservative should aim well behind the pin
    assert top["aim_yards"] > 25

# 5. Cover trouble zones / penalty avoidance (lines 503–534)
def test_trouble_zone_penalty():
    # Same distance, but one has left trouble → should penalize left-dispersing clubs
    recs_safe = sge.get_recommendations(120, "calm", "none", "flat", "fairway", "Balanced", 75)
    recs_trouble = sge.get_recommendations(
        120, "calm", "none", "flat", "fairway", "Balanced", 75,
        left_trouble=True
    )
    # Top club might change or score should be lower when trouble exists
    assert recs_trouble[0]["total_score"] < recs_safe[0]["total_score"] or \
           recs_trouble[0]["club"] != recs_safe[0]["club"]
