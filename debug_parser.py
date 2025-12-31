from XBrainLab.utils.filename_parser import FilenameParser
import re

filename = "sub-01_ses-01_eeg.set"
pattern = r"sub-(\d+)_ses-(\d+)"
sub_idx = 1
sess_idx = 2

print(f"Testing with filename='{filename}', pattern='{pattern}'")
sub, sess = FilenameParser.parse_by_regex(filename, pattern, sub_idx, sess_idx)
print(f"Result: sub='{sub}', sess='{sess}'")
