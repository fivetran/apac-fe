from logminer.watermarks import (
    adapt_span,
    calculate_low_watermark,
    choose_window_end,
)


def test_low_watermark_is_oldest_unresolved_position():
    assert calculate_low_watermark(500, 100, 300, 250) == 100


def test_low_watermark_advances_when_nothing_is_unresolved():
    assert calculate_low_watermark(501) == 501


def test_window_end_is_bounded_by_fixed_target():
    assert choose_window_end(100, 150, 25) == 124
    assert choose_window_end(140, 150, 25) == 150


def test_span_adapts_within_limits():
    assert adapt_span(100, 0, 25, 400) == 200
    assert adapt_span(100, 100_000, 25, 400) == 50
