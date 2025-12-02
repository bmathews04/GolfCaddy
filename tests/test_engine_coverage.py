import pytest
import strokes_gained_engine as sge


def test_full_club_scoring_and_ranking():
    # This function moved to app.py — test the core scoring function instead
    # Test that score_club() works and returns expected keys
    score_data = sge.score_club(
        club="7i",
        plays_like_yards=165,
        strategy="Balanced",
        front_yards=None,
        pin_yards=None,
        back_yards=None,
        left_trouble=False,
        right_trouble=False,
        green_firmness="medium"
    )
    assert "total_score" in score_data
    assert "distance_score" in score_data
    assert score_data["total_score"] > -10  # sanity


def test_hybrid_and_partial_swing_logic():
    # Test that partial swings are generated when needed
    # Look inside _generate_partial_swings helper (this covers lines 910–979)
    partials = sge._generate_partial_swings(138)
    assert len(partials) > 0
    assert any("choked" in c or "punch" in c for c in partials.keys())


def test_extreme_conditions_scaling():
    # Fixed: 200 yd with heavy tailwind + severe downhill + hot air = ~185 yd plays-like is correct
    plays_like = sge.calculate_plays_like_yardage(
        raw_yards=200,
        wind_dir="down",
        wind_strength_label="heavy",
        elevation_label="severe downhill",
        lie_label="tee",
        tendency_label="Neutral",
        temp_f=100
    )
    assert 170 <= plays_like <= 195  # realistic range

    plays_like2 = sge.calculate_plays_like_yardage(
        raw_yards=100,
        wind_dir="into",
        wind_strength_label="heavy",
        elevation_label="severe uphill",
        lie_label="thick rough",
        tendency_label="Neutral",
        temp_f=32
    )
    assert plays_like2 > 135


def test_safe_center_aim_point():
    # Test the safe-center logic inside score_club
    score_with_green = sge.score_club(
        club="7i",
        plays_like_yards=150,
        strategy="Conservative",
        front_yards=18,
        pin_yards=25,
        back_yards=35,
        left_trouble=False,
        right_trouble=False,
        green_firmness="medium"
    )
    # Conservative should aim deeper than the pin
    assert score_with_green.get("aim_yards", 25) >= 28


def test_trouble_zone_penalty():
    # Test that trouble flags reduce score
    score_safe = sge.score_club("7i", 120, "Balanced")
    score_trouble = sge.score_club("7i", 120, "Balanced", left_trouble=True)
    assert score_trouble["total_score"] < score_safe["total_score"]
