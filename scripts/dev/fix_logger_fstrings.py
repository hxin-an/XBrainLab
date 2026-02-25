"""Convert logger f-string calls to %-style lazy formatting.

Usage: python scripts/dev/fix_logger_fstrings.py [--dry-run]

Transforms:
    logger.info(f"Loading {path}")       →  logger.info("Loading %s", path)
    logger.error(f"Error: {e}", exc_info=True)  →  logger.error("Error: %s", e, exc_info=True)
    logger.debug(f"DEBUG: pattern='{p}', name='{n}'")  →  logger.debug("DEBUG: pattern='%s', name='%s'", p, n)
"""

import re
import sys
from pathlib import Path


def convert_fstring_to_percent(line: str) -> str:
    """Convert a single logger f-string call to %-style formatting."""
    # Match:  logger.LEVEL(f"...{expr}..."  with optional trailing args
    # We need to find the f-string and extract {expressions}
    pattern = r'(logger\.\w+\()f"((?:[^"\\]|\\.)*)(")'
    match = re.search(pattern, line)
    if not match:
        pattern = r"(logger\.\w+\()f'((?:[^'\\]|\\.)*)(')"
        match = re.search(pattern, line)
    if not match:
        return line

    prefix = match.group(1)  # e.g. "logger.info("
    fstring_body = match.group(2)  # e.g. "Loading {path}"
    _ = match.group(3)  # closing quote (unused, captured for regex structure)

    # Extract {expressions} from the f-string body
    exprs = []
    fmt_body = ""
    i = 0
    while i < len(fstring_body):
        if fstring_body[i] == "{":
            if i + 1 < len(fstring_body) and fstring_body[i + 1] == "{":
                # Escaped {{ -> {
                fmt_body += "{"
                i += 2
                continue
            # Find matching }
            depth = 1
            j = i + 1
            while j < len(fstring_body) and depth > 0:
                if fstring_body[j] == "{":
                    depth += 1
                elif fstring_body[j] == "}":
                    depth -= 1
                j += 1
            expr = fstring_body[i + 1 : j - 1]
            exprs.append(expr)
            fmt_body += "%s"
            i = j
        elif (
            fstring_body[i] == "}"
            and i + 1 < len(fstring_body)
            and fstring_body[i + 1] == "}"
        ):
            # Escaped }} -> }
            fmt_body += "}"
            i += 2
        else:
            fmt_body += fstring_body[i]
            i += 1

    if not exprs:
        # No expressions found, nothing to convert
        return line

    # Build the new call
    # Determine what comes after the closing quote in original
    after_match_start = match.end()
    rest = line[after_match_start:]

    # Build: logger.level("fmt_body", expr1, expr2, ...)REST
    new_args = ", ".join(exprs)
    new_line = line[: match.start()] + prefix + '"' + fmt_body + '", ' + new_args + rest

    return new_line


def process_file(filepath: Path, dry_run: bool = False) -> int:
    """Process a single Python file, returns count of changes."""
    text = filepath.read_text(encoding="utf-8")
    if "logger." not in text:
        return 0

    lines = text.split("\n")
    changes = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue

        # Check if line contains logger.xxx(f"
        if not re.search(r'logger\.\w+\(f["\']', line):
            continue

        new_line = convert_fstring_to_percent(line)
        if new_line != line:
            changes += 1
            if dry_run:
                print(f"  {filepath}:{i + 1}")
                print(f"    - {line.strip()}")
                print(f"    + {new_line.strip()}")
            lines[i] = new_line

    if changes > 0 and not dry_run:
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return changes


def main():
    dry_run = "--dry-run" in sys.argv
    total = 0

    for pyfile in sorted(Path("XBrainLab").rglob("*.py")):
        count = process_file(pyfile, dry_run)
        if count > 0:
            total += count
            if not dry_run:
                print(f"  {pyfile}: {count} conversions")

    print(f"\nTotal: {total} f-string logger calls converted")
    if dry_run:
        print("(dry-run mode, no files modified)")


if __name__ == "__main__":
    main()
