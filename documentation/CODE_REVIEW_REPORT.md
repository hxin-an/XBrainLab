# XBrainLab Backend Code Review Report

**Reviewer**: Automated Senior Python Code Reviewer
**Scope**: All backend source files (~60 files) under `XBrainLab/backend/`
**Date**: 2026-02-08

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 7     |
| MEDIUM   | 10    |
| LOW      | 8     |
| **Total**| **27**|

**Files reviewed**: 60
**Files with issues**: 22

---

## CRITICAL

### C-1 · `export_saliency` — `UnboundLocalError` on unknown method

**File**: `XBrainLab/backend/training/record/eval.py` lines 148-163
**Category**: BUG

The `if/elif` chain has no `else` clause. If `method` is not one of the five known strings, `saliency` is never assigned and `torch.save(saliency, ...)` raises `UnboundLocalError` at runtime.

```python
def export_saliency(self, method: str, target_path: str) -> None:
    if method == "Gradient":
        saliency = self.gradient
    elif method == "Gradient * Input":
        saliency = self.gradient_input
    elif method == "SmoothGrad":
        saliency = self.smoothgrad
    elif method == "SmoothGrad_Squared":
        saliency = self.smoothgrad_sq
    elif method == "VarGrad":
        saliency = self.vargrad
    torch.save(saliency, target_path)   # <-- unbound if no branch matches
```

**Fix**: Add an `else` branch that raises `ValueError(f"Unknown saliency method: {method}")`.

---

### C-2 · `torch.load` without `weights_only=True` — arbitrary code execution

**File**: `XBrainLab/backend/training/model_holder.py` line 62
**Category**: SECURITY

`torch.load(self.pretrained_weight_path)` uses the default `weights_only=False`, which unpickles arbitrary Python objects. A crafted `.pt` file executes code on load. PyTorch ≥ 2.6 changes the default to `True`, but the current code is vulnerable on older versions.

```python
model.load_state_dict(torch.load(self.pretrained_weight_path))
```

The same pattern also appears in `eval.py` line 113, though that call explicitly passes `weights_only=False` — it still represents a risk for externally-shared eval files.

**Fix**: Use `torch.load(path, weights_only=True)` wherever only tensor state-dicts are expected. For `eval.py` where dicts of numpy arrays are saved, consider migrating to `np.savez` / `np.load`.

---

## HIGH

### H-1 · Z-score normalisation division by zero

**File**: `XBrainLab/backend/preprocessor/normalize.py` lines 44-57
**Category**: BUG

When a channel is constant (e.g., all zeros from a bad channel), `std == 0`. The z-score path divides by `std` without any epsilon, producing `NaN` / `inf` that silently corrupt all downstream computations. The `minmax` path correctly adds `1e-12`.

```python
# z-score path (raw)
preprocessed_data.get_mne()._data = (
    arrdata - np.multiply(arrdata.mean(axis=-1)[:, None], np.ones_like(arrdata))
) / np.multiply(arrdata.std(axis=-1)[:, None], np.ones_like(arrdata))
```

**Fix**: Add `+ 1e-12` (or `np.finfo(float).eps`) to the std denominator, consistent with the minmax path.

---

### H-2 · Timestamp mode creates annotations but never sets them before `events_from_annotations`

**File**: `XBrainLab/backend/load_data/event_loader.py` lines 200-230
**Category**: BUG

In timestamp mode, `mne.Annotations` is created and stored in `self.annotations`, but `self.raw.get_mne().set_annotations(self.annotations)` is only called later in `apply()`. The very next line calls `mne.events_from_annotations(self.raw.get_mne())`, which reads annotations *from the raw object* — but they haven't been set yet. The call will convert whatever pre-existing annotations the raw has (likely none or stim-channel events), not the user's labels.

```python
self.annotations = mne.Annotations(
    onset=onsets, duration=durations, description=descriptions
)
try:
    events, event_id = mne.events_from_annotations(
        self.raw.get_mne(), event_id=None   # reads annotations from raw
    )
```

**Fix**: Call `self.raw.get_mne().set_annotations(self.annotations)` before calling `mne.events_from_annotations`.

---

### H-3 · `set_seed` overflow when `seed is None`

**File**: `XBrainLab/backend/utils/seed.py` lines 27-29
**Category**: BUG

