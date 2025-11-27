import tkinter as tk
from tkinter import scrolledtext, simpledialog
import requests
from .ui_auto import UI_Auto
from ..base import TopWindow
import os
from .extract_files import case_1_with_template, case_2_without_template, case_3_single_list

api_url = "http://127.0.0.1:5000/generate_command"

class ChatDialog(TopWindow):
    def __init__(self, parent, menu_items, preprocess_widgets, training_widgets, evaluation_widgets, visualization_widgets, load_data_widgets, chat_history, on_close):
        super().__init__(parent, "UI Helper")
        self.title("UI Helper")
        self.geometry("320x400")
        
        self.data_path = ''
        self.event_path = ''
        self.filename_temp = ''
        self.file_cnt = 0

        self.menu_items = menu_items
        self.preprocess_widgets = preprocess_widgets
        self.training_widgets = training_widgets
        self.evaluation_widgets = evaluation_widgets
        self.visualization_widgets = visualization_widgets
        self.load_data_widgets = load_data_widgets
        self.chat_history = chat_history if chat_history else []
        self.on_close = on_close

        self.chat_frame = tk.Frame(self)
        self.chat_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.chat_display = tk.Canvas(self.chat_frame, bg="white")
        self.chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat_display.config(width=250, height=370)

        self.scrollbar = tk.Scrollbar(self.chat_frame, orient="vertical", command=self.chat_display.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.config(yscrollcommand=self.scrollbar.set)

        self.message_frame = tk.Frame(self.chat_display, bg="white")
        self.chat_display.create_window((0, 0), window=self.message_frame, anchor="nw")
        self.message_frame.bind("<Configure>", self._configure_scroll_region)

        self.input_frame = tk.Frame(self)
        self.input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        self.user_input = tk.Entry(self.input_frame, width=30)
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.user_input.bind("<Return>", self.send_input)

        self.send_button = tk.Button(self.input_frame, text="Send", command=self.send_input)
        self.send_button.pack(side=tk.RIGHT, padx=5)

        self.chat_frame.pack_propagate(False)
        
        self.reload_chat_history()
        self.protocol("WM_DELETE_WINDOW", self.on_close_dialog)
        self.root = parent

    def reload_chat_history(self):
        for message in self.chat_history:
            role = message['role']
            content = message['content']
            
            if isinstance(content, list) and "text" in content[0]:
                content = content[0]["text"]
            elif "text" in content:
                content = content["text"]
            
            bg_color = "snow2" if role == "user" else "chartreuse2"
            
            self.display_message(role, content, bg=bg_color)
    
    def _configure_scroll_region(self, event=None):
        self.chat_display.update_idletasks()
        self.chat_display.configure(scrollregion=self.chat_display.bbox("all"))
        # self.chat_display.yview_moveto(1.0)
        # self.chat_display.after(10, lambda: self.chat_display.after(30, lambda: self.chat_display.yview_moveto(1.0)))

    def send_input(self, event=None):
        user_input_text = self.user_input.get()
        self.user_input.delete(0, tk.END)
        if not user_input_text.strip():
            return
        if user_input_text == "clear":
            self.clear_chat()
            self.user_input.delete(0, tk.END)
            return

        self.display_message("User", user_input_text, bg="snow2")
        self.chat_history.append({"role": "user", "content": user_input_text})
        self.process_llm_request(user_input_text)

    def clear_chat(self):
        for widget in self.message_frame.winfo_children():
            widget.destroy()
        self.chat_history = []
        self._configure_scroll_region()

    def display_message(self, role, message, bg):
        message_frame = tk.Frame(self.message_frame, bg=bg, bd=0, relief=tk.FLAT)
        label = tk.Label(message_frame, text=message, anchor="w", bg=bg, justify="left", wraplength=230)
        label.pack(padx=10, pady=5, fill=tk.X, expand=True)
        message_frame.pack(anchor="nw", pady=5, padx=7)

        self._configure_scroll_region()
        self.chat_display.yview_moveto(1.0)

    def process_llm_request(self, user_input_text):
        data = {
            "input_text": user_input_text,
            "history": self.chat_history
        }
        while 1:
            response = requests.post(api_url, json=data)
            if response != '':
                break

        if response.status_code == 200:
            llm_response = response.json()
            print(llm_response)

            # Case 1: No response
            if not llm_response:
                self.display_message("LLM", "Unable to generate a correct response, please try again.", bg="chartreuse2")
                self.chat_history.append({"role": "LLM", "content": "Unable to generate a correct response, please try again."})
                return

            # Case 2: Multiple command sets (List of Lists)
            if isinstance(llm_response[0], list):
                self.choose_command_set(llm_response)
                return

            # Case 3: Single response (flat list)
            actions = []
            for resp in llm_response:
                if "command" in resp:
                    if resp["command"] not in actions:
                        actions.append(resp["command"])
                elif "text" in resp:
                    self.display_message("LLM", resp["text"], bg="chartreuse2")
                    self.chat_history.append({"role": "LLM", "content": resp["text"]})
                else:
                    self.display_message("LLM", resp, bg="chartreuse2")
                    self.chat_history.append({"role": "LLM", "content": resp["text"]})
            if actions:
                self.display_message("LLM", f"Perform {', '.join(actions)}", bg="chartreuse2")
                self.chat_history.append({"role": "LLM", "content": f"Perform {', '.join(actions)}"})
                self.confirm_or_cancel(llm_response)

        else:
            tk.messagebox.showerror(
                "Error", f"Failed to get a response from the server. Status code: {response.status_code}"
            )

    def ask_path(self):
        self.input_frame.pack_forget()
        while True:
            self.data_path = simpledialog.askstring("Input", "Please provide the folder path for data (or click 'Cancel' to stop):")
            if self.data_path is None:
                return  # User canceled
            if os.path.isdir(self.data_path):
                break
            self.display_message("LLM", "Invalid path. Please try again.", bg="chartreuse2")

        while True:
            self.event_path = simpledialog.askstring("Input", "Please provide the folder path for event (or click 'Cancel' if integrated in data):")
            if self.event_path is None:
                break
            if os.path.isdir(self.event_path):
                break
            self.display_message("LLM", "Invalid path. Please try again.", bg="chartreuse2")

        self.filename_temp = simpledialog.askstring("Input", "Please provide a filename template for data files:")
        
        list1 = [f for f in os.listdir(self.data_path) if os.path.isfile(os.path.join(self.data_path, f)) and f.endswith(('.edf', '.gdf', '.cnt', '.set', '.npz', '.npy', '.mat'))]
        if self.event_path is not None:
            list2 = [f for f in os.listdir(self.event_path) if os.path.isfile(os.path.join(self.event_path, f))]
            if len(list1) != len(list2):
                    self.display_message("LLM", "Data and event folder have different number of files. Please check your folders and try again.", bg="chartreuse2")
                    return
        self.file_cnt = len(list1)

        if self.filename_temp is None and self.event_path:
            results = case_2_without_template(list1, list2)
        elif self.filename_temp and self.event_path:
            results = case_1_with_template(list1, list2, self.filename_temp)
        elif self.filename_temp is None and self.event_path is None:
            results = case_3_single_list(list1)
        elif self.filename_temp and self.event_path is None:
            results = [{"command": "load data", "parameters": {"data": f}} for f in list1]
        actions = ["load data"]
        self.display_message("LLM", f"Start data loading", bg="chartreuse2")
        print(results)
        self.confirm_or_cancel(results)
        self.chat_history.append({"role": "LLM", "content": f"Perform {', '.join(actions)}"})
        
    def confirm_or_cancel(self, response):
        self.input_frame.pack_forget()

        button_frame = tk.Frame(self)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        confirm_btn = tk.Button(button_frame, text="Confirm", command=lambda: self.execute_command(response, button_frame))
        confirm_btn.pack(side=tk.LEFT, padx=15)

        cancel_btn = tk.Button(button_frame, text="Cancel", command=lambda: self.cancel_command(button_frame))
        cancel_btn.pack(side=tk.RIGHT, padx=15)

    def choose_command_set(self, command_sets):
        self.input_frame.pack_forget()
        # self.chat_display.yview_moveto(1)
        self.selected_index = tk.IntVar(value=-1)

        option_frame = tk.Frame(self, bg="white")
        option_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=4)
        self.option_widgets = []

        def update_highlight():
            for idx, (frame, rb) in enumerate(self.option_widgets):
                if self.selected_index.get() == idx:
                    frame.config(bg="#cceeff")  # 淺藍高亮
                    rb.config(bg="#cceeff", fg="black", selectcolor="#3399ff")
                else:
                    frame.config(bg="white")
                    rb.config(bg="white", fg="black", selectcolor="white")
        
        for idx, cmds in enumerate(command_sets):
            if cmds is None:
                continue
            summary = " → ".join(cmd["command"] for cmd in cmds if "command" in cmd)
            outer = tk.Frame(option_frame, bd=2, relief="groove", bg="white")
            outer.pack(fill=tk.X, pady=0)
            rb = tk.Radiobutton(
                outer,
                text=f"Option {idx + 1}:\n{summary}",
                variable=self.selected_index,
                value=idx,
                anchor="w", justify="left", 
                bg="white", fg="black", 
                wraplength=400,
                padx=10, pady=3,
                indicatoron=True,
                selectcolor="white",
                command=update_highlight
            )
            rb.pack(fill=tk.X, pady=4)
            self.option_widgets.append((outer, rb))

        # Confirm / Cancel buttons
        button_frame = tk.Frame(self)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        confirm_btn = tk.Button(button_frame, text="Confirm", command=lambda: self.confirm_choice(command_sets, button_frame, option_frame))
        confirm_btn.pack(side=tk.LEFT, padx=15)

        cancel_btn = tk.Button(button_frame, text="Cancel", command=lambda: self.cancel_command(button_frame, option_frame))
        cancel_btn.pack(side=tk.RIGHT, padx=15)
        
        self._configure_scroll_region()
        self.chat_display.yview_moveto(1.0)

    def confirm_choice(self, command_sets, button_frame, option_frame):
        selected = self.selected_index.get()
        if selected == -1:
            self.display_message("System", "Please select one of the options.", bg="orange")
            return

        chosen_response = command_sets[selected]
        actions = []
        for resp in chosen_response:
            if resp["command"] not in actions:
                actions.append(resp["command"])
        self.display_message("LLM", f"Perform {', '.join(actions)}", bg="chartreuse2")
        self.chat_history.append({"role": "LLM", "content": f"Perform {', '.join(actions)}"})

        if option_frame:
            option_frame.destroy()
        if button_frame:
            button_frame.destroy()

        self.execute_command(chosen_response, None)

    def execute_command(self, llm_responses, button_frame):
        if button_frame:
            button_frame.destroy()
        for response in llm_responses:
            if response.get("command", "").lower() == "import data":
                self.ask_path()
                return
            if response.get("command", "").lower() == "load data":
                if len(llm_responses) != self.file_cnt:
                    self.display_message("LLM", "Failed to match files. Please try again or alter filenames.", bg="chartreuse2")
                    return
                auto = UI_Auto(self.root, llm_responses, self.menu_items, self.preprocess_widgets, self.training_widgets, self.evaluation_widgets, self.visualization_widgets, self.load_data_widgets, self.data_path, self.event_path)
                auto.action_mapping()
                break
            if "text" in response:
                break
            auto = UI_Auto(self.root, response, self.menu_items, self.preprocess_widgets, self.training_widgets, self.evaluation_widgets, self.visualization_widgets, self.load_data_widgets, None, None)
            auto.action_mapping()
        self.display_message("LLM", "Command Executed.", bg="chartreuse2")
        self.chat_history.append({"role": "LLM", "content": "Command Executed."})
        self.input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    def cancel_command(self, *frames):
        self.display_message("LLM", "Command Cancelled.", bg="chartreuse2")
        self.chat_history.append({"role": "LLM", "content": "Command Cancelled."})
        for frame in frames:
            if frame is not None:
                frame.destroy()
        self.input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    def on_close_dialog(self):
        if self.on_close:
            self.on_close(self.chat_history)
        self.destroy()