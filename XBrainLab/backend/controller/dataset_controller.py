from XBrainLab.backend.load_data import RawDataLoader
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend import preprocessor as Preprocessor
from XBrainLab.ui.services.label_import_service import LabelImportService
from XBrainLab.backend.load_data import EventLoader
from XBrainLab.backend.utils.logger import logger
import os

class DatasetController:
    """
    Controller for managing dataset operations.
    Handles data loading, modification, and interactions with the Study backend.
    """
    def __init__(self, study):
        self.study = study
        self.label_service = LabelImportService()

    def get_loaded_data_list(self):
        """Returns the list of currently loaded raw data objects."""
        return self.study.loaded_data_list

    def is_locked(self):
        """Checks if the dataset is locked (e.g., downstream operations exist)."""
        return self.study.is_locked()

    def has_data(self):
        """Checks if any data is loaded."""
        return bool(self.study.loaded_data_list)

    def import_files(self, filepaths):
        """
        Imports files into the dataset.
        Returns: (success_count, errors_list)
        """
        existing_data = []
        if self.study.loaded_data_list:
            existing_data = list(self.study.loaded_data_list)
            
        try:
            loader = RawDataLoader(existing_data)
        except Exception as e:
            # If existing data is invalid, specialized handling might be needed
            # For now propagate error or return specific status
            raise ValueError(f"Existing dataset inconsistent: {e}")

        success_count = 0
        errors = []

        for path in filepaths:
            # Check duplicates
            if any(d.get_filepath() == path for d in loader):
                logger.info(f"Skipping duplicate: {path}")
                continue
                
            try:
                logger.info(f"Loading file: {path}")
                raw = RawDataLoaderFactory.load(path)
                
                if raw:
                    loader.append(raw)
                    success_count += 1
                else:
                    errors.append(f"{path}: Loader returned None.")
                    
            except UnsupportedFormatError:
                logger.error(f"Unsupported format: {path}")
                errors.append(f"{path}: Unsupported format.")
            except FileCorruptedError:
                logger.error(f"File corrupted: {path}")
                errors.append(f"{path}: File corrupted.")
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
                errors.append(f"{path}: {str(e)}")

        if success_count > 0:
            loader.apply(self.study, force_update=True)
            
        return success_count, errors

    def clean_dataset(self):
        """Clears all loaded data."""
        self.study.clean_raw_data(force_update=True)

    def remove_files(self, indices):
        """Removes files at specified indices."""
        current_list = self.study.loaded_data_list
        to_remove = []
        for idx in indices:
            if idx < len(current_list):
                to_remove.append(current_list[idx])
        
        new_list = [d for d in current_list if d not in to_remove]
        self.study.set_loaded_data_list(new_list, force_update=True)

    def update_metadata(self, index, subject=None, session=None):
        """Updates subject/session for a specific file index."""
        current_list = self.study.loaded_data_list
        if index < len(current_list):
            data = current_list[index]
            if subject is not None:
                data.set_subject_name(subject)
            if session is not None:
                data.set_session_name(session)
            
            # Sync to study to trigger updates if necessary (often metadata-only doesn't strictly require it, 
            # but resetting preprocess ensures consistency)
            self.study.reset_preprocess(force_update=True)

    def apply_smart_parse(self, results):
        """
        Applies smart parser results to the dataset.
        results: dict {filepath: (subject, session)}
        Returns: count of updated files
        """
        data_list = self.study.loaded_data_list
        count = 0
        for data in data_list:
            path = data.get_filepath()
            if path in results:
                sub, sess = results[path]
                if sub != "-":
                    data.set_subject_name(sub)
                if sess != "-":
                    data.set_session_name(sess)
                count += 1
        
        if count > 0:
            self.study.reset_preprocess(force_update=True)
            
        return count

    def apply_channel_selection(self, selected_channels):
        """
        Applies channel selection to the dataset.
        Returns: success (bool)
        """
        data_list = self.study.loaded_data_list
        preprocessor = Preprocessor.ChannelSelection(data_list)
        
        try:
            # Performs processing
            result = preprocessor.data_preprocess(selected_channels)
            
            # Apply changes
            self.study.backup_loaded_data()
            self.study.set_loaded_data_list(result, force_update=True)
            self.study.lock_dataset()
            return True
        except Exception as e:
            logger.error(f"Channel selection failed: {e}")
            raise e

    def get_filenames(self):
        """Returns list of filepaths for loaded data."""
        return [d.get_filepath() for d in self.study.loaded_data_list]

    def reset_preprocess(self):
        """Triggers a reset of downstream preprocessing."""
        self.study.reset_preprocess(force_update=True)

    # Label Import Wrappers
    def get_data_at_assignments(self, indices):
        """Returns data objects for given indices."""
        data_list = self.study.loaded_data_list
        return [data_list[i] for i in indices if i < len(data_list)]

    def apply_labels_batch(self, target_files, label_map, file_mapping, mapping, selected_event_names):
        """Wraps label service batch application."""
        count = self.label_service.apply_labels_batch(
            target_files, label_map, file_mapping, mapping, selected_event_names
        )
        if count > 0:
            self.study.reset_preprocess(force_update=True)
        return count

    def apply_labels_legacy(self, target_files, labels, mapping, selected_event_names, force_import=False):
        """Wraps label service legacy application."""
        count = self.label_service.apply_labels_legacy(
            target_files, labels, mapping, selected_event_names, force_import=force_import
        )
        if count > 0:
            self.study.reset_preprocess(force_update=True)
        return count

    def get_epoch_count(self, data, event_names):
        """Helper to get epoch count for label validation."""
        return self.label_service.get_epoch_count_for_file(data, event_names)

    def get_smart_filter_suggestions(self, data, target_count):
        """Returns suggested event IDs for filtering based on target count."""
        loader = EventLoader(data)
        return loader.smart_filter(target_count)