`torch.seed()` returns a 64-bit integer (up to 2^63 − 1). This value is then passed to `SeedSequence(seed)` (accepts any integer) and `random.seed(seed)` (accepts any integer), both of which are fine. However, `torch.manual_seed` is also fine with large ints. The real concern is that the function *returns* this potentially huge seed and callers may store/display it assuming it's a small integer. More importantly, the contract says `int | None` but torch.seed returns a Python int that exceeds 2^32 — this works in Python but may cause surprises when serialized to JSON (e.g., JavaScript `Number.MAX_SAFE_INTEGER` is 2^53).

**Severity downgrade note**: This is a latent correctness hazard rather than an immediate crash, but noted as HIGH because seed reproducibility may silently fail if the value is truncated during serialisation.

**Fix**: Mask to 32 bits: `seed = torch.seed() & 0xFFFF_FFFF` or use `seed = random.randint(0, 2**31 - 1)`.

---

### H-4 · Duplicate `XBrainLabError` exception hierarchies

**File**: `XBrainLab/backend/exceptions.py` + `XBrainLab/backend/utils/error_handler.py`
**Category**: BUG / API MISUSE

Two independent `XBrainLabError` base classes exist. Code that catches `error_handler.XBrainLabError` will **not** catch subclasses from `exceptions.XBrainLabError` (e.g., `FileCorruptedError`, `DataMismatchError`), and vice versa. The `handle_error` decorator re-wraps unexpected exceptions in `error_handler.XBrainLabError`, which is invisible to catch blocks using the other one.

**Fix**: Remove the duplicate in `error_handler.py` and import from `exceptions.py`, or merge the two modules.

---

### H-5 · Double "training_stopped" notification

**File**: `XBrainLab/backend/controller/training_controller.py` lines 103 + 146
**Category**: BUG / CONCURRENCY

When the user calls `stop_training()`, it immediately emits `notify("training_stopped")` (line 103). Then `_monitor_loop` (running in its daemon thread) also detects `is_training() == False` and emits `notify("training_stopped")` again (line 146). UI listeners may receive the event twice, causing duplicate state transitions or flickering.

```python
def stop_training(self):
    if self.is_training():
        self._study.stop_training()
        self.notify("training_stopped")  # First emission

def _monitor_loop(self):
    while not self._shutdown_event.is_set():
        if not self.is_training():
            self.notify("training_stopped")  # Second emission
            break
```

**Fix**: Remove the `notify` from `stop_training()` and let `_monitor_loop` be the sole emitter, or set a flag that prevents double notification.

---

### H-6 · `plt.clf()` / `plt.gcf()` global state — not thread-safe

**File**: `XBrainLab/backend/training/record/train.py` (multiple figure methods)
**Also**: `XBrainLab/backend/visualization/saliency_map.py`, `saliency_spectrogram_map.py`, `saliency_topomap.py`
**Category**: CONCURRENCY

All visualisation code calls `plt.subplot()`, `plt.imshow()`, `plt.gcf()`, etc. These operate on matplotlib's global current-figure state, which is not thread-safe. If multiple training groups or concurrent UI requests render simultaneously, figures can bleed into each other.

**Fix**: Use the object-oriented API (`fig, axes = plt.subplots(...)`) and pass `ax` explicitly. Return `fig` instead of `plt.gcf()`.

---

### H-7 · Direct access to `MNE._data` private attribute

**File**: `XBrainLab/backend/preprocessor/normalize.py` lines 43-81
**Category**: API MISUSE

`preprocessed_data.get_mne()._data` directly accesses MNE's private data buffer. This is fragile and may break on MNE updates. Additionally, `.load_data()` is called first but if the data is memory-mapped, `_data` modification may not propagate correctly depending on MNE's internal caching.

**Fix**: Use the public API `get_data()` / `Raw.__setitem__` or `apply_function()` for in-place transforms.

---

## MEDIUM

### M-1 · `get_training_repeat()` loop variable leak

**File**: `XBrainLab/backend/training/training_plan.py` lines 625-630
**Category**: BUG

```python
def get_training_repeat(self) -> int:
    for i in range(self.option.repeat_num):
        if not self.train_record_list[i].is_finished():
            break
    return i
```

If **all** records are finished, the `for` loop completes without hitting `break`, and `i` holds the last index (`repeat_num - 1`). The caller receives the *last* repeat index, which is misleadingly identical to "still training the last repeat" rather than "all done". If `repeat_num == 0`, `i` is unbound and raises `UnboundLocalError`.

