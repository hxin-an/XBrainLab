"""LLM backend implementations.

Backends are imported lazily to avoid triggering heavy dependencies
(e.g. ``torch`` in ``LocalBackend``) at package import time.  Import
specific backends directly from their modules.
"""

# Expose nothing eagerly to avoid triggering heavy imports (like torch in LocalBackend)
# Users should import specific backends directly from their modules.
