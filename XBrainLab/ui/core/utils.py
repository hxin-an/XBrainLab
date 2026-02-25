"""UI utility classes for XBrainLab."""


class CheckboxObj:
    """Helper class wrapping a checkbox state and optional callback.

    Commonly used with PyVista/3D plot checkbox widgets to track
    toggle state and invoke a callback on change.

    Attributes:
        ctrl: The current checkbox state value.
        callback: Optional callable invoked with the new state.

    """

    def __init__(self, init_val, callback=None):
        """Initialize the checkbox state wrapper.

        Args:
            init_val: Initial state value for the checkbox.
            callback: Optional callable to invoke on state change.

        """
        self.ctrl = init_val
        self.callback = callback

    def __call__(self, state):
        """Update the state and invoke the callback if set.

        Args:
            state: The new checkbox state value.

        """
        self.ctrl = state
        if self.callback:
            self.callback(state)
