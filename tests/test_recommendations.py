import strokes_gained_engine as sge


def _simple_candidates():
    # Compact fake bag around 150 yards
    return [
        {
            "club": "8i",
            "shot_type": "Full",
            "trajectory": "Stock",
            "carry": 140,
            "total": 145,
            "category": "short_iron",
        },
        {
            "club": "7i",
            "shot_type": "Full",
            "trajectory": "Stock",
            "carry": 150,
            "total": 155,
            "category": "mid_iron",
        },
        {
            "club": "6i",
            "shot_type": "Full",
            "trajectory": "Stock",
            "carry": 160,
            "total": 165,
            "category": "mid_iron",
        },
    ]


def test_recommendations_sorted_by_sg_desc():
    ranked = sge.recommend_shots_with_sg(
        target_total=150,
        candidates=_simple_candidates(),
        short_trouble_label="None",
        long_trouble_label="None",
        left_trouble_label="None",
        right_trouble_label="None",
        strategy_label=sge.STRATEGY_BALANCED,
        start_distance_yards=150,
        start_surface="fairway",
        sg_profile_factor=1.0,
        top_n=3,
    )

    # ensure non-empty
    assert ranked
    # SG should be non-increasing down the list
    for a, b in zip(ranked, ranked[1:]):
        assert a["sg"] >= b["sg"]


def test_severe_long_trouble_penalizes_long_option():
    no_trouble = sge.recommend_shots_with_sg(
        target_total=150,
        candidates=_simple_candidates(),
        short_trouble_label="None",
        long_trouble_label="None",
        left_trouble_label="None",
        right_trouble_label="None",
        strategy_label=sge.STRATEGY_BALANCED,
        start_distance_yards=150,
        start_surface="fairway",
        sg_profile_factor=1.0,
        top_n=3,
    )

    long_trouble = sge.recommend_shots_with_sg(
        target_total=150,
        candidates=_simple_candidates(),
        short_trouble_label="None",
        long_trouble_label="Severe",
        left_trouble_label="None",
        right_trouble_label="None",
        strategy_label=sge.STRATEGY_BALANCED,
        start_distance_yards=150,
        start_surface="fairway",
        sg_profile_factor=1.0,
        top_n=3,
    )

    # Find the 6-iron entry in each result
    six_no = next(s for s in no_trouble if s["club"] == "6i")
    six_long = next(s for s in long_trouble if s["club"] == "6i")

    assert six_long["sg"] < six_no["sg"]
