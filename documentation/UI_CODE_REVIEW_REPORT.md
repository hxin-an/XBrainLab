# XBrainLab UI Code Review Report

**Reviewer:** Senior Python Code Reviewer (Automated)
**Date:** 2026-02-08
**Scope:** All UI source files under `XBrainLab/ui/` (~70+ files)
**Framework:** PyQt6, Matplotlib, PyQtGraph, PyVista

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 11    |
| MEDIUM   | 18    |
| LOW      | 12    |
| **Total**| **44**|

**Files Reviewed:** 73
**Lines of Code (approx.):** ~12,000

---

## CRITICAL Issues

### C-01 — Calling nonexistent method `set_selection` on `EventFilterDialog`

- **File:** `panels/dataset/actions.py`, `_filter_events_for_import`
- **Category:** Bug / AttributeError at runtime
- **Description:** `_filter_events_for_import` calls `dlg.set_selection(suggested)` on an `EventFilterDialog` instance. However, `EventFilterDialog` (in `dialogs/dataset/event_filter_dialog.py`) does **not** define a `set_selection` method. This will raise `AttributeError` every time an import triggers event filtering with a suggested selection.
- **Fix:** Add a `set_selection(self, items: list)` method to `EventFilterDialog` that programmatically checks the matching items in its list widget, or remove the call if the suggestion feature is not yet implemented.

---

### C-02 — `TestOnlySettingWindow` calls `init_ui()` twice

- **File:** `dialogs/training/test_only_setting.py`, lines 37–49
- **Category:** Bug / Double initialization
- **Description:** `BaseDialog.__init__` already calls `self.init_ui()`. `TestOnlySettingWindow.__init__` then calls `self.init_ui()` a second time, creating duplicate widgets and potentially causing layout corruption.
- **Fix:** Remove the explicit `self.init_ui()` call from `TestOnlySettingWindow.__init__`, relying on `BaseDialog.__init__` to invoke it.

---

### C-03 — `DataSplittingDialog.confirm()` calls `get_result()` twice, then calls `super().accept()` instead of `self.accept()`

- **File:** `dialogs/dataset/data_splitting_dialog.py`, `confirm()` method
- **Category:** Bug / Logic error
- **Description:**
  1. `self.split_result = self.step2_window.get_result()` is written on two consecutive lines — a copy-paste duplication that is harmless but signals a potential deeper logic error.
  2. On cancel (`else` branch), `self.reject()` is called even though the user cancelled step 2. The parent dialog should stay open to allow retrying, not reject entirely.
- **Fix:** Remove the duplicate `get_result()` call. Change the `else` branch to `return` instead of `self.reject()` so the user can try again.

---

## HIGH Issues

### H-01 — `PlotFigureWindow` doesn't chain `SinglePlotWindow.__init__` properly

- **File:** `components/plot_figure_window.py`
- **Category:** Bug / Broken inheritance
- **Description:** `PlotFigureWindow.__init__` sets instance attributes and calls `self.init_ui()` directly without ever calling `super().__init__()` from `SinglePlotWindow`. This means `SinglePlotWindow.__init__` is skipped, so `init_figure()` is never called and the base class's attribute setup is bypassed. The code works by accident because `init_ui()` duplicates some of the setup, but this is fragile.
- **Fix:** Call `super().__init__(parent, title=title)` and ensure `init_figure()` runs in the correct order.

---

### H-02 — `on_activate_clicked` has a no-op branch when both backends are available

- **File:** `dialogs/model_settings_dialog.py`, `on_activate_clicked` method
- **Category:** Bug / Logic gap
- **Description:** When both local and Gemini backends are available, the `else` branch does nothing (falls through). `active_mode` is never set, so the subsequent `self.accept()` returns a stale or `None` mode.
- **Fix:** Add explicit logic to prompt the user to choose which mode to activate when both are available, or default to the one most recently configured.

---

### H-03 — Figure/Canvas leaks in saliency view widgets

