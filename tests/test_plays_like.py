import strokes_gained_engine as sge


def test_into_wind_increases_plays_like():
    base = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="None",
        wind_strength_label="None",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=75,
    )
    into = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="Into",
        wind_strength_label="Medium",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=75,
    )
    assert into > base


def test_downwind_reduces_plays_like():
    base = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="None",
        wind_strength_label="None",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=75,
    )
    down = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="Down",
        wind_strength_label="Medium",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=75,
    )
    assert down < base


def test_cold_plays_longer_hot_plays_shorter_but_not_insane():
    cold = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="None",
        wind_strength_label="None",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=50,
    )
    neutral = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="None",
        wind_strength_label="None",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=75,
    )
    hot = sge.calculate_plays_like_yardage(
        raw_yards=150,
        wind_dir="None",
        wind_strength_label="None",
        elevation_label="Flat",
        lie_label="Good",
        tendency_label="Neutral",
        temp_f=90,
    )

    assert cold > neutral > hot
    # sanity guard: temperature shouldn’t move it 30+ yards
    assert abs(cold - hot) < 20
