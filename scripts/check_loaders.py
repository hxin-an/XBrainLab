import os
import sys

# Ensure backend modules can be imported
sys.path.append(os.getcwd())
try:
    import XBrainLab.backend.load_data  # noqa: F401 # Should trigger registration via __init__.py
    from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
except ImportError:
    # Try importing without XBrainLab prefix if running from inside
    try:
        import backend.load_data  # noqa: F401
        from backend.load_data.factory import RawDataLoaderFactory
    except ImportError:
        print("Could not import backend modules. Run from project root.")
        sys.exit(1)


def check_extension(ext):
    try:
        loader = RawDataLoaderFactory.get_loader(f"test{ext}")
    except Exception as e:
        print(f"[FAIL] {ext}: {e}")
        return False
    else:
        print(f"[OK] {ext}: Found loader {loader.__name__}")
        return True


def check_loader_registration():
    extensions = [".gdf", ".set", ".fif", ".edf", ".bdf", ".cnt", ".vhdr"]

    print("Checking RawDataLoaderFactory registrations...")
    missing = [ext for ext in extensions if not check_extension(ext)]

    if missing:
        print(f"\nMissing registrations for: {missing}")
        sys.exit(1)
    else:
        print("\nAll required loaders are registered.")
        sys.exit(0)


if __name__ == "__main__":
    check_loader_registration()
