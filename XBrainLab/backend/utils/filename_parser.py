"""Filename parsing utilities for extracting subject and session metadata."""

import os
import re

from XBrainLab.backend.utils.logger import logger


class FilenameParser:
    """Utility class for parsing subject and session metadata from filenames.

    Supports multiple strategies: split-based, regex, folder structure,
    fixed character positions, and named regex groups.
    """

    @staticmethod
    def parse_by_split(
        filename: str, separator: str, sub_idx: int, sess_idx: int
    ) -> tuple[str, str]:
        """Parse subject and session from a filename by splitting on a separator.

        Args:
            filename: The filename (with or without extension).
            separator: The character to split by (e.g., ``'_'``, ``'-'``).
            sub_idx: 1-based index of the subject part after splitting.
            sess_idx: 1-based index of the session part after splitting.

        Returns:
            A tuple of ``(subject, session)``, defaulting to ``('-', '-')``
            if indices are out of range.
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
        """Parse subject and session from a filename using a regular expression.

        Args:
            filename: The filename (with or without extension).
            pattern: The regex pattern string with capture groups.
            sub_group: 1-based group index for the subject.
            sess_group: 1-based group index for the session.

        Returns:
            A tuple of ``(subject, session)``, defaulting to ``('-', '-')``
            if the pattern does not match.
        """
        # Remove extension for easier parsing, similar to split method
        name_no_ext = os.path.splitext(filename)[0]

        sub = "-"
        sess = "-"

        try:
            regex = re.compile(pattern)
            match = regex.search(name_no_ext)
            logger.debug("DEBUG: pattern='%s', name='%s'", pattern, name_no_ext)
            if match:
                logger.debug("DEBUG: groups=%s", match.groups())
                if sub_group <= len(match.groups()):
                    sub = match.group(sub_group)
                if sess_group <= len(match.groups()):
                    sess = match.group(sess_group)
        except re.error as e:
            logger.debug("Failed to parse filename by regex: %s", e)
        return sub, sess

    @staticmethod
    def parse_by_folder(filepath: str) -> tuple[str, str]:
        """Parse subject and session from parent folder names.

        Assumes a directory structure like ``.../<Subject>/<Session>/filename``.
        If the immediate parent contains ``'ses'``, it is treated as session
        and the grandparent as subject.

        Args:
            filepath: Full file path.

        Returns:
            A tuple of ``(subject, session)``, defaulting to ``('-', '-')``
            if parsing fails.
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
        except (OSError, ValueError) as e:
            logger.debug("Failed to parse filename by folder: %s", e)
        return sub, sess

    @staticmethod
    def parse_by_fixed_position(
        filename: str, sub_start: int, sub_len: int, sess_start: int, sess_len: int
    ) -> tuple[str, str]:
        """Parse subject and session from fixed character positions in a filename.

        Args:
            filename: The filename (with or without extension).
            sub_start: 1-based start index for the subject substring.
            sub_len: Length of the subject substring.
            sess_start: 1-based start index for the session substring.
            sess_len: Length of the session substring.

        Returns:
            A tuple of ``(subject, session)``, defaulting to ``('-', '-')``
            if positions are out of range.
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
        except (IndexError, ValueError) as e:
            logger.debug("Failed to parse filename by fixed position: %s", e)
        return sub, sess

    @staticmethod
    def parse_by_named_regex(filename: str, pattern: str) -> tuple[str, str]:
        """Parse subject and session using named regex groups.

        Expects the pattern to define ``(?P<subject>...)`` and/or
        ``(?P<session>...)`` named groups.

        Args:
            filename: The filename (with or without extension).
            pattern: Regex pattern with named groups ``'subject'`` and ``'session'``.

        Returns:
            A tuple of ``(subject, session)``, defaulting to ``('-', '-')``
            if the pattern does not match.
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
        except re.error as e:
            logger.debug("Failed to parse filename by regex: %s", e)
        return sub, sess
