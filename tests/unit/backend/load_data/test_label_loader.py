import numpy as np
import pytest
import scipy.io

from XBrainLab.backend.load_data.label_loader import load_label_file


def test_txt_returns_integer_sequence_and_ignores_line_boundaries(tmp_path):
    path = tmp_path / "labels.txt"
    path.write_text("1\n2 3\n4 5\n", encoding="utf-8")

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, np.array([1, 2, 3, 4, 5]))
    assert labels.dtype.kind in {"i", "u"}


def test_txt_ignores_non_integer_tokens(tmp_path):
    path = tmp_path / "labels.txt"
    path.write_text("1 2 invalid 3", encoding="utf-8")

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, np.array([1, 2, 3]))


def test_empty_txt_returns_empty_integer_array(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    labels = load_label_file(str(path))

    assert labels.shape == (0,)
    assert labels.tolist() == []


def test_missing_label_file_is_rejected():
    with pytest.raises(FileNotFoundError, match=r"File not found: non_existent\.txt"):
        load_label_file("non_existent.txt")


def test_unsupported_label_format_is_rejected(tmp_path):
    path = tmp_path / "labels.xyz"
    path.write_text("1,2,3", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Unsupported file format"):
        load_label_file(str(path))


def test_mat_prefers_label_like_variable_over_first_variable(tmp_path):
    path = tmp_path / "labels.mat"
    scipy.io.savemat(
        str(path),
        {
            "aaa_meta": np.array([[999]]),
            "classlabel": np.array([[1], [2], [3]]),
        },
    )

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, np.array([1, 2, 3], dtype=np.int32))


def test_mat_reviewed_label_variable_overrides_automatic_selection(tmp_path):
    path = tmp_path / "labels.mat"
    scipy.io.savemat(
        str(path),
        {
            "classlabel": np.array([9, 9, 9]),
            "target": np.array([1, 2, 1]),
        },
    )

    labels = load_label_file(str(path), label_field="target")

    np.testing.assert_array_equal(labels, np.array([1, 2, 1], dtype=np.int32))


def test_mat_reviewed_label_and_sample_anchor_form_mne_events(tmp_path):
    path = tmp_path / "labels.mat"
    scipy.io.savemat(
        str(path),
        {
            "classlabel": np.array([1, 2, 1]),
            "cue_onset": np.array([100, 250, 400]),
        },
    )

    events = load_label_file(
        str(path),
        label_field="classlabel",
        anchor="cue_onset",
    )

    np.testing.assert_array_equal(
        events,
        np.array([[100, 0, 1], [250, 0, 2], [400, 0, 1]], dtype=np.int32),
    )


@pytest.mark.parametrize(
    ("duration_field", "duration_values"),
    [
        ("cue_duration", np.array([50, 75])),
        ("offset", np.array([150, 325])),
    ],
    ids=("duration", "end-anchor"),
)
def test_mat_reviewed_duration_is_returned_as_sample_interval(
    tmp_path,
    duration_field,
    duration_values,
):
    path = tmp_path / "labels.mat"
    scipy.io.savemat(
        str(path),
        {
            "classlabel": np.array([1, 2]),
            "cue_onset": np.array([100, 250]),
            duration_field: duration_values,
        },
    )

    events = load_label_file(
        str(path),
        label_field="classlabel",
        anchor="cue_onset",
        duration_field=duration_field,
    )

    assert events == [
        {"onset": 100, "duration": 50, "label": 1},
        {"onset": 250, "duration": 75, "label": 2},
    ]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (np.array([[1], [2], [3]]), np.array([1, 2, 3], dtype=np.int32)),
        (np.array([[4, 5, 6]]), np.array([4, 5, 6], dtype=np.int32)),
        (
            np.array([[0, 0, 1], [100, 0, 2], [200, 0, 3]]),
            np.array([1, 2, 3], dtype=np.int32),
        ),
        (
            np.array([[1, 2], [3, 4], [5, 6]]),
            np.array([1, 2, 3, 4, 5, 6], dtype=np.int32),
        ),
        (np.array([10, 20, 30]), np.array([10, 20, 30], dtype=np.int32)),
        (np.arange(24).reshape(2, 3, 4), np.arange(24, dtype=np.int32)),
    ],
    ids=(
        "column-vector",
        "row-vector",
        "mne-events",
        "nonstandard-matrix",
        "flat-vector",
        "higher-dimensional",
    ),
)
def test_mat_shapes_normalize_to_integer_label_sequence(tmp_path, data, expected):
    path = tmp_path / "labels.mat"
    scipy.io.savemat(str(path), {"y": data})

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, expected)
    assert labels.dtype == np.dtype(np.int32)


def test_mat_without_data_variables_is_rejected(tmp_path):
    path = tmp_path / "empty.mat"
    scipy.io.savemat(str(path), {})

    with pytest.raises(ValueError, match=r"No variables"):
        load_label_file(str(path))


def test_csv_onset_label_and_duration_return_timestamp_events(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text(
        "onset,label,duration\n1.0,EventA,0.5\n2.0,EventB,0.8\n",
        encoding="utf-8",
    )

    events = load_label_file(str(path))

    assert events == [
        {"onset": 1.0, "label": "EventA", "duration": 0.5},
        {"onset": 2.0, "label": "EventB", "duration": 0.8},
    ]


def test_csv_time_and_trial_type_use_default_zero_duration(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("time,trial_type\n0.5,Left\n1.5,Right\n", encoding="utf-8")

    events = load_label_file(str(path))

    assert events == [
        {"onset": 0.5, "label": "Left", "duration": 0.0},
        {"onset": 1.5, "label": "Right", "duration": 0.0},
    ]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("label\n1\n2\n3\n", np.array([1, 2, 3])),
        ("values\n10\n20\n30\n", np.array([10, 20, 30])),
        ("col_a,col_b\n1,100\n2,200\n3,300\n", np.array([1, 2, 3])),
    ],
    ids=("label-column", "single-column", "first-of-multiple-columns"),
)
def test_csv_without_timing_returns_one_label_sequence(tmp_path, content, expected):
    path = tmp_path / "labels.csv"
    path.write_text(content, encoding="utf-8")

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, expected)


def test_tsv_label_column_returns_sequence(tmp_path):
    path = tmp_path / "labels.tsv"
    path.write_text("label\n5\n6\n7\n", encoding="utf-8")

    labels = load_label_file(str(path))

    np.testing.assert_array_equal(labels, np.array([5, 6, 7]))


def test_tsv_latency_and_type_return_timestamp_events(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text("latency\ttype\n0.1\tA\n0.2\tB\n", encoding="utf-8")

    events = load_label_file(str(path))

    assert events == [
        {"onset": 0.1, "label": "A", "duration": 0.0},
        {"onset": 0.2, "label": "B", "duration": 0.0},
    ]


def test_tsv_reviewed_columns_override_automatic_selection(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "sample\ttrial_type\tignored\n128\tleft\tnoise\n256\tright\tnoise\n",
        encoding="utf-8",
    )

    events = load_label_file(
        str(path),
        label_field="trial_type",
        anchor="sample",
    )

    assert events == [
        {"onset": 128, "label": "left", "duration": 0.0},
        {"onset": 256, "label": "right", "duration": 0.0},
    ]
