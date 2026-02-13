# Sitecustomize: Patch PyTorch docstring registration before coverage.py loads
#
# This file is loaded by Python at startup (before any imports) when placed in site-packages
# or when PYTHONPATH includes this directory. It patches torch's _add_docstr to be idempotent,
# preventing the "already has a docstring" error during coverage tracing.
#
# Usage: Set PYTHONPATH=tests/fixtures before running pytest with --cov

import sys

_original_import = (
    __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
)

_patched_add_docstr = False


def _patched_import(name, *args, **kwargs):
    global _patched_add_docstr  # noqa: PLW0603
    module = _original_import(name, *args, **kwargs)

    # Patch torch._C._add_docstr after torch._C is imported
    if name == "torch._C" and not _patched_add_docstr:
        _patched_add_docstr = True
        try:
            _C = module
            original_add_docstr = _C._add_docstr
            _seen = set()

            def idempotent_add_docstr(func, docstr):
                fid = id(func)
                if fid in _seen:
                    return func
                _seen.add(fid)
                return original_add_docstr(func, docstr)

            _C._add_docstr = idempotent_add_docstr
        except Exception:
            pass

    return module


# Only patch if coverage is going to run (check for coverage process or flag)
import os

if (
    os.environ.get("COVERAGE_PROCESS_START")
    or "--cov" in sys.argv
    or "coverage" in " ".join(sys.argv)
):
    try:
        import builtins

        builtins.__import__ = _patched_import
    except Exception:
        pass