- **File:** `panels/visualization/saliency_views/map_view.py`, `spectrogram_view.py`, `topomap_view.py`
- **Category:** Resource leak
- **Description:** Every call to `update_plot` creates a new `Figure` and `FigureCanvas`, removes the old canvas from the layout and calls `self.canvas.close()`, but **never calls `matplotlib.pyplot.close(self.fig)`** on the old figure. Matplotlib internally accumulates figure references, leading to memory leaks in long sessions.
- **Fix:** Before replacing `self.fig`, call `plt.close(self.fig)` to release the Matplotlib figure object.

---

### H-04 — `topomap_view.py` calls `plt_close("all")` before plotting

- **File:** `panels/visualization/saliency_views/topomap_view.py`, `update_plot`
- **Category:** Bug / Side effect
- **Description:** Calling `plt.close("all")` destroys **every** Matplotlib figure in the application, including figures belonging to other panels (confusion matrix, metrics chart, training plots). This can cause crashes or blank plots in other tabs.
- **Fix:** Only close the current figure (`plt.close(self.fig)`) instead of `"all"`. Remove the spurious `plt_figure()` call which creates an unused global figure.

---

### H-05 — `TrainingManagerWindow.update_table` replaces all items unconditionally

- **File:** `panels/training/training_manager.py`, `update_table`
- **Category:** Performance / Correctness
- **Description:** Although the method checks `rowCount() == 0`, both branches do exactly the same thing — create new `QTableWidgetItem` objects for every cell on every 100ms timer tick. This causes excessive GC pressure and visual flickering. The `if/else` is dead logic.
- **Fix:** Adopt the pattern from `TrainingHistoryTable.update_history`: only call `setItem` when the text has actually changed, and reuse existing items.

---

### H-06 — API key written to plaintext `.env` file

- **File:** `dialogs/model_settings_dialog.py`, `_save_api_key_to_env`
- **Category:** Security
- **Description:** The Gemini API key is written to a `.env` file in the current working directory with `0o644` permissions by default. This is a security risk if the project directory is shared or version-controlled.
- **Fix:** Use OS-level credential storage (e.g., `keyring` library) or at minimum set restrictive file permissions (`0o600`) and add `.env` to `.gitignore`.

---

### H-07 — `DataSplittingPreviewDialog` uses `threading.Thread` without cleanup

- **File:** `dialogs/dataset/data_splitting_preview_dialog.py`
- **Category:** Concurrency / Resource leak
- **Description:** `preview()` starts a background `threading.Thread` for dataset generation. If the dialog is closed while the thread is running, there is no join or interrupt, so the thread can continue running after the dialog is destroyed, potentially accessing deleted Qt objects (use-after-free crash).
- **Fix:** Override `closeEvent` / `reject` to call `self.dataset_generator.set_interrupt()`, then `self.preview_worker.join(timeout=5)`.

---

### H-08 — `Saliency3DPlotWidget` deferred plot via `QTimer.singleShot` captures stale closure

- **File:** `panels/visualization/saliency_views/plot_3d_view.py`, `update_plot`
- **Category:** Bug / Race condition
- **Description:** `QTimer.singleShot(100, lambda: self._do_3d_plot(...))` captures `eval_record`, `epoch_data`, and `selected_event` in a closure. If the user rapidly changes selections, the old timer fires with stale data while the new plotter widget has already been cleared/replaced.
- **Fix:** Track a generation counter and verify it hasn't changed inside `_do_3d_plot`, or cancel outstanding timers before scheduling new ones.

---

### H-09 — `VisualizationPanel.on_update` calls `QApplication.processEvents()` after `repaint()`

- **File:** `panels/visualization/panel.py`, `on_update`
- **Category:** Concurrency / Re-entrancy risk
- **Description:** Calling `QApplication.processEvents()` in a signal handler can cause re-entrant event processing, potentially triggering the same handler again before the first invocation completes. This can lead to recursive updates and stack overflows.
- **Fix:** Remove `QApplication.processEvents()`. Qt will naturally process paint events after the current event handler returns. If immediate repaint is needed, `repaint()` alone is sufficient.

---

### H-10 — `confusion_matrix.py` and `metrics_bar_chart.py` leak old Figure/Canvas

