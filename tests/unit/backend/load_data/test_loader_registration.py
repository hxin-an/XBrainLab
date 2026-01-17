import pytest

# Import the package to trigger registration via __init__.py
from XBrainLab.backend.exceptions import UnsupportedFormatError
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory


@pytest.mark.parametrize(
    "ext", [".gdf", ".set", ".fif", ".edf", ".bdf", ".cnt", ".vhdr"]
)
def test_loader_registration_integration(ext):
    """
    Regression test: Ensure that default loaders are registered
    when the package is imported.
    """
    # 1. Attempt to get loader for each extension
    # If not registered, this raises UnsupportedFormatError
    try:
        loader = RawDataLoaderFactory.get_loader(f"test_file{ext}")
        assert callable(loader), f"Loader for {ext} should be callable"
    except UnsupportedFormatError:
        pytest.fail(f"Loader for extension '{ext}' is NOT registered by default.")
