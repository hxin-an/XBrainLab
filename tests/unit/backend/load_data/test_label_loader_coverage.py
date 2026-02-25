"""Extended tests for label_loader covering _load_mat, _load_csv_tsv edge cases.

Covers: mat shapes (n,1), (1,n), (n,3), 2D non-standard, 3D+,
csv/tsv timestamp mode, sequence mode, single-column, multi-column guess.
"""

import numpy as np
import pytest
import scipy.io

from XBrainLab.backend.load_data.label_loader import load_label_file

# ---------------------------------------------------------------------------
# .mat file edge cases
# ---------------------------------------------------------------------------


class TestLoadMat:
    def test_mat_n_by_1(self, tmp_path):
        """(n, 1) shape should flatten to 1D."""
        p = tmp_path / "labels.mat"
        scipy.io.savemat(str(p), {"y": np.array([[1], [2], [3]])})
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [1, 2, 3])

    def test_mat_1_by_n(self, tmp_path):
        """(1, n) shape should flatten to 1D."""
        p = tmp_path / "labels.mat"
        scipy.io.savemat(str(p), {"y": np.array([[4, 5, 6]])})
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [4, 5, 6])

    def test_mat_n_by_3_mne_format(self, tmp_path):
        """(n, 3) MNE event format -> return last column."""
        p = tmp_path / "labels.mat"
        events = np.array([[0, 0, 1], [100, 0, 2], [200, 0, 3]])
        scipy.io.savemat(str(p), {"events": events})
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [1, 2, 3])

    def test_mat_2d_non_standard(self, tmp_path):
        """Non-standard 2D shape should flatten."""
        p = tmp_path / "labels.mat"
        data = np.array([[1, 2], [3, 4], [5, 6]])  # (3, 2)
        scipy.io.savemat(str(p), {"x": data})
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [1, 2, 3, 4, 5, 6])

    def test_mat_1d(self, tmp_path):
        """Standard 1D array."""
        p = tmp_path / "labels.mat"
        scipy.io.savemat(str(p), {"y": np.array([10, 20, 30])})
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [10, 20, 30])

    def test_mat_no_variables(self, tmp_path):
        """Mat file with only metadata should raise ValueError."""
        p = tmp_path / "empty.mat"
        # savemat always adds __header__, etc. We save empty dict
        scipy.io.savemat(str(p), {})
        with pytest.raises(ValueError, match="No variables"):
            load_label_file(str(p))

    def test_mat_3d_flatten(self, tmp_path):
        """3D+ arrays should flatten."""
        p = tmp_path / "labels.mat"
        data = np.arange(24).reshape(2, 3, 4)
        scipy.io.savemat(str(p), {"x": data})
        labels = load_label_file(str(p))
        assert len(labels) == 24


# ---------------------------------------------------------------------------
# .csv / .tsv files
# ---------------------------------------------------------------------------


class TestLoadCsvTsv:
    def test_csv_timestamp_mode(self, tmp_path):
        """CSV with onset + label columns -> list of dicts."""
        p = tmp_path / "events.csv"
        p.write_text("onset,label,duration\n1.0,EventA,0.5\n2.0,EventB,0.8\n")
        result = load_label_file(str(p))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["onset"] == 1.0
        assert result[0]["label"] == "EventA"
        assert result[0]["duration"] == 0.5

    def test_csv_timestamp_mode_time_column(self, tmp_path):
        """CSV with 'time' column (alternative to 'onset')."""
        p = tmp_path / "events.csv"
        p.write_text("time,trial_type\n0.5,Left\n1.5,Right\n")
        result = load_label_file(str(p))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["onset"] == 0.5
        assert result[0]["label"] == "Left"
        assert result[0]["duration"] == 0.0  # no duration column

    def test_csv_sequence_mode_label_column(self, tmp_path):
        """CSV with only 'label' column (no time) -> sequence mode."""
        p = tmp_path / "labels.csv"
        p.write_text("label\n1\n2\n3\n")
        result = load_label_file(str(p))
        np.testing.assert_array_equal(result, [1, 2, 3])

    def test_csv_sequence_mode_single_column(self, tmp_path):
        """CSV with single column no header match -> first column."""
        p = tmp_path / "labels.csv"
        p.write_text("values\n10\n20\n30\n")
        result = load_label_file(str(p))
        np.testing.assert_array_equal(result, [10, 20, 30])

    def test_csv_sequence_mode_multi_column_guess(self, tmp_path):
        """CSV with multiple columns, no standard names -> first column."""
        p = tmp_path / "data.csv"
        p.write_text("col_a,col_b\n1,100\n2,200\n3,300\n")
        result = load_label_file(str(p))
        np.testing.assert_array_equal(result, [1, 2, 3])

    def test_tsv_file(self, tmp_path):
        """TSV file should use tab separator."""
        p = tmp_path / "labels.tsv"
        p.write_text("label\n5\n6\n7\n")
        result = load_label_file(str(p))
        np.testing.assert_array_equal(result, [5, 6, 7])

    def test_tsv_timestamp_mode(self, tmp_path):
        """TSV with latency + type columns."""
        p = tmp_path / "events.tsv"
        p.write_text("latency\ttype\n0.1\tA\n0.2\tB\n")
        result = load_label_file(str(p))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["onset"] == 0.1
        assert result[0]["label"] == "A"


# ---------------------------------------------------------------------------
# .txt edge cases
# ---------------------------------------------------------------------------


class TestLoadTxt:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        labels = load_label_file(str(p))
        assert len(labels) == 0

    def test_multiline(self, tmp_path):
        p = tmp_path / "multi.txt"
        p.write_text("1\n2\n3\n4 5\n")
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, [1, 2, 3, 4, 5])
