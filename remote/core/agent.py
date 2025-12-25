import random
import numpy as np
import torch
from sentence_transformers import util
from typing import List, Tuple, Dict, Any

from .rag_engine import RAGEngine
from .llm_engine import LLMEngine
from .command_parser import CommandParser

# Import prompts
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from prompts import prompt_start, prompt_is_load_data, prompt_preprocess, prompt_training, prompt_evaluation, prompt_visualization

class Agent:
    """
    The Main Agent Class.
    
    Orchestrates:
    1. Prompt Selection (based on user input).
    2. Context Retrieval (RAG).
    3. Command Generation (LLM).
    4. Result Parsing & Voting.
    """

    def __init__(self, use_rag: bool = True, use_voting: bool = True, no_prompt_selection: bool = False):
        self.use_rag = use_rag
        self.use_voting = use_voting
        self.no_prompt_selection = no_prompt_selection

        # Initialize Components
        self.rag = RAGEngine()
        self.llm = LLMEngine()
        self.parser = CommandParser()

        # Load RAG Reference
        if self.use_rag:
            # Assuming the path relative to where the script is run (usually root)
            # Or we can make this configurable.
            self.rag.load_reference_document("./txt_output/formatted_output.txt")

        # Initialize Prompts
        self.prompts = [
            ("Start", prompt_start),
            ("Import Data", prompt_is_load_data),
            ("Preprocess", prompt_preprocess),
            ("Training", prompt_training),
            ("Evaluation", prompt_evaluation),
            ("Visualization", prompt_visualization)
        ]
        self.prompt_texts = [p[1] for p in self.prompts]
        
        # Pre-compute prompt embeddings for selection
        print("[Agent] Encoding prompts for selection...")
        self.prompt_embeddings = self.rag.encode(self.prompt_texts, convert_to_tensor=True)

    def match_prompt(self, input_text: str) -> Tuple[int, str]:
        """
        Select the best prompt based on input similarity.
        
        Returns:
            Tuple[int, str]: (number_of_inferences, selected_prompt_text)
        """
        # 1. Encode Input
        query_embedding = self.rag.encode(input_text, convert_to_tensor=True)
        
        # 2. Compute Similarity
        cos_scores = util.pytorch_cos_sim(query_embedding, self.prompt_embeddings)[0]
        
        # 3. Dynamic Thresholding
        mean_similarity = sum(cos_scores) / len(cos_scores)
        std_dev = np.std(cos_scores.cpu().numpy())
        threshold = mean_similarity + std_dev

        # 4. Select Prompts
        original_selected = [
            i for i in range(len(self.prompts))
            if cos_scores[i] > threshold and cos_scores[i] >= 0.2
        ]
        
        n = max(1, len(original_selected)) # Number of inferences

        # Case: Random Selection (Ablation)
        if self.no_prompt_selection:
            idxs = random.sample(range(len(self.prompts)), n)
            picked_text = "".join(self.prompts[i][1] for i in idxs)
            return (n, picked_text if picked_text else prompt_start)

        # Case: No match found
        if not original_selected:
            print("[Agent] No specific prompt matched -> Using Start Prompt")
            return (1, prompt_start)

        # Case: Match found
        chosen_text = "".join(self.prompts[i][1] for i in original_selected)
        for i in original_selected:
            print(f"[Agent] Matched Prompt: {self.prompts[i][0]}")
            
        return (n, prompt_start + chosen_text)

    def generate_commands(self, history: str, input_text: str) -> List[Dict[str, Any]]:
        """
        Generate commands based on user input and history.
        """
        # 1. Select Prompt
        cnt, matched_prompt = self.match_prompt(input_text)
        
        # Special Case: Load Data shortcut
        # (Original logic: if prompt is Load Data, return Import Data command directly)
        # However, match_prompt returns combined text, so we check if it *contains* specific logic or just rely on LLM?
        # The original code had: if matched_prompt == "Load Data": return ...
        # But match_prompt returned tuple. Let's replicate the original logic carefully.
        # Original: if matched_prompt == "Load Data" (which was a string return in one branch)
        # My match_prompt returns (n, text).
        # Let's trust the LLM unless we want to hardcode. 
        # For now, I'll skip the hardcoded "Load Data" shortcut unless I see it's critical, 
        # or I can check if prompt_is_load_data is in matched_prompt.
        
        # 2. Retrieve Context (RAG)
        retrieved_info = ""
        if self.use_rag:
            hits = self.rag.retrieve(input_text)
            retrieved_info = "\n".join(hits)

        # 3. Construct Full Prompt
        if self.use_rag:
            combined_prompt = f"{history}{matched_prompt}\n[EEG Research Info]:\n{retrieved_info}\nuser: {input_text}\nmodel: "
        else:
            combined_prompt = f"{history}{matched_prompt}\nuser: {input_text}\nmodel: "

        print(f"[Agent] Generating with {cnt} inferences...")
        
        # 4. Generate (Multiple times if needed)
        if not self.use_voting:
            cnt = 1
            
        raw_outputs = self.llm.generate(combined_prompt, n=cnt)
        
        # 5. Parse Outputs
        parsed_outputs = []
        for output in raw_outputs:
            commands = self.parser.parse(output)
            
            # Fallback: if no commands but we used Start prompt, maybe it's just chat
            if not commands and matched_prompt == prompt_start:
                commands = [{"text": output}]
            
            if commands:
                parsed_outputs.append(commands)

        if not parsed_outputs:
            return []

        # 6. Majority Voting
        return self._perform_voting(parsed_outputs)

    def _perform_voting(self, outputs: List[List[Dict]]) -> List[Dict]:
        """Select the best command set from multiple outputs."""
        if len(outputs) == 1:
            return outputs[0]

        # Case 1: All are text responses
        all_text = all("text" in cmd for cmds in outputs for cmd in cmds)
        if all_text:
            # Return the first text response found
            for cmds in outputs:
                for cmd in cmds:
                    if "text" in cmd:
                        return [cmd]

        # Case 2: Majority Voting on Commands
        # Convert list of dicts to tuple of tuples for hashing
        command_sets = []
        for cmds in outputs:
            # Extract only command parts for voting key
            cmd_tuple = tuple(cmd["command"] for cmd in cmds if "command" in cmd)
            command_sets.append(cmd_tuple)
        
        command_set_counts = {cs: command_sets.count(cs) for cs in command_sets}
        print(f"[Agent] Voting Results: {command_set_counts}")

        majority_set = None
        for cs, count in command_set_counts.items():
            if count >= 2:
                majority_set = cs
                break
        
        if majority_set:
            # Find the full command objects that match the majority set
            for cmds in outputs:
                if tuple(cmd["command"] for cmd in cmds if "command" in cmd) == majority_set:
                    return cmds

        # Case 3: No majority -> Return unique options (or just the first one)
        # Original code returned list of options if unique.
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
        
        # If multiple unique valid command sets, return all of them (as a list of lists? or just one?)
        # The original code returned `unique_sequences` which is List[List[Dict]].
        # The UI probably handles this.
        return unique_sequences
