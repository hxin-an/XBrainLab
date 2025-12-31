
import pytest
from XBrainLab.utils.filename_parser import FilenameParser
import os

class TestFilenameParser:
    
    def test_parse_by_split(self):
        filename = "Sub01_Ses02_Task.gdf"
        
        # Test standard case
        sub, sess = FilenameParser.parse_by_split(filename, '_', 1, 2)
        assert sub == "Sub01"
        assert sess == "Ses02"
        
        # Test out of bounds
        sub, sess = FilenameParser.parse_by_split(filename, '_', 10, 11)
        assert sub == "-"
        assert sess == "-"
        
        # Test different separator
        filename_hyphen = "Sub01-Ses02.gdf"
        sub, sess = FilenameParser.parse_by_split(filename_hyphen, '-', 1, 2)
        assert sub == "Sub01"
        assert sess == "Ses02"

    def test_parse_by_regex(self):
        filename = "sub-01_ses-02_task-rest.gdf"
        
        # Test BIDS style
        pattern = r"sub-([^_]+)_ses-([^_]+)"
        sub, sess = FilenameParser.parse_by_regex(filename, pattern, 1, 2)
        assert sub == "01"
        assert sess == "02"
        
        # Test no match
        sub, sess = FilenameParser.parse_by_regex("nomatch.gdf", pattern, 1, 2)
        assert sub == "-"
        assert sess == "-"

    def test_parse_by_folder(self):
        # Mock path
        filepath = "/data/Subject01/Session02/data.gdf"
        
        # Note: parse_by_folder uses os.path.dirname, so we need full paths or at least relative dirs
        sub, sess = FilenameParser.parse_by_folder(filepath)
        # Logic: parent=Session02 (contains 'ses'?), grandparent=Subject01
        # 'Session02' doesn't contain 'ses' (case sensitive? code says .lower())
        # "Session02".lower() -> "session02" -> contains "ses" -> True
        assert sub == "Subject01"
        assert sess == "Session02"
        
        # Test simple parent
        filepath_simple = "/data/Subject01/data.gdf"
        sub, sess = FilenameParser.parse_by_folder(filepath_simple)
        # parent=Subject01 (no 'ses') -> sub=Subject01, sess=-
        assert sub == "Subject01"
        assert sess == "-"

    def test_parse_by_fixed_position(self):
        filename = "A01T.gdf"
        # Sub: A01 (start 1, len 3), Sess: T (start 4, len 1)
        sub, sess = FilenameParser.parse_by_fixed_position(filename, 1, 3, 4, 1)
        assert sub == "A01"
        assert sess == "T"
        
        # Test out of bounds
        sub, sess = FilenameParser.parse_by_fixed_position(filename, 10, 3, 20, 1)
        assert sub == "-"
        assert sess == "-"
