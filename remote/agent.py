import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer, util
import time
import re
import numpy as np
from flask import Flask, request, jsonify
from pydantic import BaseModel, Field
from prompts import command_dict, prompt_start, prompt_preprocess, prompt_training, prompt_evaluation, prompt_visualization, prompt_is_load_data
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
    # tsne_log.append({
    #     "input": input_text,
    #     "embedding": query_embedding.detach().cpu(),
    # })

    mean_similarity = sum(cos_scores) / len(cos_scores)
    cos_scores_np = cos_scores.cpu().numpy()
    std_dev = np.std(cos_scores_np)
    threshold = mean_similarity + std_dev

    sorted_indices = torch.argsort(cos_scores, descending=True)
    # if prompts[sorted_indices[0].item()][0] == "Load Data":
    #     return (1, "Load Data")
    
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
        if command.lower() not in command_dict:
            return []
        param_str = parameters[i] if i < len(parameters) else '{}'
        try:
            # Parse parameters as dictionary
            param_dict = eval(param_str)  # Caution: eval can be risky with untrusted input
            extracted_commands.append({"command": command, "parameters": param_dict})
        except Exception as e:
            print(f"Error parsing parameters: {e}")

    # Extract texts
    for text in texts:
      extracted_commands.append({"text": text})

    return extracted_commands

def generate_command(input_text, retrieved_info):
    cnt, matched_prompt = match_prompt(input_text, ablation_random=False)
    if matched_prompt == "Load Data":
        return [{"command": "Import Data"}]

    combined_input = matched_prompt + f"\n[EEG Research Info]:\n{retrieved_info} + \nuser: {input_text}" + "\nmodel: " #\n[EEG Research Info]:\n{retrieved_info}
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
    # commands = generate_command(input_text, "\n".join(retrieved_info))
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

from sklearn.manifold import TSNE
import umap
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from sklearn.metrics.pairwise import cosine_distances

def true_input_class(idx: int) -> str:
    if idx < 10:         return "Import Data"
    elif idx < 60:       return "Preprocess"
    elif idx < 100:      return "Training"
    elif idx < 130:      return "Evaluation"
    else:                return "Visualization"

@app.route("/tsne_log_v3_heatmap_class_avg_sim2", methods=["GET"])
def api_tsne_log_v3_heatmap_class_avg_sim():
    import pandas as pd
    import seaborn as sns
    import matplotlib.pyplot as plt
    from collections import defaultdict
    from sklearn.metrics.pairwise import cosine_similarity

    if not tsne_log:
        return jsonify({"error": "No inputs recorded yet."}), 400

    # 1. 取得 embeddings
    input_embeddings = torch.cat(
        [item["embedding"].unsqueeze(0) for item in tsne_log], dim=0
    ).cpu().numpy()
    prompt_labels = [p[0] for p in prompts[1:]]
    prompt_emb_np = prompt_embeddings[1:].cpu().numpy()

    # 2. 先對所有 input 計算 cosine similarity matrix
    similarity_matrix = cosine_similarity(input_embeddings, prompt_emb_np)  # shape: (num_inputs, num_prompts)

    # 3. 分類每個 input 所屬 class
    input_classes = [true_input_class(i) for i in range(len(tsne_log))]
    class_to_indices = defaultdict(list)
    for i, cls in enumerate(input_classes):
        class_to_indices[cls].append(i)

    # 4. 對每個 input 的 similarity row 做 binary select
    binary_select_matrix = []
    for i in range(len(similarity_matrix)):
        cos_scores = similarity_matrix[i]
        mean_sim = np.mean(cos_scores)
        std_sim = np.std(cos_scores)
        threshold = mean_sim + std_sim
        binary_select = (cos_scores > threshold) & (cos_scores >= 0.2)
        binary_select_matrix.append(binary_select.astype(int))  # 1 if selected, 0 otherwise
        print(i, binary_select)

    binary_select_matrix = np.array(binary_select_matrix)  # shape: (num_inputs, num_prompts)

    # 5. 對每個 class 的 binary row 做平均 → 得到選中機率
    avg_selection_prob = []
    class_labels = []

    for cls, indices in class_to_indices.items():
        avg_prob = np.mean(binary_select_matrix[indices, :], axis=0)
        selected_indices = np.where(avg_prob > 0)[0]
        print(f"[{cls}] indices = {indices}")
        print(f"[{cls}] selected prompts:", [prompt_labels[i] for i in selected_indices])
        avg_selection_prob.append(avg_prob)
        class_labels.append(f"{cls} input")

    # 6. 畫圖：轉成 DataFrame 畫 heatmap
    df = pd.DataFrame(avg_selection_prob, index=class_labels, columns=prompt_labels)

    plt.figure(figsize=(12, max(6, len(class_labels) * 0.6)))
    sns.heatmap(df, cmap="YlGnBu", annot=True, fmt=".2f", linewidths=0.5)
    plt.title("Prompt Selection Probability (Thresholded by Mean + Std & ≥ 0.2)")
    plt.tight_layout()
    plt.savefig("tsne_prompt_selection_prob_heatmap.png", dpi=300)
    plt.close()

    return jsonify({
        "status": "ok",
        "message": "saved as tsne_prompt_input_heatmap_class_avg_sim.png",
        "num_classes": len(class_labels)
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)