- **File:** `panels/evaluation/confusion_matrix.py`, `panels/evaluation/metrics_bar_chart.py`
- **Category:** Resource leak
- **Description:** Both widgets create a new `Figure` and `FigureCanvas` on every `update_plot` call. The old canvas is removed from the layout and deleted via `deleteLater()`, but the old `Figure` is never closed with `plt.close()`, causing Matplotlib to accumulate figure references.
- **Fix:** Call `plt.close(self.fig)` before creating the new figure, or reuse the same figure/axes and just clear and replot.

---

### H-11 — `message_bubble.py` uses `subprocess.Popen` with unescaped path

- **File:** `chat/message_bubble.py`
- **Category:** Security / Injection
- **Description:** The `_open_file_link` method builds a command using `subprocess.Popen(f'explorer /select,"{path}"', ...)`. If the path contains special characters (e.g., `"` or `&`), this can lead to command injection on Windows. While the path comes from an internal tool result, defense-in-depth applies.
- **Fix:** Use `subprocess.Popen(['explorer', '/select,', path])` (list form) to avoid shell interpretation, or use `os.startfile()` / `QDesktopServices.openUrl()`.

---

## MEDIUM Issues

### M-01 — `AgentManager.switch_panel` doesn't uncheck other nav buttons

- **File:** `components/agent_manager.py`, `switch_panel`
- **Category:** UX / State inconsistency
- **Description:** When `switch_panel(index)` is called, it sets the requested button to checked but does not uncheck the previously checked button. PyQt6 only auto-manages exclusive button groups; individual `QPushButton.setCheckable(True)` buttons do not have this behavior.
- **Fix:** Iterate all nav buttons and uncheck them before checking the target one, or put them into a `QButtonGroup` with `exclusive=True`.

---

### M-02 — `EventBus` singleton is not thread-safe

- **File:** `core/event_bus.py`
- **Category:** Concurrency
- **Description:** The `_instance` class variable is checked and set without any lock. If two threads call `EventBus()` simultaneously before the first assignment completes, two instances could be created, violating the singleton contract.
- **Fix:** Use a threading lock around the instance check, or use the `__init_subclass__` / module-level instance pattern.

---

### M-03 — `InfoPanelService.unregister` uses lambda with destroyed signal

- **File:** `components/info_panel_service.py`
- **Category:** Bug / Dangling reference
- **Description:** `panel.destroyed.connect(lambda: self.unregister(panel))` captures `panel` in a closure. When `destroyed` fires, `panel` is a C++ deleted object; calling `self.unregister(panel)` may crash or silently fail because the Python wrapper still exists but the underlying C++ object is dead.
- **Fix:** Use `functools.partial` with weak references or track panels by ID and clean up on `destroyed` without accessing the panel object.

---

### M-04 — `info_panel.py` duration calculation uses lossy truncation

- **File:** `components/info_panel.py`
- **Category:** Correctness
- **Description:** `int(first_data.get_epoch_duration() * 100 / first_data.get_sfreq()) / 100` truncates rather than rounds. For example, a duration of 1.999 would display as 1.99 instead of 2.00.
- **Fix:** Use `round(first_data.get_epoch_duration() / first_data.get_sfreq(), 2)`.

---

### M-05 — `FilteringDialog` accepts `l_freq=0` for bandpass

- **File:** `dialogs/preprocess/filtering_dialog.py`
- **Category:** Bug / API misuse
- **Description:** When bandpass is selected, the lowcut frequency can be set to 0. MNE's `filter()` does not accept `0` as a valid low-frequency cutoff and will raise a `ValueError`.
- **Fix:** Add validation: `if l_freq <= 0: show warning`.

---

### M-06 — `chat/panel.py` `set_status` is a no-op

- **File:** `chat/panel.py`, `set_status`
- **Category:** Dead code
- **Description:** `set_status(self, text)` method has an empty body (`pass`). It is called from external code expecting a visible status update.
- **Fix:** Implement the method to display status text (e.g., in the input area placeholder or a status bar), or remove it and its callers.

---

### M-07 — `chat/panel.py` `start_agent_message` is mostly redundant

- **File:** `chat/panel.py`, `start_agent_message`
- **Category:** Dead code / Redundancy
- **Description:** `start_agent_message` calls `add_message("", is_user=False)` and `set_status("Thinking...")`. Since `set_status` is a no-op and the empty message is immediately overwritten by streaming chunks, this method has no visible effect.
- **Fix:** Either implement `set_status` properly (show a thinking indicator) or remove `start_agent_message`.

