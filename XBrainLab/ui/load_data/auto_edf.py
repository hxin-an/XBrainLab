from XBrainLab.load_data import EventLoader, Raw, RawDataLoader
from XBrainLab.ui.load_data.base.event import EventDictInfoSetter
from ..script import Script
import mne
import numpy as np
from scipy.io import loadmat

class AutoEdf:
    def __init__(self, parent, data_paths, event_paths, subject_ids, session_ids, type_ctrl):
        data_len = len(data_paths)
        if not (data_len == len(event_paths) == len(subject_ids) == len(session_ids)):
            raise ValueError("All input lists must have the same length.")

        self.data_paths = data_paths
        self.event_paths = event_paths
        self.subject_ids = subject_ids
        self.session_ids = session_ids

        self.raws = []
        self.data_loader = RawDataLoader()
        self.script_history = Script()

    def load_data(self):
        """
        Load raw data from EDF/GDF files and initialize RawDataLoader for each file.
        """
        self.script_history.add_import("import mne")
        self.script_history.add_import("from XBrainLab.load_data import Raw")
        self.script_history.add_cmd("data_loader = study.get_raw_data_loader()")
        self.script_history.newline()

        for i, data_path in enumerate(self.data_paths):
            self.script_history.newline()
            path = data_path.replace('\\', '/')
            self.script_history.add_cmd(f"filepath = {repr(path)}")
            if data_path.endswith('.edf'):
                mne_data = mne.io.read_raw_edf(data_path, preload=True)
                self.script_history.add_cmd(
                    f"data = mne.io.read_raw_edf(filepath, preload=True)"
                )
            elif data_path.endswith('.gdf'):
                mne_data = mne.io.read_raw_gdf(data_path, preload=True)
                self.script_history.add_cmd(
                    f"data = mne.io.read_raw_gdf(filepath, preload=True)"
                )
            else:
                raise ValueError(f"Unsupported file type for {data_path}. Only EDF (.edf) and GDF (.gdf) files are supported.")

            raw = Raw(data_path, mne_data)
            self.data_loader.append(raw)
            self.raws.append(raw)

            self.script_history.add_cmd(f"raw_data = Raw(filepath, data)")
            self.script_history.add_cmd(f"data_loader.append(raw_data)")

    def load_events(self):
        self.script_history.add_import("from XBrainLab.load_data import EventLoader")
        self.script_history.newline()

        for i, (raw, event_path, subject_id, session_id) in enumerate(zip(self.raws, self.event_paths, self.subject_ids, self.session_ids)):
            self.script_history.newline()
            path = self.data_paths[i].replace('\\', '/')
            self.script_history.add_cmd(
                f"raw_data = data_loader.get_loaded_raw({repr(path)})"
            )
            self.script_history.add_cmd(f"raw_data.get_event_list()")
            self.script_history.add_cmd(f"event_loader = EventLoader(raw_data)")
            event_loader = EventLoader(raw)

            # Load events
            if ".txt" in event_path:
                label_list = event_loader.read_txt(event_path)
                path = event_path.replace('\\', '/')
                self.script_history.add_cmd(f"event_loader.read_txt({repr(path)})")
            elif ".mat" in event_path:
                self.script_history.add_import("import scipy.io")
                loaded_mat = loadmat(event_path)
                keys = [k for k in loaded_mat if not k.startswith('_')]
                label_key = keys[0] if len(keys) == 1 else EventDictInfoSetter(None, loaded_mat, keys).get_result()
                label_list = event_loader.from_mat(loaded_mat[label_key])
                path = event_path.replace('\\', '/')
                self.script_history.add_cmd(f"filepath = {repr(path)}")
                self.script_history.add_cmd("event_data = scipy.io.loadmat(filepath)")
                self.script_history.add_cmd(f"event_data = event_data[{label_key!r}]")
                self.script_history.add_cmd(f"event_loader.from_mat(event_data)")
            else:
                raise ValueError(f"Unsupported file type for {event_path}.")

            # Apply events
            new_event_name = {k: str(k) for k in np.unique(label_list)}
            event_loader.create_event(new_event_name)
            raw.set_event(event_loader.events, event_loader.event_id)
            self.script_history.add_cmd(f"event_loader.create_event({new_event_name!r})")
            self.script_history.add_cmd("event_loader.apply()")
            raw.set_subject_name(subject_id)
            raw.set_session_name(session_id)
            self.script_history.add_cmd(f"raw_data.set_subject_name({repr(subject_id)})")
            self.script_history.add_cmd(f"raw_data.set_session_name({repr(session_id)})")


    def assign_ids(self):
        """
        Assign subject IDs and session IDs to the raw data.
        """
        for i, (raw, subject_id, session_id) in enumerate(zip(self.raws, self.subject_ids, self.session_ids)):
            raw.set_subject_name(subject_id)
            raw.set_session_name(session_id)
            self.script_history.add_cmd(f"raw_data.set_subject_name({repr(subject_id)})")
            self.script_history.add_cmd(f"raw_data.set_session_name({repr(session_id)})")

    def get_script(self):
        """
        Get the script history for reproducibility.
        """
        return self.script_history

    def get_results(self):
        """
        Validate and return the processed raw data loaders.
        """
        self.data_loader.validate()
        self.script_history.add_cmd(f"data_loader.validate()", newline=True)
        return self.data_loader
