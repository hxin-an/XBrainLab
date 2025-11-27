import tkinter as tk
from tkinter import Label, Button
from ..base import TopWindow


class DataTypeBox(TopWindow):
    def __init__(self, parent):
        super().__init__(parent, title="Select Data Type")
        self.result = None  # To store the selected data type

        # Fix window size and prevent resizing
        self.fix_window_size()

        # Add label and buttons
        Label(self, text="Please choose the data type:").pack(pady=10)

        Button(self, text="Raw", command=lambda: self.select_type("raw")).pack(side="left", padx=10, pady=20)
        Button(self, text="Epochs", command=lambda: self.select_type("epochs")).pack(side="right", padx=10, pady=20)

    def select_type(self, data_type):
        """Set the selected data type and close the dialog."""
        self.result = data_type
        self.destroy()

    def _get_result(self):
        """Return the selected data type."""
        return self.result