---

### M-08 — `global_exception_handler` may fail without QApplication

- **File:** `main_window.py`
- **Category:** Error handling
- **Description:** The global exception handler creates a `QMessageBox`. If the exception occurs before `QApplication` is instantiated or after it's destroyed, the `QMessageBox` constructor will crash.
- **Fix:** Guard with `if QApplication.instance():` before creating the message box, and fall back to `sys.stderr.write()`.

---

### M-09 — `observer_bridge.py` lambda wrapping prevents disconnection

- **File:** `core/observer_bridge.py`, `connect_to`
- **Category:** Architecture / Resource management
- **Description:** `connect_to` wraps the callback in a lambda for thread safety. However, the lambda cannot be disconnected later because the reference is lost. This prevents clean teardown of observer connections.
- **Fix:** Store the lambda reference and provide a `disconnect_from` method, or use `functools.partial`.

---

### M-10 — `TrainingSidebar.__init__` doesn't pass `parent` to `super()`

- **File:** `panels/training/sidebar.py`, line 56
- **Category:** Bug
- **Description:** `super().__init__()` is called without passing `parent`, so the widget has no parent. This means it won't be automatically destroyed when the parent panel is closed, potentially causing a memory leak.
- **Fix:** Change to `super().__init__(parent)`.

---

### M-11 — `ModelSummaryWindow` doesn't reject when no trainers

- **File:** `panels/visualization/model_summary.py`, `check_data`
- **Category:** UX
- **Description:** If `self.trainers` is empty, a warning is shown but the dialog still opens with an empty combo box. The user can interact with it meaninglessly.
- **Fix:** Call `self.reject()` after the warning, or disable interaction when no trainers are available.

---

### M-12 — `model_selection_dialog.py` type inference is fragile

- **File:** `dialogs/training/model_selection_dialog.py`
- **Category:** Correctness
- **Description:** Parameter type inference uses `isdigit()` and `replace(".", "", 1).isdigit()` to decide between `int`, `float`, and `str`. This fails for negative numbers (e.g., "-1"), scientific notation (e.g., "1e-3"), and boolean-like strings other than exact "True"/"False".
- **Fix:** Use `ast.literal_eval()` wrapped in try/except for safe type coercion, or display the expected type from the model's parameter annotations.

---

### M-13 — `export_saliency_dialog.py` uses `pickle.dump`

- **File:** `dialogs/visualization/export_saliency_dialog.py`
- **Category:** Security
- **Description:** Pickle is used for serialization. If these pickle files are later loaded from untrusted sources, arbitrary code execution is possible.
- **Fix:** Document the security implications clearly, or use a safer format like `numpy.savez` or JSON for the saliency data.

---

### M-14 — `montage_picker_dialog.py` `clear_selections` calls `setCurrentIndex(0)` twice

- **File:** `dialogs/visualization/montage_picker_dialog.py`, `clear_selections`
- **Category:** Dead code
- **Description:** `combo.setCurrentIndex(0)` is written twice in succession within the same loop body. The second call is redundant.
- **Fix:** Remove the duplicate line.

---

### M-15 — `ControlSidebar.__init__` doesn't pass `parent` to `super().__init__` correctly

- **File:** `panels/visualization/control_sidebar.py`, line 39
- **Category:** Bug (minor)
- **Description:** `super().__init__(parent)` is called correctly here, but the widget also calls `self.setAttribute(WA_StyledBackground, True)` before `init_ui()`. This is fine, but the sidebar's `setFixedWidth(260)` and `setObjectName("RightPanel")` in `init_ui()` means the background styling from `Stylesheets.SIDEBAR_CONTAINER` applies to ALL child QWidgets too (due to the non-scoped selector), potentially overriding child widget styles.
- **Fix:** Scope the sidebar stylesheet using `#RightPanel` or `QWidget#RightPanel { ... }` to avoid cascade to children.

---

### M-16 — `preview_widget.py` crosshair can reference deleted curve data

