"""Shared mutation tracking for background training read consistency."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from XBrainLab.backend.training_state_contract import TrainingStateToken

_STABLE_READ_WAIT_SECONDS = 0.05


class TrainingStateTracker:
    """Expose a sequence token around nested training mutations.

    The generation is odd while one or more tracked mutations are active and
    even when the nested training state is stable.  All holders and records in
    one :class:`Trainer` share the same tracker, so a state snapshot can reject
    a read that overlaps a background update. Normal mutation markers do not
    hold the tracker lock while work runs. A stable read or short
    compare-and-publish commit briefly serializes new mutation markers.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stable = threading.Condition(self._lock)
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
                    self._stable.notify_all()

    def token(self) -> TrainingStateToken:
        """Return the current generation and whether no mutation is active."""
        with self._lock:
            return TrainingStateToken(
                generation=self._generation,
                stable=self._active_mutations == 0,
            )

    @contextmanager
    def stable_read(self) -> Iterator[None]:
        """Wait briefly for a short update, then keep one stable read still.

        A stable entry does not wait. A busy entry releases the tracker lock
        while waiting at most 50 ms for existing mutations to finish. If that
        budget expires, the caller still uses ordinary before/after tokens and
        must fail closed on any overlap; long work is never certified stable.
        """
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            yield
            return
        try:
            if not self._stable.wait_for(
                lambda: self._active_mutations == 0,
                timeout=_STABLE_READ_WAIT_SECONDS,
            ):
                acquired = False
                self._lock.release()
            yield
        finally:
            if acquired:
                self._lock.release()

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
            self._stable.notify_all()
            self._lock.release()
