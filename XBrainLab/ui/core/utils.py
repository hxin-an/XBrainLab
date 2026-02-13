class CheckboxObj:
    """
    Helper class to wrap a checkbox state and callback.
    Commonly used in PyVista/3D plots.
    """

    def __init__(self, init_val, callback=None):
        self.ctrl = init_val
        self.callback = callback

    def __call__(self, state):
        self.ctrl = state
        if self.callback:
            self.callback(state)
