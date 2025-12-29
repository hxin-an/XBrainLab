import pytest
from XBrainLab.utils.filename_parser import FilenameParser

class TestFilenameParser:
    
    def test_parse_by_split(self):
        # Case 1: Standard underscore
        fname = "sub-01_ses-02_task-rest.gdf"
        sub, sess = FilenameParser.parse_by_split(fname, '_', 1, 2)
        assert sub == "sub-01"
        assert sess == "ses-02"
        
        # Case 2: Out of bounds
        sub, sess = FilenameParser.parse_by_split(fname, '_', 10, 1)
        assert sub == "-"
        
        # Case 3: Different separator
        fname2 = "S01-Session1.set"
        sub, sess = FilenameParser.parse_by_split(fname2, '-', 1, 2)
        assert sub == "S01"
        assert sess == "Session1"

    def test_parse_by_regex(self):
        fname = "sub-01_ses-02.gdf"
        
        # Case 1: BIDS style
        pattern = r"sub-([^_]+)_ses-([^_]+)"
        sub, sess = FilenameParser.parse_by_regex(fname, pattern, 1, 2)
        assert sub == "01"
        assert sess == "02"
        
        # Case 2: No match
        sub, sess = FilenameParser.parse_by_regex("random_file.txt", pattern, 1, 2)
        assert sub == "-"
        assert sess == "-"

    def test_parse_by_folder(self):
        # Case 1: .../Subject/Session/file
        path1 = "/data/Subject01/Session02/data.gdf"
        sub, sess = FilenameParser.parse_by_folder(path1)
        # Note: Logic assumes 'ses' in folder name to distinguish session
        # If not present, it might treat parent as Subject.
        # Let's test the specific heuristic implemented:
        # if "ses" in parent -> parent is sess, grandparent is sub
        
        path2 = "/data/Subject01/ses-01/data.gdf"
        sub, sess = FilenameParser.parse_by_folder(path2)
        assert sub == "Subject01"
        assert sess == "ses-01"
        
        # Case 2: .../Subject/file (No session folder)
        path3 = "/data/Subject02/data.gdf"
        sub, sess = FilenameParser.parse_by_folder(path3)
        assert sub == "Subject02"
        assert sess == "-"

    def test_parse_by_fixed_position(self):
        fname = "S01T02.gdf" # S01 is sub, T02 is sess
        # S01: start 1, len 3
        # T02: start 4, len 3
        
        sub, sess = FilenameParser.parse_by_fixed_position(fname, 1, 3, 4, 3)
        assert sub == "S01"
        assert sess == "T02"
        
        # Case 2: Out of bounds
        sub, sess = FilenameParser.parse_by_fixed_position(fname, 10, 3, 1, 1)
        assert sub == "-"
