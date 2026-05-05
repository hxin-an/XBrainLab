from XBrainLab.ui.table_sizing import scaled_column_widths


def test_scaled_column_widths_fill_available_width() -> None:
    widths = scaled_column_widths((240, 84, 112), 640, min_width=48)

    assert sum(widths) == 640
    assert widths[0] > 240
    assert all(width >= 48 for width in widths)


def test_scaled_column_widths_shrink_to_available_width() -> None:
    widths = scaled_column_widths((240, 84, 112), 320, min_width=48)

    assert sum(widths) == 320
    assert max(widths) < 240
    assert all(width >= 48 for width in widths)


def test_scaled_column_widths_respects_minimum_when_too_narrow() -> None:
    widths = scaled_column_widths((240, 84, 112), 100, min_width=48)

    assert widths == [48, 48, 48]
