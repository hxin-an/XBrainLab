import requests
import csv
import time

API_URL = "http://127.0.0.1:5000/generate_command"

def process_input(input_text, chat_history):
    data = {
        "input_text": input_text,
        "history": chat_history
    }

    start_time = time.time()
    response = requests.post(API_URL, json=data)
    end_time = time.time()

    if response.status_code == 200:
        try:
            llm_output = response.json()
        except:
            llm_output = [{"text": "Invalid JSON response."}]
    else:
        llm_output = [{"text": f"Error {response.status_code}"}]

    elapsed = end_time - start_time
    return llm_output, elapsed

def run_batch(input_csv_path, output_csv_path):
    with open(input_csv_path, newline='', encoding='utf-8-sig') as infile, \
         open(output_csv_path, 'w', newline='', encoding='utf-8') as outfile:

        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ['Model Output', 'Latency (s)']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            row = {k.strip(): v for k, v in row.items()}
            user_input = row["User Input"]
            print(user_input)
            chat_history = []
            llm_response, latency = process_input(user_input, chat_history)

            row['Model Output'] = llm_response
            row['Latency (s)'] = f"{latency:.2f}"
            writer.writerow(row)

    print(f"\nBatch completed. Output saved to: {output_csv_path}")

if __name__ == "__main__":
    run_batch("example_inputs.csv", "output_with_llm/output_with_llm_1.csv")
    run_batch("example_inputs_multi.csv", "output_with_llm/output_with_llm_multi_1.csv")
    run_batch("example_inputs_text.csv", "output_with_llm/output_with_llm_text_1.csv")
