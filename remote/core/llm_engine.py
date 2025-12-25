import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from typing import List

class LLMEngine:
    """
    LLM Engine.
    
    Responsible for:
    1. Loading the Language Model (e.g., Gemma-2b-it) and Tokenizer.
    2. Generating text based on inputs.
    """

    def __init__(self, model_name: str = "google/gemma-2b-it"):
        """
        Initialize the LLM Engine.

        Args:
            model_name (str): HuggingFace model identifier.
        """
        print(f"[LLMEngine] Loading model: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def generate(self, prompt: str, n: int = 1, max_length: int = 5000, temperature: float = 0.6) -> List[str]:
        """
        Generate responses from the model.

        Args:
            prompt (str): The full input prompt.
            n (int): Number of sequences to generate (for majority voting).
            max_length (int): Max token length.
            temperature (float): Sampling temperature.

        Returns:
            List[str]: A list of generated response strings (output only, without prompt).
        """
        input_ids = self.tokenizer(prompt, return_tensors="pt")
        if self.device == "cuda":
            input_ids = input_ids.to("cuda")

        results = []
        # Generate n times
        # Note: We loop n times instead of num_return_sequences=n because 
        # we might want independent generations or to handle memory better.
        # Also, the original code did a loop.
        for _ in range(n):
            output = self.model.generate(
                input_ids['input_ids'],
                max_length=max_length,
                do_sample=True,
                temperature=temperature,
                top_p=0.9
            )
            decoded = self.tokenizer.decode(output[0], skip_special_tokens=True)
            
            # Extract only the new content (remove the prompt part if model echoes it)
            # The original code split by "model:"
            if "model:" in decoded:
                output_only = decoded.split("model:")[-1].strip()
            else:
                # Fallback if "model:" tag isn't present (shouldn't happen with correct prompting)
                output_only = decoded[len(prompt):].strip()
            
            results.append(output_only)

        return results
