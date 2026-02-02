class CheckboxObj:
    def __init__(self, init_val, callback=None):
        self.ctrl = init_val
        self.callback = callback

    def __call__(self, state):
        self.ctrl = state
        if self.callback:
            self.callback(state)
