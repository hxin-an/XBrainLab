class XBrainLabError(Exception):
    """Base class for exceptions in XBrainLab."""

class FileCorruptedError(XBrainLabError):
    """Exception raised when a file is corrupted or cannot be read."""
    def __init__(self, filepath, message="File is corrupted or unreadable"):
        self.filepath = filepath
        self.message = f"{message}: {filepath}"
        super().__init__(self.message)

class UnsupportedFormatError(XBrainLabError):
    """Exception raised when a file format is not supported."""
    def __init__(self, file_extension, message="Unsupported file format"):
        self.file_extension = file_extension
        self.message = f"{message}: {file_extension}"
        super().__init__(self.message)

class DataMismatchError(XBrainLabError):
    """Exception raised when data parameters (e.g., sfreq) do not match."""
    def __init__(self, message="Data parameters mismatch"):
        self.message = message
        super().__init__(self.message)
