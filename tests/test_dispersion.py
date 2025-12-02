import strokes_gained_engine as sge


def test_lie_dispersion_factor_ordering():
    fairway = sge.lie_dispersion_factor("fairway")
    ok = sge.lie_dispersion_factor("ok")
    rough = sge.lie_dispersion_factor("rough")
    bunker = sge.lie_dispersion_factor("sand")

    assert fairway < ok <= rough
    assert fairway < bunker


def test_sigma_increases_with_worse_lie_for_mid_iron():
    base_sigma = sge.get_dispersion_sigma("mid_iron")

    fairway_sigma = base_sigma * sge.lie_dispersion_factor("fairway")
    rough_sigma = base_sigma * sge.lie_dispersion_factor("rough")

    assert rough_sigma > fairway_sigma