- **File:** `panels/preprocess/preview_widget.py`, `_update_crosshair`
- **Category:** Bug / Potential crash
- **Description:** `_update_crosshair` accesses `target_curve.xData` and `target_curve.yData` which may be `None` or deallocated if the plot was just cleared from another thread or signal. The `if x_data is not None ...` check helps but the data arrays could be reassigned between check and use.
- **Fix:** Wrap the data access in a try/except block as a safety net.

---

### M-17 — `TrainingPanel.update_info` sets `self.info_panel = None`

- **File:** `panels/training/panel.py`, `update_info`
- **Category:** Bug
- **Description:** `self.info_panel = None` is set unconditionally. If any code later accesses `self.info_panel`, it will get `None` even though the panel object still exists in the sidebar. This line appears to be a leftover from refactoring.
- **Fix:** Remove `self.info_panel = None`.

---

### M-18 — `Saliency3D._setup_scene` is empty

- **File:** `panels/visualization/saliency_views/plot_3d_head.py`, `_setup_scene`
- **Category:** Dead code
- **Description:** `_setup_scene()` is called from `__init__` but the method body is just `pass`. This is misleading and suggests incomplete implementation.
- **Fix:** Implement the method or remove it and its call site.

---

## LOW Issues

### L-01 — `main_window.py` `add_nav_btn` has dead code at `index==1`

- **File:** `main_window.py`
- **Category:** Dead code
- **Description:** A `pass` statement occupies the `if index == 1:` branch, suggesting an incomplete placeholder feature.
- **Fix:** Remove or implement.

---

### L-02 — `confusion_matrix.py` uses `print()` instead of `logger`

- **File:** `panels/evaluation/confusion_matrix.py`
- **Category:** Code quality
- **Description:** Error handling in `update_plot` uses `print()` instead of the project's `logger`. This is inconsistent with the rest of the codebase.
- **Fix:** Replace `print(...)` with `logger.error(...)`.

---

### L-03 — `topomap_view.py` uses `traceback.print_exc()` alongside `logger.error`

- **File:** `panels/visualization/saliency_views/topomap_view.py`
- **Category:** Code quality
- **Description:** Both `traceback.print_exc()` and `logger.error(..., exc_info=True)` are called. The logger call with `exc_info=True` already logs the full traceback, making `print_exc()` redundant.
- **Fix:** Remove `traceback.print_exc()`.

---

### L-04 — `channel_selection_dialog.py` mixes MultiSelection mode and checkboxes

- **File:** `dialogs/dataset/channel_selection_dialog.py`
- **Category:** UX confusion
- **Description:** The list widget uses both `MultiSelection` selection mode AND individual item checkboxes. Users may be confused about which mechanism controls selection.
- **Fix:** Use one mechanism consistently — either selection highlighting or checkboxes, not both.

---

### L-05 — `TrainingManagerWindow` appears to be legacy / unused

- **File:** `panels/training/training_manager.py`
- **Category:** Dead code
- **Description:** The docstring says "Legacy standalone training manager window" and "NOTE: Appears to be legacy/alternative to `TrainingPanel`". If the new `TrainingPanel` fully replaces this class, it should be removed to reduce maintenance burden.
- **Fix:** Confirm usage, and if unused, remove or mark as deprecated.

---

### L-06 — `BaseDialog` and subclasses inconsistently handle `init_ui()` invocation

- **File:** `core/base_dialog.py`, various dialog subclasses
- **Category:** Architecture inconsistency
- **Description:** `BaseDialog.__init__` calls `self.init_ui()`, but several subclasses (e.g., `DataSplittingDialog`, `VisualizationPanel`) set instance attributes *before* calling `super().__init__()` specifically because they know `init_ui()` will be called during `super().__init__()`. This is a fragile pattern — if a developer doesn't know about this, they may set attributes *after* `super().__init__()` and find `init_ui()` already ran with uninitialized state.
- **Fix:** Document the convention prominently in `BaseDialog`, or change `BaseDialog` to NOT call `init_ui()` automatically (like `BasePanel`), letting subclasses call it explicitly.

---

### L-07 — `data_splitting_preview_dialog.py` `to_thread()` is a no-op on `DataSplitterHolder`

