
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from threading import Thread
from .config import LLMConfig
import logging

logger = logging.getLogger("XBrainLab.LLM")

class LLMEngine:
    """
    Core engine for handling LLM loading and inference.
    """
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self.model = None
        self.tokenizer = None
        self.is_loaded = False

    def load_model(self):
        """Loads the model and tokenizer."""
        if self.is_loaded:
            return

        logger.info(f"Loading model: {self.config.model_name} on {self.config.device}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name, 
                cache_dir=self.config.cache_dir
            )
            
            # Load model with optional quantization
            model_kwargs = {
                "device_map": self.config.device,
                "cache_dir": self.config.cache_dir,
                "trust_remote_code": True
            }
            
            if self.config.load_in_4bit:
                # Requires bitsandbytes
                model_kwargs["load_in_4bit"] = True
            else:
                if self.config.device == "cuda":
                    model_kwargs["torch_dtype"] = torch.float16

            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.model_name, 
                **model_kwargs
            )
            
            self.is_loaded = True
            logger.info("Model loaded successfully.")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise e

    def generate_stream(self, messages: list):
        """
        Generates response in a streaming fashion.
        
        Args:
            messages: List of dicts [{'role': 'user', 'content': '...'}, ...]
        
        Yields:
            str: Decoded text chunks.
        """
        if not self.is_loaded:
            self.load_model()

        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            do_sample=self.config.do_sample,
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        for new_text in streamer:
            yield new_text
