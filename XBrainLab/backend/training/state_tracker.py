"""Shared mutation tracking for background training read consistency."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from XBrainLab.backend.training_state_contract import TrainingStateToken


class TrainingStateTracker:
    """Expose a sequence token around nested training mutations.

    The generation is odd while one or more tracked mutations are active and
    even when the nested training state is stable.  All holders and records in
    one :class:`Trainer` share the same tracker, so a state snapshot can reject
    a read that overlaps a background update. Normal mutation markers do not
    hold the tracker lock while work runs; only a short compare-and-publish
    commit briefly serializes token readers.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._generation = 0
        self._active_mutations = 0

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Mark one exception-safe mutation interval."""
        with self._lock:
            if self._active_mutations == 0:
                self._generation += 1
            self._active_mutations += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_mutations -= 1
                if self._active_mutations == 0:
                    self._generation += 1

    def token(self) -> TrainingStateToken:
        """Return the current generation and whether no mutation is active."""
        with self._lock:
            return TrainingStateToken(
                generation=self._generation,
                stable=self._active_mutations == 0,
            )

    @contextmanager
    def mutation_if_current(self, expected_generation: int) -> Iterator[bool]:
        """Enter a short exclusive mutation only from the expected stable state."""
        self._lock.acquire()
        if self._active_mutations != 0 or self._generation != expected_generation:
            self._lock.release()
            yield False
            return

        self._generation += 1
        self._active_mutations += 1
        try:
            yield True
        finally:
            self._active_mutations -= 1
            self._generation += 1
            self._lock.release()