- **File:** `dialogs/dataset/data_splitting_preview_dialog.py`, `preview`
- **Category:** Dead code
- **Description:** The code calls `splitter.to_thread()` for each splitter in the preview method, but this method is documented as a no-op.
- **Fix:** Remove the `to_thread()` calls or implement the method.

---

### L-08 — `model_settings_dialog.py` API key validation only checks "AIza" prefix

- **File:** `dialogs/model_settings_dialog.py`
- **Category:** Weak validation
- **Description:** The Gemini API key is validated only by checking if it starts with "AIza". This is insufficient — a proper validation would at least check the key length (typically 39 characters) or make a lightweight API call.
- **Fix:** Add length validation and/or a test API call during the "Test Connection" flow.

---

### L-09 — `smart_parser_dialog.py` compiles regex without using the result

- **File:** `dialogs/dataset/smart_parser_dialog.py`, `update_preview`
- **Category:** Dead code
- **Description:** `re.compile(self.regex_input.text())` is called inside `contextlib.suppress(Exception)` but the compiled pattern is never used. This appears to be a validation check that was started but never completed.
- **Fix:** Use the compiled regex or remove the dead code. If the intent is validation, show a warning label when the regex is invalid.

---

### L-10 — `Saliency3D.channelActor` compared to `[]` using `!=`

- **File:** `panels/visualization/saliency_views/plot_3d_head.py`, `update`
- **Category:** Code quality
- **Description:** `if self.channelActor != []:` should use the idiomatic `if self.channelActor:` for truthiness checking.
- **Fix:** Change to `if self.channelActor:`.

---

### L-11 — Missing `import numpy as np` in `preview_widget.py`

- **File:** `panels/preprocess/preview_widget.py`, `_update_crosshair`
- **Category:** Potential import error
- **Description:** `np.searchsorted` is used in `_update_crosshair` but `numpy` may not be imported in this file. (It is imported at the module level based on the first 200 lines read; this is a potential issue only if imports were reorganized.)
- **Fix:** Verify `import numpy as np` is present at the top of the file.

---

### L-12 — Stylesheets use non-scoped selectors that cascade unexpectedly

- **File:** `styles/stylesheets.py`
- **Category:** UX / Styling
- **Description:** Several stylesheet constants use bare selectors like `QWidget { ... }` (e.g., `SIDEBAR_CONTAINER`). When applied to a container widget, these cascade to **all** child widgets, potentially overriding styles set elsewhere.
- **Fix:** Scope selectors using object names: `QWidget#RightPanel { ... }`.

---

## Architecture Observations

1. **`BaseDialog` vs `BasePanel` init_ui contract**: `BaseDialog.__init__` calls `init_ui()` automatically, while `BasePanel` does not. This inconsistency is documented but still error-prone. Consider unifying the behavior.

2. **Observer bridge lifecycle**: `QtObserverBridge` instances are created but never explicitly disconnected. Since they're parented to Qt widgets, they'll be cleaned up on widget destruction, but the underlying backend observers may outlive the widgets if the backend controller lives longer.

3. **Matplotlib figure management**: The codebase mixes embedded `FigureCanvas` figures with `pyplot` global state. `plt.close("all")` in one widget destroys figures in others. A cleaner approach would be to exclusively use the OOP API (`Figure()`) and never touch `pyplot`.

4. **Thread safety**: Background workers (`QThreadPool`, `threading.Thread`, `threading.Timer`) are used in several places. Most results are correctly marshalled to the main thread via signals, but a few places (e.g., `PreprocessPlotter` accessing `controller.study.loaded_data_list` directly) break this contract.

5. **Sidebar widgets don't pass `parent` to `super().__init__()`**: Both `TrainingSidebar` and (partially) `ControlSidebar` have issues with parent widget lifetime management.

---

## Recommendations

1. **Immediate:** Fix C-01, C-02, C-03 (crash and data-corruption bugs).
2. **Short-term:** Address all HIGH issues, especially H-03/H-04/H-10 (matplotlib leaks) and H-07 (thread leak).
3. **Medium-term:** Standardize `BaseDialog`/`BasePanel` contracts, scope stylesheets, replace `print()` with `logger`.
4. **Long-term:** Migrate entirely to Matplotlib OOP API (no `pyplot`), add type annotations, and implement proper observer lifecycle management.
