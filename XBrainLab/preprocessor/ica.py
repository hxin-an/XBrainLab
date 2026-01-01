from mne.preprocessing import ICA as MNE_ICA
from ..load_data import Raw
from .base import PreprocessBase


class ICA(PreprocessBase):
    """Preprocessing class for ICA.

    Input:
        n_components: Number of components.
        method: ICA method (default='fastica').
        random_state: Random state.
    """

    def get_preprocess_desc(self, n_components: int, method: str = 'fastica', random_state: int = 97):
        return f"ICA (n_components={n_components}, method={method})"

    def _data_preprocess(self, preprocessed_data: Raw, n_components: int, method: str = 'fastica', random_state: int = 97):
        preprocessed_data.get_mne().load_data()
        
        # Fit ICA
        if method == 'picard':
            try:
                import picard
            except ImportError:
                raise ImportError("The 'picard' package is required to use method='picard'. Please install it via 'pip install python-picard' or select another method.")

        ica = MNE_ICA(n_components=n_components, method=method, random_state=random_state)
        ica.fit(preprocessed_data.get_mne())
        
        # Apply ICA (for now, we just apply it without excluding components, 
        # or we could add logic to exclude EOG/ECG if channels are present.
        # But typically ICA is used to *find* artifacts. 
        # For a simple pipeline, we might just want to decompose and reconstruct, 
        # or maybe the user wants to exclude specific components?
        # The prompt asks to "string up" ICA, implying a basic integration.
        # A common automated approach is to use EOG channels if available.
        # For now, let's just fit and apply, effectively reconstructing the signal.
        # Wait, just applying ICA without excluding anything doesn't change the signal much 
        # (except for some numerical noise).
        # Usually, users want to *remove* artifacts.
        # Let's add a simple artifact detection if EOG exists, or just leave it as a basic fit-apply 
        # which allows the user to see the components (if we had a visualization for it).
        # Given the UI constraints, maybe we just implement the transformation.
        # Let's stick to a basic implementation that fits and applies.
        # Ideally, we should allow excluding components, but that requires a more complex UI.
        # I'll implement fit and apply, and maybe auto-exclude if EOG is present.
        
        # Let's try to find EOG artifacts automatically if EOG channels exist
        # This makes the "ICA" button actually do something useful (artifact removal)
        # without needing a complex component selection UI yet.
        
        # Check for EOG channels
        if 'eog' in preprocessed_data.get_mne().get_channel_types():
            try:
                eog_indices, _ = ica.find_bads_eog(preprocessed_data.get_mne())
                if eog_indices:
                    ica.exclude = eog_indices
            except Exception:
                # If finding EOG fails (e.g. no events), just ignore
                pass
            
        ica.apply(preprocessed_data.get_mne())
