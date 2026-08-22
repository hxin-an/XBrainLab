"""Hemisphere-aware channel helpers adapted from Braindecode 1.6.1."""

import re


def match_hemisphere_chans(
    left_chs: list[str], right_chs: list[str]
) -> list[tuple[str, str]]:
    """Pair odd-numbered left channels with matching right channels."""
    if len(left_chs) != len(right_chs):
        raise ValueError("Left and right channels do not match.")
    remaining_right = list(right_chs)
    matched = []
    for left in left_chs:
        match = re.search(r"\d+", left)
        if match is None:
            raise ValueError(f"Channel '{left}' does not contain a number.")
        target = re.sub(r"\d+", str(1 + int(match.group())), left)
        for right in remaining_right:
            if right == target:
                matched.append((left, right))
                remaining_right.remove(right)
                break
        else:
            raise ValueError(
                f"Found no right hemisphere matching channel for '{left}'."
            )
    return matched


def division_channels_idx(
    ch_names: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Split channels into left, right, and midline name lists."""
    left: list[str] = []
    right: list[str] = []
    middle: list[str] = []
    for channel in ch_names:
        number = re.search(r"\d+", channel)
        if number is None:
            middle.append(channel)
        elif int(number[0]) % 2:
            left.append(channel)
        else:
            right.append(channel)
    return left, right, middle
