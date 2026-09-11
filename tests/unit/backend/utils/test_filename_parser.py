from XBrainLab.backend.utils.filename_parser import FilenameParser


class TestFilenameParser:
    def test_parse_by_split(self):
        filename = "Sub01_Ses02_Task.gdf"

        # Test standard case
        sub, sess = FilenameParser.parse_by_split(filename, "_", 1, 2)
        assert sub == "Sub01"
        assert sess == "Ses02"

        # Test out of bounds
        sub, sess = FilenameParser.parse_by_split(filename, "_", 10, 11)
        assert sub == "-"
        assert sess == "-"

        # Test different separator
        filename_hyphen = "Sub01-Ses02.gdf"
        sub, sess = FilenameParser.parse_by_split(filename_hyphen, "-", 1, 2)
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
        filepath = "/data/Subject01/Session02/data.gdf"

        sub, sess = FilenameParser.parse_by_folder(filepath)
        assert sub == "Subject01"
        assert sess == "Session02"

        filepath_simple = "/data/Subject01/data.gdf"
        sub, sess = FilenameParser.parse_by_folder(filepath_simple)
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

    def test_parse_by_regex_handles_invalid_and_missing_numeric_groups(self):
        invalid = FilenameParser.parse_by_regex("sub-01.gdf", "(", 1, 2)
        missing = FilenameParser.parse_by_regex("sub-01.gdf", r"sub-(\d+)", 1, 2)

        assert invalid == ("-", "-")
        assert missing == ("01", "-")

    def test_parse_by_named_regex_handles_partial_and_no_match(self):
        partial = FilenameParser.parse_by_named_regex(
            "sub-01.gdf", r"sub-(?P<subject>\d+)"
        )
        no_match = FilenameParser.parse_by_named_regex(
            "recording.gdf", r"sub-(?P<subject>\d+)_ses-(?P<session>\d+)"
        )

        assert partial == ("01", "-")
        assert no_match == ("-", "-")
