"""Data loader module for validating and applying loaded raw EEG data to a study."""

from typing import TYPE_CHECKING

from XBrainLab.backend.exceptions import DataMismatchError

from ..utils import validate_list_type, validate_type
from .raw import Raw

if TYPE_CHECKING:  # pragma: no cover
    from ..study import Study


class RawDataLoader(list):
    """Container and validator for a collection of loaded raw data files.

    Extends ``list`` to store ``Raw`` objects while enforcing consistency
    checks (channel count, sample frequency, data type, epoch duration)
    across all loaded files.

    Args:
        raw_data_list: Initial list of loaded raw data objects.

    Raises:
        ValueError: If the initial data list is inconsistent.

    """

    def __init__(self, raw_data_list: list[Raw] | None = None):
        if raw_data_list is None:
            raw_data_list = []
        validate_list_type(raw_data_list, Raw, "raw_data_list")
        super().__init__(raw_data_list)
        if raw_data_list:
            self.validate()

    def get_loaded_raw(self, filepath: str) -> Raw | None:
        """Return the loaded raw data with the given filepath.

        Args:
            filepath: Filepath of the raw data.

        """
        for raw_data in self:
            if filepath == raw_data.get_filepath():
                return raw_data
        return None

    def validate(self) -> None:
        """Validate the loaded raw data consistency.

        Raises:
            ValueError: If the loaded raw data is inconsistent or empty.

        """
        for i in range(len(self)):
            raw_data = self[i]
            self.check_loaded_data_consistency(raw_data, idx=0)
            # _, event_id = raw_data.get_event_list()
            # if not event_id:
            #     raise ValueError(
            #         f"No label has been loaded for {raw_data.get_filename()}"
            #     )
        if len(self) == 0:
            raise ValueError("No dataset has been loaded")

    def check_loaded_data_consistency(self, raw: Raw, idx: int = -1):
        """Validate the loaded raw data consistency with the raw data in the dataset
           at the given index.

        Args:
            raw: Loaded raw data.
            idx: Index of the raw data in the dataset. Default to the last one.

        Raises:
            ValueError: If the loaded raw data is inconsistent with
                        the raw data in the dataset.

        """
        validate_type(raw, Raw, "raw")
        # valide if the dataset is empty
        if not self:
            return
        reference = self[idx]
        # check channel number
        if reference.get_nchan() != raw.get_nchan():
            raise DataMismatchError(
                "Dataset channel numbers inconsistent: "
                f"expected {reference.get_nchan()} from {reference.get_filename()}, "
                f"got {raw.get_nchan()} from {raw.get_filename()}.",
            )
        # check sfreq
        if reference.get_sfreq() != raw.get_sfreq():
            raise DataMismatchError(
                "Dataset sample frequency inconsistent: "
                f"expected {reference.get_sfreq()} from {reference.get_filename()}, "
                f"got {raw.get_sfreq()} from {raw.get_filename()}.",
            )
        # check same data type
        if reference.is_raw() != raw.is_raw():
            expected_type = "raw" if reference.is_raw() else "epochs"
            got_type = "raw" if raw.is_raw() else "epochs"
            raise DataMismatchError(
                "Dataset type inconsistent: "
                f"expected {expected_type} from {reference.get_filename()}, "
                f"got {got_type} from {raw.get_filename()}.",
            )
        # check epoch trial size
        if not raw.is_raw() and (
            reference.get_epoch_duration() != raw.get_epoch_duration()
        ):
            raise DataMismatchError(
                "Epoch duration inconsistent: "
                f"expected {reference.get_epoch_duration()} from "
                f"{reference.get_filename()}, got {raw.get_epoch_duration()} "
                f"from {raw.get_filename()}.",
            )

    def append(self, raw: Raw) -> None:
        """Append the loaded raw data to the dataset.

        Args:
            raw: Loaded raw data.

        """
        self.check_loaded_data_consistency(raw)
        super().append(raw)

    def apply(self, study: "Study", force_update: bool = False) -> None:
        """Apply the loaded raw data to the study.

        Args:
            study: XBrainLab Study to apply the loaded raw data.
            force_update: Whether to force override and clear the data of
                following steps.

        """
        from ..study import Study

        validate_type(study, Study, "study")
        self.validate()
        study.set_loaded_data_list(self, force_update=force_update)
