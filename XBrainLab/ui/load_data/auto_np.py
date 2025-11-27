from XBrainLab.load_data import EventLoader, Raw, RawDataLoader
from XBrainLab.ui.load_data.base.event import EventDictInfoSetter
from ..script import Script
import numpy as np
from scipy.io import loadmat
from .base.dict_setter import DataDictInfoSetter
from .base.array_setter import ArrayInfoSetter
from .base.info import DictInfo
from .base.info import RawInfo
from ...ui.base import TopWindow
import mne
from .base import DataType

class AutoNp(TopWindow):
    def __init__(self, parent, data_paths, event_paths, subject_ids, session_ids, type_ctrl):
        data_len = len(data_paths)
        if not (data_len == len(event_paths) == len(subject_ids) == len(session_ids)):
            raise ValueError("All input lists must have the same length.")

        self.data_paths = data_paths
        self.event_paths = event_paths
        self.subject_ids = subject_ids
        self.session_ids = session_ids
        self.parent = parent
        self.winfo_x = self.parent.winfo_x
        self.winfo_y = self.parent.winfo_y
        self.event_keys = set()
        self.data_keys = set()

        self.raws = []
        self.data_loader = RawDataLoader()
        self.script_history = Script()
        self.dict_info = DictInfo()
        self.raw_info = RawInfo()

        self.script_history.add_import("import numpy as np")
        self.type_ctrl = type_ctrl

    def load_data(self):
        self.script_history.add_import("from XBrainLab.load_data import Raw")
        self.script_history.add_cmd("data_loader = study.get_raw_data_loader()")
        self.script_history.newline()
        if not self.type_ctrl:
            print("No data type selected. Aborting.")
            return False
        for i, data_path in enumerate(self.data_paths):
            self.script_history.newline()
            path = data_path.replace('\\', '/')
            self.script_history.add_cmd(f"filepath = {repr(path)}")
            selected_data = np.load(data_path)
            self.script_history.add_cmd("data = np.load(filepath)")
            if isinstance(selected_data, np.lib.npyio.NpzFile): # npz
                # set dict_info if not set, else use self.dict_info to generate mne data
                if not self.dict_info.is_info_complete(selected_data):
                    dict_info_module = DataDictInfoSetter(
                        self,
                        data_path, selected_data, self.dict_info,
                        self.type_ctrl
                    )
                    dict_info = dict_info_module.get_result()
                    if not dict_info:
                        return False
                    self.dict_info = dict_info
                    self.data_keys = self.dict_info.data_keys
                    self.event_keys = self.dict_info.event_keys
                mne_data, generation_script = self.generate_mne(
                    data_path, selected_data, self.type_ctrl
                )
                self.script_history += generation_script
            else: # npy
                if not self.raw_info.is_info_complete():
                    array_info_module = ArrayInfoSetter(
                        self, data_path, selected_data, self.raw_info,
                        self.type_ctrl
                    )
                    array_info = array_info_module.get_result()

                    if not array_info:
                        return False
                    self.array_info = array_info

                mne_data, generation_script = self.array_info.generate_mne(
                    data_path, selected_data, self.type_ctrl
                )
                self.script_history += generation_script
             
            if not isinstance(mne_data, Raw):
                self.script_history.add_cmd('raw_data = Raw(filepath, data)')
                raw_data = Raw(data_path, mne_data)
            else:
                self.script_history.add_cmd('raw_data = data')
                raw_data = mne_data
            self.data_loader.append(raw_data)
            self.raws.append(raw_data)

            self.script_history.add_cmd(f"data_loader.append(raw_data)")

    def generate_mne(self, filepath, selected_data, data_type):
        script = Script()
        script.add_import("import numpy as np")
        script.add_import("import mne")
        data_array = event_array = None
        for k in self.event_keys:
            if k in selected_data:
                event_array = selected_data[k]
                script.add_cmd(f"event = data[{k!r}]")
                break
        for k in self.data_keys:
            if k in selected_data:
                data_array = selected_data[k]
                script.add_cmd(f"data = data[{k!r}]")
                break
        if data_array is None:
            raise ValueError('No data key was found')

        mne_data, array_script = self.with_key_generate_mne(
            filepath, data_array, data_type
        )
        script += array_script
        # handle event and return raw
        if event_array is None:
            return mne_data, script
        event_array = event_array.squeeze()
        assert len(event_array.shape) == 1
        event_id = {str(i): i for i in np.unique(event_array)}
        events = np.zeros((len(event_array), 3))
        events[:, 0] = range(len(event_array))
        events[:, -1] = event_array

        raw_data = Raw(filepath, mne_data)
        raw_data.set_event(events, event_id)

        script.add_cmd("event = event.squeeze()")
        script.add_cmd("event_id = {str(i): i for i in np.unique(event)}")
        script.add_cmd("events = np.zeros((len(event), 3))")
        script.add_cmd("events[:, 0] = range(len(event))")
        script.add_cmd("events[:, -1] = event")
        script.add_cmd("data = Raw(filepath, data)")
        script.add_cmd("data.set_event(events, event_id)")

        return raw_data, script

    def with_key_generate_mne(self, filepath, data_array, data_type):
        script = Script()
        script.add_import("import numpy as np")
        script.add_import("import mne")
        data_array = self.reshape_array(data_array, script)
        nchan = self.dict_info.nchan
        sfreq = self.dict_info.sfreq
        data_info = mne.create_info(nchan, sfreq, 'eeg')
        script.add_cmd(
            "data_info = mne.create_info("
            f"{nchan!r}, {sfreq!r}, 'eeg')"
        )

        if data_type == DataType.RAW.value:
            mne_data = mne.io.RawArray(data_array, data_info)
            script.add_cmd("data = mne.io.RawArray(data, data_info)")
        elif data_type == DataType.EPOCH.value:
            mne_data = mne.EpochsArray(
                data=data_array, info=data_info, tmin=self.dict_info.tmin
            )
            script.add_cmd(
                "data = mne.EpochsArray("
                f"data=data, info=data_info, tmin={self.dict_info.tmin!r})"
            )
        return mne_data, script

    def reshape_array(self, data, script):
        reshape_idx = []
        MAX_DATA_DIM = 2
        channel_info = self.dict_info.channel_info
        channel_type = self.dict_info.channel_type
        if len(data.shape) > MAX_DATA_DIM:
            epoch_idx = channel_info.index(channel_type.EPOCH)
            reshape_idx = [epoch_idx]
        ch_idx = channel_info.index(channel_type.CH)
        time_idx = channel_info.index(channel_type.TIME)
        reshape_idx += [ch_idx, time_idx]
        data = np.transpose(data, reshape_idx)
        script.add_cmd(f"data = np.transpose(data, axes={reshape_idx!r})")
        return data

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

    def apply_to_study(self, study):
        """
        Apply the processed raw data to a study object.
        """
        for i, data_loader in enumerate(self.data_loaders):
            data_loader.apply(study)
            self.script_history.add_cmd(f"data_loader.apply(study)")

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
