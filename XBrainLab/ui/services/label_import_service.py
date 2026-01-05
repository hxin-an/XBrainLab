
import os
import numpy as np
from typing import List, Dict, Any, Optional, Set
from XBrainLab.backend.load_data import EventLoader
from XBrainLab.backend.utils.logger import logger

class LabelImportService:
    """
    Service for handling label import operations.
    Encapsulates logic for:
    - Mapping label files to data files
    - Filtering and synchronizing events
    - Applying labels to Raw objects
    """

    def apply_labels_batch(self, 
                          target_files: List[Any], 
                          label_map: Dict[str, List[int]], 
                          file_mapping: Dict[str, str], 
                          mapping: Dict[int, str],
                          selected_event_names: Optional[Set[str]] = None) -> int:
        """
        Apply labels to multiple files based on a file mapping.
        
        Args:
            target_files: List of Raw data objects.
            label_map: Dictionary {label_filename: [labels]}.
            file_mapping: Dictionary {data_filepath: label_filename}.
            mapping: Dictionary {label_code: label_name}.
            selected_event_names: Set of event names to filter by (optional).
            
        Returns:
            int: Number of files successfully updated.
        """
        matched_count = 0
        
        for data in target_files:
            data_path = data.get_filepath()
            if data_path in file_mapping:
                label_fname = file_mapping[data_path]
                if label_fname in label_map:
                    matched_labels = label_map[label_fname]
                    try:
                        self.apply_labels_to_single_file(data, matched_labels, mapping, selected_event_names)
                        matched_count += 1
                    except Exception as e:
                        logger.error(f"Error applying labels to {data_path}: {e}", exc_info=True)
                        # We re-raise or handle? For batch, maybe log and continue, 
                        # but let's let the caller decide if they want to stop or not.
                        # For now, we log and continue to match UI behavior.
                        pass
                        
        return matched_count

    def apply_labels_legacy(self,
                           target_files: List[Any],
                           labels: List[int],
                           mapping: Dict[int, str],
                           selected_event_names: Optional[Set[str]] = None,
                           force_import: bool = False) -> int:
        """
        Apply a single list of labels sequentially to multiple files (Legacy Mode).
        
        Args:
            target_files: List of Raw data objects.
            labels: Flat list of labels to distribute.
            mapping: Dictionary {label_code: label_name}.
            selected_event_names: Set of event names to filter by.
            force_import: If True, ignores mismatch and forces application (dangerous).
            
        Returns:
            int: Number of files successfully updated.
        """
        label_count = len(labels)
        total_epochs = sum(self.get_epoch_count_for_file(d, selected_event_names) for d in target_files)
        
        if label_count == total_epochs and total_epochs > 0:
            current_idx = 0
            for data in target_files:
                n = self.get_epoch_count_for_file(data, selected_event_names)
                file_labels = labels[current_idx : current_idx + n]
                current_idx += n
                
                if n > 0:
                    self.apply_labels_to_single_file(data, file_labels, mapping, selected_event_names)
            return len(target_files)
            
        elif force_import:
            # Force Import Logic
            current_idx = 0
            applied_count = 0
            for data in target_files:
                # In force mode, we might not trust the filter, but let's try to estimate size
                # or just take chunks. The original UI logic used get_epoch_count_for_file(data, None)
                n = self.get_epoch_count_for_file(data, None) 
                if n == 0: n = 100 # Default fallback from original code
                
                if current_idx + n <= len(labels):
                    file_labels = labels[current_idx : current_idx + n]
                    current_idx += n
                    
                    self._force_apply_single(data, file_labels, mapping)
                    applied_count += 1
            return applied_count
            
        else:
            # Mismatch and not forced
            return 0

    def apply_labels_to_single_file(self, 
                                   data: Any, 
                                   labels: List[int], 
                                   mapping: Dict[int, str], 
                                   selected_event_names: Optional[Set[str]] = None):
        """
        Apply labels to a single data object.
        """
        logger.info(f"Applying labels to {data.get_filename()}. Label count: {len(labels)}")
        
        file_specific_ids = []
        if selected_event_names is not None and data.is_raw():
             events, event_id_map = data.get_event_list()
             if event_id_map:
                 file_specific_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]

        if selected_event_names is not None and data.is_raw() and file_specific_ids:
            # Sync with specific events
            events, _ = data.get_event_list()
            mask = np.isin(events[:, -1], file_specific_ids)
            filtered_events = events[mask]
            
            if len(filtered_events) != len(labels):
                raise ValueError(f"Event count mismatch in {data.get_filename()}: Expected {len(labels)}, found {len(filtered_events)} filtered events.")
                
            new_events = filtered_events.copy()
            new_events[:, 2] = labels
            
            # Update event_id map for the new labels
            new_event_id = {name: code for code, name in mapping.items() if code in np.unique(labels)}
            
            data.set_event(new_events, new_event_id)
            data.set_labels_imported(True)
            logger.info(f"Successfully applied synced labels to {data.get_filename()}")
            
        else:
            # Standard application (using EventLoader)
            loader = EventLoader(data)
            loader.label_list = labels
            loader.create_event(mapping) 
            loader.apply()
            data.set_labels_imported(True)
            logger.info(f"Successfully applied labels to {data.get_filename()}")

    def _force_apply_single(self, data: Any, labels: List[int], mapping: Dict[int, str]):
        """Helper for force application."""
        loader = EventLoader(data)
        loader.label_list = labels
        loader.create_event()
        
        # Update mapping if possible
        current_events, _ = data.get_event_list()
        if current_events is not None:
             new_event_id = {name: code for code, name in mapping.items() if code in np.unique(current_events[:, 2])}
             if new_event_id:
                 data.set_event(current_events, new_event_id)
        
        data.set_labels_imported(True)

    def get_epoch_count_for_file(self, data: Any, selected_event_names: Optional[Set[str]]) -> int:
        """Calculate number of epochs/events in a file matching the filter."""
        if data.is_raw():
            events, event_id_map = data.get_event_list()
            if selected_event_names is not None and event_id_map:
                relevant_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]
                if relevant_ids:
                    mask = np.isin(events[:, -1], relevant_ids)
                    return np.sum(mask)
                return 0
            return len(events)
        else:
            return data.get_epochs_length()
