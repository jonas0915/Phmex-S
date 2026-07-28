from overlap import mann_whitney_u


def test_mann_whitney_separated_samples_low_p():
    a = [1, 2, 3, 4, 5, 6, 7, 8]
    b = [11, 12, 13, 14, 15, 16, 17, 18]
    u, p = mann_whitney_u(a, b)
    assert p < 0.01


def test_mann_whitney_identical_samples_high_p():
    a = [1, 2, 3, 4, 5, 6, 7, 8]
    u, p = mann_whitney_u(a, list(a))
    assert p > 0.5


def test_mann_whitney_small_sample_guard():
    import math
    u, p = mann_whitney_u([1, 2], [3, 4])
    assert math.isnan(u) and p == 1.0
