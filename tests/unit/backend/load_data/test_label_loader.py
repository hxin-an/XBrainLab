from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import scipy.io

from XBrainLab.backend.load_data.label_loader import load_label_file


class TestLabelLoader:
    def test_load_txt_success(self, tmp_path):
        # Create a dummy txt file
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "test.txt"
        p.write_text("1 2 3\n4 5")

        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, np.array([1, 2, 3, 4, 5]))

    def test_load_txt_with_garbage(self, tmp_path):
        # Test robustness against non-integer values
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "garbage.txt"
        p.write_text("1 2 a b 3")

        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, np.array([1, 2, 3]))

    def test_load_mat_success(self, tmp_path):
        # Create a dummy mat file
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "test.mat"

        data = {"labels": np.array([1, 2, 3])}
        scipy.io.savemat(str(p), data)

        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, np.array([1, 2, 3]))

    def test_load_non_existent_file(self):
        with pytest.raises(FileNotFoundError):
            load_label_file("non_existent.txt")

    def test_load_unsupported_format(self, tmp_path):
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "test.xyz"
        p.write_text("1,2,3")

        with pytest.raises(ValueError, match=r"Unsupported file format"):
            load_label_file(str(p))

    def test_load_csv_success(self, tmp_path):
        """Test CSV loading with mocked pandas."""
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "test.csv"
        p.write_text("label\n1\n2\n3")

        # Mock pandas
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_df.columns = ["label"]
        mock_df.__getitem__.return_value.values = np.array([1, 2, 3])
        # iterrows for timestamp check (not used if timestamp cols missing)
        # But _load_csv_tsv checks columns first.

        mock_pd.read_csv.return_value = mock_df

        with patch.dict("sys.modules", {"pandas": mock_pd}):
            labels = load_label_file(str(p))
            np.testing.assert_array_equal(labels, np.array([1, 2, 3]))
