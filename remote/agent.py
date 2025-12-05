import os
import torch
import argparse
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer, util
import time
import re
import numpy as np
from flask import Flask, request, jsonify
from pydantic import BaseModel, Field
from prompts import command_params, prompt_start, prompt_preprocess, prompt_training, prompt_evaluation, prompt_visualization, prompt_is_load_data
import random

# Argument Parser
parser = argparse.ArgumentParser()
parser.add_argument("--no_prompt_selection", action="store_true",
                    help="Do not perform semantic prompt selection. Randomly select prompts.")
parser.add_argument("--no_voting", action="store_true",
                    help="Disable multiple inference and majority voting.")
parser.add_argument("--no_rag", action="store_true",
                    help="Disable retrieval-augmented generation.")
args = parser.parse_args()

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

def match_prompt(input_text):
    # Step 1: ALWAYS run original selection to determine n
    query_embedding = retriever.encode(input_text, convert_to_tensor=True)
    cos_scores = util.pytorch_cos_sim(query_embedding, prompt_embeddings)[0]
    mean_similarity = sum(cos_scores) / len(cos_scores)
    cos_scores_np = cos_scores.cpu().numpy()
    std_dev = np.std(cos_scores_np)
    threshold = mean_similarity + std_dev

    original_selected = [
        i for i in range(len(prompts))
        if cos_scores[i] > threshold and cos_scores[i] >= 0.2
    ]
    n = max(1, len(original_selected))   # number of inferences

    # Case 1: no prompt selection → ablation random
    if args.no_prompt_selection:
        idxs = random.sample(range(len(prompts)), n)
        picked_text = "".join(prompts[i][1] for i in idxs)
        if picked_text == "":
            return (1, prompt_start)
        return (n, picked_text)

    # Case 2: normal prompt selection
    if not original_selected:
        print("no match → return start")
        return (1, prompt_start)

    chosen_text = "".join(prompts[i][1] for i in original_selected)
    for i in original_selected:
        print(prompts[i][0])
    return (n, prompt_start + chosen_text)

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

if not args.no_rag:
    load_reference_document(reference_path)

def retrieve_relevant_info(input_text, top_k=3):
    if args.no_rag:
        return []  # 不做 RAG

    query_embedding = retriever.encode(input_text, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, document_embeddings, top_k=top_k)
    return [documents[h['corpus_id']][1] for h in hits[0]]

class Command(BaseModel):
    command: str = Field(description="The command to perform")
    parameters: dict = Field(description="The parameters for the command")

class Text(BaseModel):
    text: str = Field(description="User friendly reply")

def parse_commands_from_output(output):
    # regular expressions
    command_pattern = re.compile(r'"command":\s*"([^"]+)"')
    parameter_pattern = re.compile(r'"parameters":\s*(\{[^{}]+\})')
    text_pattern = re.compile(r'"text":\s*"([^"]+)"')

    commands = command_pattern.findall(output)
    parameters = parameter_pattern.findall(output)
    texts = text_pattern.findall(output)

    extracted_commands = []

    for i, command in enumerate(commands):
        cmd = command.lower()
        if cmd not in command_params:
            continue

        param_str = parameters[i] if i < len(parameters) else '{}'
        try:
            params = eval(param_str)
        except:
            continue

        required = command_params[cmd].get("required", [])
        atleast = command_params[cmd].get("at_least_one", [])

        if any(r not in params for r in required):
            continue
        if atleast and not any(p in params for p in atleast):
            continue

        extracted_commands.append({"command": cmd, "parameters": params})

    # text response
    for t in texts:
        extracted_commands.append({"text": t})

    return extracted_commands

def generate_command(history, input_text, retrieved_info):
    cnt, matched_prompt = match_prompt(input_text)

    if matched_prompt == "Load Data":
        return [{"command": "Import Data"}]

    if args.no_rag:
        combined = f"{history}" + matched_prompt + f"\nuser: {input_text}\nmodel: "
    else:
        combined =f"{history}" + matched_prompt + f"\n[EEG Research Info]:\n{retrieved_info}\nuser: {input_text}\nmodel: "
    print(combined)

    input_ids = tokenizer(combined, return_tensors="pt")
    if torch.cuda.is_available():
        input_ids = input_ids.to("cuda")

    # no voting
    if args.no_voting:
        cnt = 1

    # inference cnt times
    outputs = []
    for _ in range(cnt):
        output = model.generate(
            input_ids['input_ids'],
            max_length=5000,
            do_sample=True,
            temperature=0.6,
            top_p=0.9
        )
        result = tokenizer.decode(output[0], skip_special_tokens=True)
        output_only = result.split("model:")[-1].strip()
        commands = parse_commands_from_output(output_only)
        # no valid command extrated and matched prompt is start
        if commands == [] and matched_prompt == prompt_start:
            print("skip")
            commands = [{"text": output_only}]
        # cnt=1（no voting case），direct return
        if cnt == 1:
            return commands
        if commands:
            outputs.append(commands)

    if not outputs:
        return []

    # Case 1: all text
    all_text = all("text" in cmd for cmds in outputs for cmd in cmds)
    if all_text:
        for cmds in outputs:
            for cmd in cmds:
                if "text" in cmd:
                    return [cmd]

    # Case 2: majority voting
    command_sets = [tuple(cmd["command"] for cmd in cmds if "command" in cmd) for cmds in outputs]
    command_set_counts = {cs: command_sets.count(cs) for cs in command_sets}
    print(command_set_counts)
    majority_set = None
    for cs, count in command_set_counts.items():
        if count >= 2:
            majority_set = cs
            break
    if majority_set:
        for cmds in outputs:
            if tuple(cmd["command"] for cmd in cmds if "command" in cmd) == majority_set:
                return cmds

    # Case 3: unique sequences → give list of options
    unique_sequences = []
    seen = set()
    for cmds in outputs:
        if any("text" in cmd for cmd in cmds):
            continue
        seq = tuple(cmd["command"] for cmd in cmds if "command" in cmd)
        if seq not in seen:
            seen.add(seq)
            unique_sequences.append(cmds)
    if len(unique_sequences) == 1:
        return unique_sequences[0]
    return unique_sequences

@app.route('/generate_command', methods=['POST'])
def api_generate_command():
    data = request.get_json()
    input_text = data.get('input_text', '')
    history = data.get('history', '')
    print(input_text)
    start = time.time()
    retrieved_info = retrieve_relevant_info(input_text)
    while 1:
        commands = generate_command(history, input_text, "\n".join(retrieved_info))
        if commands != []:
          break
        elif (time.time()-start) > 10:
          commands = []
          break
    print(f"spend time: {time.time()-start} sec")
    for command in commands:
      print(command)
    return jsonify(commands)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
