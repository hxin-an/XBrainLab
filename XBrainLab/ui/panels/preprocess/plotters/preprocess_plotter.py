from typing import TYPE_CHECKING

import numpy as np
from scipy.signal import welch

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme

if TYPE_CHECKING:
    from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


class PreprocessPlotter:
    """Handles plotting logic for the PreprocessPanel."""

    def __init__(self, panel: "PreprocessPanel"):
        self.panel = panel

    def _get_chan_data(self, obj, ch_idx, start_time=0, duration=5):
        """Helper to retrieve channel data from a data object."""
        is_raw = obj.is_raw()
        obj_sfreq = obj.get_sfreq()
        data = obj.get_mne().get_data()
        if data is None:
            return None, None

        if is_raw:
            start_sample = int(start_time * obj_sfreq)
            n_samples = int(duration * obj_sfreq)
            end_sample = start_sample + n_samples

            # Check bounds
            if start_sample >= data.shape[1]:
                return None, None
            end_sample = min(end_sample, data.shape[1])

            y = data[ch_idx, start_sample:end_sample]
            x = np.arange(start_sample, end_sample) / obj_sfreq
            return x, y
        elif data.ndim == 3:
            # For epochs, start_time is the epoch index
            epoch_idx = int(start_time)
            epoch_idx = max(epoch_idx, 0)
            if epoch_idx >= data.shape[0]:
                epoch_idx = data.shape[0] - 1

            y = data[epoch_idx, ch_idx, :]
            x = obj.get_mne().times
            return x, y
        return None, None

    def _calc_psd(self, sig, sfreq):
        """Helper to calculate Power Spectral Density."""
        f, Pxx = welch(sig, fs=sfreq, nperseg=min(len(sig), 256 * 4))
        return f, Pxx

    def plot_sample_data(self):
        """Main plotting routine."""
        # Access UI elements from panel
        ax_time = self.panel.ax_time
        ax_freq = self.panel.ax_freq
        canvas_time = self.panel.canvas_time
        canvas_freq = self.panel.canvas_freq

        ax_time.clear()
        ax_freq.clear()

        if (
            not hasattr(self.panel, "controller")
            or not self.panel.controller.has_data()
        ):
            return

        data_list = self.panel.controller.get_preprocessed_data_list()

        orig_list = []
        if hasattr(self.panel, "controller") and hasattr(
            self.panel.controller, "study"
        ):
            orig_list = self.panel.controller.study.loaded_data_list

        if not data_list:
            return

        try:
            # Use first file
            raw_obj = data_list[0]
            orig_obj = orig_list[0] if orig_list else None

            chan_idx = self.panel.chan_combo.currentIndex()
            if chan_idx < 0:
                return  # No channel selected
            chan_name = self.panel.chan_combo.currentText()

            sfreq = raw_obj.get_sfreq()

            # Get Current Data
            start_t = self.panel.time_spin.value()
            x_curr, y_curr = self._get_chan_data(raw_obj, chan_idx, start_time=start_t)

            # Get Original Data (if available and compatible)
            x_orig, y_orig = None, None
            if orig_obj:
                # Try to match time
                x_orig, y_orig = self._get_chan_data(
                    orig_obj, chan_idx, start_time=start_t
                )

            # --- Time Domain Plot ---
            if y_curr is not None:
                # Scale to uV
                y_curr_uv = y_curr * 1e6
                y_orig_uv = y_orig * 1e6 if y_orig is not None else None

                if y_orig_uv is not None and x_orig is not None:
                    ax_time.plot(
                        x_orig, y_orig_uv, color="gray", alpha=0.5, label="Original"
                    )

                ax_time.plot(
                    x_curr, y_curr_uv, color="#2196F3", linewidth=1, label="Current"
                )
                if raw_obj.is_raw():
                    ax_time.set_title(f"{chan_name} (Time)")
                else:
                    ax_time.set_title(f"{chan_name} (Epoch {int(start_t)})")
                ax_time.set_xlabel("Time (s)")
                ax_time.set_ylabel("Amplitude (uV)")
                ax_time.legend(loc="upper right", fontsize="small")

                ax_time.grid(True, linestyle="--", alpha=0.5)

                # Apply Y-Scale
                y_scale = self.panel.yscale_spin.value()
                if y_scale > 0:
                    ax_time.set_ylim(-y_scale, y_scale)

                # --- Plot Events ---
                if raw_obj.is_raw():
                    try:
                        events, event_id_map = raw_obj.get_event_list()
                        if len(events) > 0:
                            # Create reverse map for labels
                            id_to_name = {v: k for k, v in event_id_map.items()}

                            # Define time window
                            t_start_view = x_curr[0]
                            t_end_view = x_curr[-1]

                            for ev in events:
                                ev_sample = ev[0]
                                ev_time = ev_sample / sfreq
                                ev_id = ev[2]

                                if t_start_view <= ev_time <= t_end_view:
                                    ax_time.axvline(
                                        x=ev_time,
                                        color=Theme.WARNING,
                                        linestyle="--",
                                        alpha=0.8,
                                    )
                                    label = id_to_name.get(ev_id, str(ev_id))
                                    # Place text near top
                                    y_lim = ax_time.get_ylim()
                                    y_pos = y_lim[1] - (y_lim[1] - y_lim[0]) * 0.05
                                    x_offset = (t_end_view - t_start_view) * 0.01
                                    ax_time.text(
                                        ev_time + x_offset,
                                        y_pos,
                                        label,
                                        color=Theme.WARNING,
                                        ha="left",
                                        va="bottom",
                                        fontsize="small",
                                        rotation=0,
                                    )
                    except Exception as e:
                        logger.warning(f"Failed to plot events: {e}")

            # --- Frequency Domain (PSD) Plot ---
            if y_curr is not None:
                f_curr, p_curr = self._calc_psd(y_curr_uv, sfreq)

                if y_orig_uv is not None:
                    f_orig, p_orig = self._calc_psd(y_orig_uv, sfreq)
                    ax_freq.plot(
                        f_orig,
                        10 * np.log10(p_orig),
                        color="gray",
                        alpha=0.5,
                        label="Original",
                    )

                ax_freq.plot(
                    f_curr,
                    10 * np.log10(p_curr),
                    color="#2196F3",
                    linewidth=1,
                    label="Current",
                )
                ax_freq.set_title(f"{chan_name} (PSD)")
                ax_freq.set_xlabel("Frequency (Hz)")
                ax_freq.set_ylabel("Power (dB/Hz)")
                ax_freq.legend(loc="upper right", fontsize="small")
                ax_freq.grid(True, linestyle="--", alpha=0.5)

            # Apply Theme to all axes
            Theme.apply_matplotlib_dark_theme(None, axes=[ax_time, ax_freq])

            canvas_time.draw()
            canvas_freq.draw()

        except Exception as e:
            logger.error(f"Plotting failed: {e}")
            ax_time.text(
                0.5, 0.5, "Plot Error", ha="center", va="center", color=Theme.TEXT_MUTED
            )
            canvas_time.draw()
