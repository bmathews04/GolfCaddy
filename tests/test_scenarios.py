import strokes_gained_engine as sge


def test_generate_random_scenario_has_required_keys_and_plausible_output():
    for _ in range(25):
        scenario = sge.generate_random_scenario()

        # Basic shape
        for key in [
            "raw_yards",
            "wind_dir",
            "wind_strength",
            "elevation",
            "lie",
            "temp_f",
        ]:
            assert key in scenario

        plays_like = sge.calculate_plays_like_yardage(
            raw_yards=scenario["raw_yards"],
            wind_dir=scenario["wind_dir"],
            wind_strength_label=scenario["wind_strength"],
            elevation_label=scenario["elevation"],
            lie_label=scenario["lie"],
            tendency_label="Neutral",
            temp_f=scenario["temp_f"],
        )

        # Plays-like should remain in a sane on-course range
        assert 40 <= plays_like <= 260
