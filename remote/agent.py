import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer, util
import time
import re
import numpy as np
from flask import Flask, request, jsonify
from pydantic import BaseModel, Field
from prompts import command_params, prompt_start, prompt_preprocess, prompt_training, prompt_evaluation, prompt_visualization, prompt_is_load_data
import random

retriever = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
reference_path = "./txt_output/formatted_output.txt"
documents = []
document_embeddings = []

prompts = [
    ("Start", prompt_start),
    ("Import Data", prompt_is_load_data),
    ("Preprocess", prompt_preprocess),
    ("Training", prompt_training),
    ("Evaluation", prompt_evaluation),
    ("Visualization", prompt_visualization)
]

prompt_texts = [p[1] for p in prompts]
prompt_embeddings = retriever.encode(prompt_texts, convert_to_tensor=True)

app = Flask(__name__)

tokenizer = AutoTokenizer.from_pretrained("google/gemma-2b-it")
model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-2b-it",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

tsne_log = []
# prompt_log = []
def match_prompt(input_text, ablation_random=False):
    query_embedding = retriever.encode(input_text, convert_to_tensor=True)
    cos_scores = util.pytorch_cos_sim(query_embedding, prompt_embeddings)[0]
    mean_similarity = sum(cos_scores) / len(cos_scores)
    cos_scores_np = cos_scores.cpu().numpy()
    std_dev = np.std(cos_scores_np)
    threshold = mean_similarity + std_dev

    sorted_indices = torch.argsort(cos_scores, descending=True)
    
    prompt_for_model = ""
    if not ablation_random:
        # ✅ 正常選擇模式
        for i in range(len(prompts)):
            if cos_scores[i] > threshold and cos_scores[i] >= 0.2:
                print(prompts[i][0])
                prompt_for_model += prompts[i][1]
    else:
        # ✅ Ablation: 先跑一遍看原本會選幾個
        original_selected = [
            i for i in range(len(prompts))
            if cos_scores[i] > threshold and cos_scores[i] >= 0.2
        ]
        cnt = max(1, len(original_selected))
        print(f"Randomly selecting {cnt} prompts for ablation")
        random_indices = random.sample(range(len(prompts)), k=cnt)
        for i in random_indices:
            print(f"[Random] {prompts[i][0]}")
            prompt_for_model += prompts[i][1]

    if prompt_for_model == prompt_is_load_data:
        return (1, "Load Data")
    elif prompt_for_model != "":
        return (3, prompt_start + prompt_for_model)
    else:
        print("no match: Start")
        return (1, prompt_start)

def split_text_into_chunks(text, chunk_size=512):
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

def load_reference_document(path, chunk_size=512):
    global documents, document_embeddings
    with open(path, 'r', encoding='utf-8') as file:
        doc = file.read()
        chunks = split_text_into_chunks(doc, chunk_size)
        for idx, chunk in enumerate(chunks):
            documents.append((f"chunk_{idx}", chunk))

    document_embeddings = retriever.encode([chunk[1] for chunk in documents], convert_to_tensor=True)

load_reference_document(reference_path)

def retrieve_relevant_info(input_text, top_k=3):
    query_embedding = retriever.encode(input_text, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, document_embeddings, top_k=top_k)
    
    retrieved_texts = []
    for hit in hits[0]:
        chunk_name = documents[hit['corpus_id']][0]
        chunk_text = documents[hit['corpus_id']][1]
        snippet = chunk_text
        retrieved_texts.append(f"{chunk_name}: {snippet}")
    
    return retrieved_texts

class Command(BaseModel):
    command: str = Field(description="The command to perform")
    parameters: dict = Field(description="The parameters for the command")

class Text(BaseModel):
    text: str = Field(description="User friendly reply")

