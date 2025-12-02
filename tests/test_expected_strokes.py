import strokes_gained_engine as sge


def test_expected_strokes_increases_with_distance():
    s1 = sge.expected_strokes(50, surface="fairway", handicap_factor=1.0)
    s2 = sge.expected_strokes(150, surface="fairway", handicap_factor=1.0)
    s3 = sge.expected_strokes(250, surface="fairway", handicap_factor=1.0)

    assert s1 < s2 < s3


def test_rough_and_sand_are_worse_than_fairway():
    fairway = sge.expected_strokes(150, surface="fairway", handicap_factor=1.0)
    rough = sge.expected_strokes(150, surface="rough", handicap_factor=1.0)
    sand = sge.expected_strokes(150, surface="sand", handicap_factor=1.0)

    assert fairway < rough < sand


def test_handicap_factor_scales_difficulty():
    low = sge.expected_strokes(150, surface="fairway", handicap_factor=0.8)
    mid = sge.expected_strokes(150, surface="fairway", handicap_factor=1.0)
    high = sge.expected_strokes(150, surface="fairway", handicap_factor=1.3)

    assert low < mid < high
