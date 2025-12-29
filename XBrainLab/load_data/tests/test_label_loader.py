import os
import numpy as np
import scipy.io
import pytest
from XBrainLab.load_data.label_loader import load_label_file

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
        
        data = {'labels': np.array([1, 2, 3])}
        scipy.io.savemat(str(p), data)
        
        labels = load_label_file(str(p))
        np.testing.assert_array_equal(labels, np.array([1, 2, 3]))

    def test_load_non_existent_file(self):
        with pytest.raises(FileNotFoundError):
            load_label_file("non_existent.txt")

    def test_load_unsupported_format(self, tmp_path):
        d = tmp_path / "labels"
        d.mkdir()
        p = d / "test.csv" # CSV not explicitly supported in current implementation
        p.write_text("1,2,3")
        
        with pytest.raises(ValueError, match="Unsupported file format"):
            load_label_file(str(p))