**Fix**: Initialise `i = self.option.repeat_num - 1` before the loop or use an explicit sentinel / `for-else` construct.

---

### M-2 · Double deep-copy in preprocessing pipeline

**File**: `XBrainLab/backend/preprocessor/base.py` constructor + `XBrainLab/backend/controller/preprocess_controller.py` `_apply_processor`
**Category**: RESOURCE LEAK / PERFORMANCE

`PreprocessBase.__init__` deep-copies the data list, and `_apply_processor` also copies before passing to the constructor. For large EEG datasets this doubles memory overhead unnecessarily.

**Fix**: Copy in exactly one location (preferably the controller).

---

### M-3 · `get_averaged_record` does not average labels/outputs

**File**: `XBrainLab/backend/controller/visualization_controller.py`
**Category**: BUG

`get_averaged_record` averages only gradient dicts across runs but takes `label` and `output` from the first record only. If runs differ in data composition (e.g., different fold splits), the labels/output mismatch the averaged gradients.

**Fix**: Either assert all runs share identical labels/output, or compute pooled metrics properly.

---

### M-4 · Hardcoded input shape assumption in `get_model_summary_str`

**File**: `XBrainLab/backend/controller/evaluation_controller.py`
**Category**: BUG

```python
dummy_input = torch.zeros(1, 1, *X.shape[-2:])
```

This hardcodes the channel dimension to `1`, which is specific to EEGNet/SCCNet's `(batch, 1, channels, time)` convention. Any model expecting a different input layout will produce an incorrect or crashing summary.

**Fix**: Query the model's expected input shape from `model_holder` or `epoch_data.get_model_args()`.

---

### M-5 · `saliency_spectrogram_map.py` — mismatched `_get_plt` signature

**File**: `XBrainLab/backend/visualization/saliency_spectrogram_map.py` line 20
**Category**: BUG

`SaliencySpectrogramMapViz._get_plt(self, method)` takes only `method`, while `SaliencyMapViz._get_plt(self, method, absolute)` and `SaliencyTopoMapViz._get_plt(self, method, absolute)` accept an additional `absolute` parameter. If the caller passes `absolute` uniformly, the spectrogram visualiser will crash with `TypeError: _get_plt() got an unexpected keyword argument 'absolute'`.

**Fix**: Add `absolute: bool = False` parameter for interface consistency, even if unused.

---

### M-6 · `saliency_topomap.py` — noise injection for constant data

**File**: `XBrainLab/backend/visualization/saliency_topomap.py` lines 85-86
**Category**: BUG

```python
if np.std(data) < 1e-10:
    data += np.random.normal(0, 1e-10, data.shape)
```

Injecting random noise to prevent MNE warnings silently alters the visualisation. It also makes outputs non-deterministic. A better approach is to either display a uniform-colour plot or show a warning message.

**Fix**: Use a constant fallback colour with a "no variance" annotation, or suppress the specific MNE warning.

---

### M-7 · `saliency_3d_engine.py` — redundant loop guard

**File**: `XBrainLab/backend/visualization/saliency_3d_engine.py` lines 265-268
**Category**: DEAD CODE

```python
for ele in electrode:
    if ele not in electrode:   # Always False
        continue
```

`ele` is iterated from `electrode`, so `ele not in electrode` is always `False`. This guard does nothing.

**Fix**: Remove the dead `if` check.

---

### M-8 · `print()` instead of `logger` in `raw.py`

**File**: `XBrainLab/backend/load_data/raw.py`
**Category**: API MISUSE

`set_mne` uses `print()` to output a warning about event inconsistency. This bypasses the logging framework and is invisible to log aggregation.

**Fix**: Replace with `logger.warning(...)`.

---

### M-9 · `model_params_map` falsy-value filtering

**File**: `XBrainLab/backend/training/model_holder.py` lines 42-45
**Category**: BUG

```python
option_list = [
    f"{i}={self.model_params_map[i]}"
    for i in self.model_params_map
    if self.model_params_map[i]
]
```

The comprehension filter `if self.model_params_map[i]` silently drops parameters whose value is `0`, `0.0`, `False`, or `""` — all of which may be legitimate hyperparameter values (e.g., dropout=0).

**Fix**: Use `if self.model_params_map[i] is not None` or remove the filter entirely.

---

### M-10 · `channel_convex_hull` — unused `ConvexHull` import and dead comments

**File**: `XBrainLab/backend/visualization/saliency_3d_engine.py` lines 9, 36-52
**Category**: DEAD CODE