def parse_commands_from_output(output):
    # Regular expressions to match commands, parameters, and text
    command_pattern = re.compile(r'"command":\s*"([^"]+)"')
    parameter_pattern = re.compile(r'"parameters":\s*(\{[^{}]+\})')
    text_pattern = re.compile(r'"text":\s*"([^"]+)"')

    # Find all command and parameter pairs
    commands = command_pattern.findall(output)
    parameters = parameter_pattern.findall(output)
    texts = text_pattern.findall(output)

    extracted_commands = []

    # Extract commands and parameters
    for i, command in enumerate(commands):
        cmd = command.lower()
        # step 1: check command
        if cmd not in command_params:
            continue
        # step 2: check parameters
        param_str = parameters[i] if i < len(parameters) else '{}'
        try:
            params = eval(param_str)
            # extracted_commands.append({"command": command, "parameters": paramst})
        except Exception as e:
            print(f"Error parsing parameters: {e}")
            continue
        # step 3: check if all required parameters exist
        required = command_params[cmd].get("required", [])
        at_least_one = command_params[cmd].get("at_least_one", [])
        missing = [p for p in required if p not in params]
        if missing:
            continue
        if at_least_one:
            if not any(p in params for p in at_least_one):
                continue

        # save valied answers
        extracted_commands.append({
            "command": cmd,
            "parameters": params
        })

    # Extract texts
    for text in texts:
      extracted_commands.append({"text": text})

    return extracted_commands

def generate_command(input_text, retrieved_info):
    cnt, matched_prompt = match_prompt(input_text, ablation_random=False)
    if matched_prompt == "Load Data":
        return [{"command": "Import Data"}]

    combined_input = matched_prompt + f"\n[EEG Research Info]:\n{retrieved_info}\nuser: {input_text}" + "\nmodel: " #\n[EEG Research Info]:\n{retrieved_info}
    input_ids = tokenizer(combined_input, return_tensors="pt")

    if torch.cuda.is_available():
        input_ids = input_ids.to("cuda")

    outputs = []
    for _ in range(cnt):
        output = model.generate(
            input_ids['input_ids'],
            max_length= 5000,
            do_sample=True,
            temperature=0.6,
            top_p=0.9
        )
        result = tokenizer.decode(output[0], skip_special_tokens=True)
        output_only = result.split("model:")[-1].strip()
        commands = parse_commands_from_output(output_only)
        print(commands)
        if commands == [] and matched_prompt == prompt_start:
            print("skip")
            commands = [{"text": output_only}]
        if cnt == 1:
            return commands
        if commands:
            outputs.append(commands)

    all_text = all("text" in cmd for cmds in outputs for cmd in cmds)
    if all_text:
        for cmds in outputs:
          for cmd in cmds:
              if "text" in cmd:
                return [cmd]
            
    # Extract the "command" part from each output for comparison
    command_sets = [tuple(cmd["command"] for cmd in cmds if "command" in cmd) for cmds in outputs]
    command_set_counts = {cmd_set: command_sets.count(cmd_set) for cmd_set in command_sets}
    # print(command_sets)
    print(command_set_counts)
    majority_set = None
    for cmd_set, count in command_set_counts.items():
        if count >= 2:
            majority_set = cmd_set
            break

    if majority_set:
        for cmds in outputs:
            if tuple(cmd["command"] for cmd in cmds if "command" in cmd) == majority_set:
                return cmds
    else:
        unique_sequences = []
        seen = set()

        for cmds in outputs:
            if any("text" in cmd for cmd in cmds):
                continue
            sequence = tuple(cmd["command"] for cmd in cmds if "command" in cmd)
            if sequence not in seen:
                seen.add(sequence)
                unique_sequences.append(cmds)
        if len(unique_sequences) == 1:
            return unique_sequences[0]
        return unique_sequences

@app.route('/generate_command', methods=['POST'])
def api_generate_command():
    data = request.get_json()
    input_text = data.get('input_text', '')
    print(input_text)
    start = time.time()
    retrieved_info = retrieve_relevant_info(input_text)
    while 1:
        commands = generate_command(input_text, "\n".join(retrieved_info))
        if commands != []:
          break
        elif (time.time()-start) > 10:
          commands = []
          break
    print(f"spend time: {time.time()-start} sec")
    print(f"spend time: {(time.time()-start)/60} min")
    for command in commands:
      print(command)
    return jsonify(commands)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
