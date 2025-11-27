import tkinter as tk
import tkinter.simpledialog
import tkinter.messagebox
import requests
from .ui_auto import UI_Auto

# Define the API URL (replace with your server's IP address or domain)
api_url = "http://127.0.0.1:5000/generate_command"

def open_llm_input_dialog(menu_items, preprocess_widgets):
    user_input = tk.simpledialog.askstring("User Input", "Enter your command for helper:")

    if user_input:
        print(f"Sending request for input: {user_input}")
        
        data = {
            "input_text": user_input
        }

        response = requests.post(api_url, json=data)

        if response.status_code == 200:
            while len(response.json()) == 0:
                print("error in model output, request again...")
                response = requests.post(api_url, json=data)
                
            llm_response = response.json()
            print(llm_response)
            execute = tk.messagebox.askokcancel("Execute Command", f"LLM Response: {llm_response}\nDo you want to execute these commands?")

            if execute:
                for response in llm_response:
                    print("response: ", response)
                    if "issue" not in response:
                        auto = UI_Auto(response, menu_items, preprocess_widgets)
                        auto.action_mapping()
            else:
                print("Execution canceled.")
        else:
            tk.messagebox.showerror(
                "Error", f"Failed to get a response from the server. Status code: {response.status_code}"
            )
    else:
        print("No input provided")