`ConvexHull` is imported (with `noqa: F401`) and many commented-out code blocks remain. The function only uses `pv.PolyData(...).delaunay_2d()`. The dead code and import add confusion.

**Fix**: Remove the `ConvexHull` import and dead comments.

---

## LOW

### L-1 · `sum()` on numpy boolean mask

**File**: `XBrainLab/backend/dataset/dataset.py` (multiple occurrences)
**Category**: PERFORMANCE

Python's built-in `sum()` on a numpy boolean array creates intermediate Python objects. Use `mask.sum()` or `np.sum(mask)` for vectorised performance.

---

### L-2 · `validate()` overwrites `reason` without short-circuiting

**File**: `XBrainLab/backend/training/option.py`
**Category**: NAMING/STYLE

The validation method checks multiple conditions and each failed condition overwrites `reason`. The first failure reason may be hidden if a later check also fails.

**Fix**: Return early on the first failure or collect all reasons into a list.

---

### L-3 · `np.multiply(x, np.ones_like(y))` is redundant broadcasting

**File**: `XBrainLab/backend/preprocessor/normalize.py` lines 44-80
**Category**: PERFORMANCE

Expressions like `np.multiply(arrdata.mean(axis=-1)[:, None], np.ones_like(arrdata))` manually broadcast by multiplying with ones. NumPy's broadcasting handles this natively: `arrdata.mean(axis=-1, keepdims=True)` is cleaner and more efficient.

---

### L-4 · `saliency_map.py` — tick off-by-one

**File**: `XBrainLab/backend/visualization/saliency_map.py` line 62
**Category**: BUG (cosmetic)

```python
ticks=np.linspace(0, saliency.shape[-1], 5),
labels=np.round(np.linspace(0, duration, 5), 2),
```

`np.linspace(0, saliency.shape[-1], 5)` includes `saliency.shape[-1]` as the last tick, which is one past the last valid pixel index. This may cause the rightmost tick label to be clipped.

---

### L-5 · `saliency_spectrogram_map.py` — tick offset heuristic

**File**: `XBrainLab/backend/visualization/saliency_spectrogram_map.py` lines 52-54
**Category**: BUG (cosmetic)

```python
ticks = np.linspace(0, saliency.shape[1], len(tick_label))
ticks = ticks - tick_inteval
```

Subtracting `tick_interval` from all tick positions is a hard-coded cosmetic offset that may misalign with actual spectrogram time bins, especially when `sfreq` varies.

---

### L-6 · `get_kappa` — potential division by zero

**File**: `XBrainLab/backend/training/record/eval.py` lines 201-208
**Category**: BUG

```python
return (p0 - pe) / (1 - pe)
```

If `pe == 1.0` (perfect agreement by chance, rare but possible with degenerate predictions), this divides by zero.

---

### L-7 · File download without checksum verification

**File**: `XBrainLab/backend/visualization/saliency_3d_engine.py` lines 90-95
**Category**: SECURITY

`ModelDownloadThread` downloads `.ply` files from GitHub and writes directly to disk. The only integrity check is `os.path.getsize(file_path) < 1024`. No hash/checksum verification is performed, leaving the application vulnerable to corrupted or tampered downloads.

---

### L-8 · Nondeterministic `SALIENCY_DOWNLOAD_THREADS` global set

**File**: `XBrainLab/backend/visualization/saliency_3d_engine.py` line 100
**Category**: CONCURRENCY

The module-level `SALIENCY_DOWNLOAD_THREADS = set()` is mutated from both the main thread (`.add()`) and a lambda connected to `QThread.finished` (`.discard()`). Python's GIL makes set operations atomic for CPython, but this is an implementation detail, not a language guarantee. A thread-safe collection or explicit lock would be more robust.

---

## Issues Not Flagged (Excluded per Instructions)

- Missing docstrings
- Import ordering
- Line length
- Stylistic / formatting preferences

---

## Recommendations (Non-Issue)

1. **Consolidate exception hierarchy**: Merge `exceptions.py` and `error_handler.py` into a single module.
2. **Adopt OOP matplotlib**: Replace all `plt.subplot/imshow/gcf` calls with `fig, ax = plt.subplots()` for thread safety and testability.
3. **Add `weights_only=True`** to all `torch.load` calls site-wide as a security hardening measure.
4. **Use MNE public API** for data access instead of `._data`.
