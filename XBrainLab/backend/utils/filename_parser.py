import os
import re

from XBrainLab.backend.utils.logger import logger


class FilenameParser:
    """
    Utility class for parsing metadata (Subject, Session) from filenames or paths.
    Supports multiple strategies: Split, Regex, Folder structure, and Fixed position.
    """

    @staticmethod
    def parse_by_split(
        filename: str, separator: str, sub_idx: int, sess_idx: int
    ) -> tuple[str, str]:
        """
        Parse filename by splitting with a separator.

        Args:
            filename: The filename (with or without extension).
            separator: The character to split by (e.g., '_', '-').
            sub_idx: 1-based index for Subject part.
            sess_idx: 1-based index for Session part.

        Returns:
            (subject, session) or ("-", "-") if not found.
        """
        name_no_ext = os.path.splitext(filename)[0]
        parts = name_no_ext.split(separator)

        sub = "-"
        sess = "-"

        # Convert 1-based index to 0-based
        s_i = sub_idx - 1
        se_i = sess_idx - 1

        if 0 <= s_i < len(parts):
            sub = parts[s_i]
        if 0 <= se_i < len(parts):
            sess = parts[se_i]

        return sub, sess

    @staticmethod
    def parse_by_regex(
        filename: str, pattern: str, sub_group: int, sess_group: int
    ) -> tuple[str, str]:
        """
        Parse filename using Regular Expression.

        Args:
            filename: The filename.
            pattern: The regex pattern string.
            sub_group: The group index for Subject.
            sess_group: The group index for Session.
        """
        # Remove extension for easier parsing, similar to split method
        name_no_ext = os.path.splitext(filename)[0]

        sub = "-"
        sess = "-"

        try:
            regex = re.compile(pattern)
            match = regex.search(name_no_ext)
            logger.debug(f"DEBUG: pattern='{pattern}', name='{name_no_ext}'")
            if match:
                logger.debug(f"DEBUG: groups={match.groups()}")
                if sub_group <= len(match.groups()):
                    sub = match.group(sub_group)
                if sess_group <= len(match.groups()):
                    sess = match.group(sess_group)
        except Exception:
            pass

        return sub, sess

    @staticmethod
    def parse_by_folder(filepath: str) -> tuple[str, str]:
        """
        Parse metadata from parent folder names.
        Assumes structure like: .../Subject/Session/filename.gdf
        """
        sub = "-"
        sess = "-"

        try:
            parent_dir = os.path.dirname(filepath)
            parent_name = os.path.basename(parent_dir)
            grandparent_dir = os.path.dirname(parent_dir)
            grandparent_name = os.path.basename(grandparent_dir)

            # Heuristic: if parent looks like a session (contains 'ses'),
            # use grandparent as Subject.
            if "ses" in parent_name.lower():
                sess = parent_name
                sub = grandparent_name
            else:
                # Otherwise assume parent is Subject, Session is unknown or same
                sub = parent_name
                sess = "-"
        except Exception:
            pass

        return sub, sess

    @staticmethod
    def parse_by_fixed_position(
        filename: str, sub_start: int, sub_len: int, sess_start: int, sess_len: int
    ) -> tuple[str, str]:
        """
        Parse filename by fixed character positions.

        Args:
            filename: The filename.
            sub_start: 1-based start index for Subject.
            sub_len: Length of Subject part.
            sess_start: 1-based start index for Session.
            sess_len: Length of Session part.
        """
        name_no_ext = os.path.splitext(filename)[0]
        sub = "-"
        sess = "-"

        try:
            # Subject (1-based -> 0-based)
            s_start = sub_start - 1
            if s_start >= 0 and s_start < len(name_no_ext):
                extracted = name_no_ext[s_start : s_start + sub_len]
                if extracted:
                    sub = extracted

            # Session (1-based -> 0-based)
            se_start = sess_start - 1
            if se_start >= 0 and se_start < len(name_no_ext):
                extracted = name_no_ext[se_start : se_start + sess_len]
                if extracted:
                    sess = extracted
        except Exception:
            pass

        return sub, sess

    @staticmethod
    def parse_by_named_regex(filename: str, pattern: str) -> tuple[str, str]:
        """
        Parse filename using Named Regular Expression (e.g. (?P<subject>...)).

        Args:
            filename: The filename.
            pattern: The regex pattern string with named groups 'subject' and 'session'.

        Returns:
            (subject, session) or ("-", "-") if not found.
        """
        # Remove extension for easier parsing
        name_no_ext = os.path.splitext(filename)[0]

        sub = "-"
        sess = "-"

        try:
            regex = re.compile(pattern)
            match = regex.match(filename)
            # Try matching full filename first, if not, try name without extension
            if not match:
                match = regex.match(name_no_ext)

            if match:
                groupdict = match.groupdict()
                if "subject" in groupdict:
                    sub = groupdict["subject"]
                if "session" in groupdict:
                    sess = groupdict["session"]
        except Exception:
            pass

        return sub, sess
