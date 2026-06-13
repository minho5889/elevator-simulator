#!/usr/bin/env python3
# scripts/train.py
"""Stage-4 LoRA fine-tuning script.

Supports fast training using Unsloth if available, or falls back to standard
Hugging Face PEFT / TRL for maximum portability on any cloud GPU.
"""

import os
import sys
import argparse
from datasets import load_dataset
import torch

def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune Gemma-2 on assembled SFT dataset using LoRA.")
    parser.add_argument("--model-id", type=str, default="google/gemma-2-2b-it", help="HF base model ID to fine-tune.")
    parser.add_argument("--train-data", type=str, default="data/sft_train.jsonl", help="Path to training JSONL.")
    parser.add_argument("--eval-data", type=str, default="data/sft_heldout.jsonl", help="Path to evaluation/heldout JSONL.")
    parser.add_argument("--output-dir", type=str, default="outputs/gemma-lora", help="Directory to save checkpoint adapters.")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size.")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate.")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank.")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha.")
    parser.add_argument("--use-unsloth", action="store_true", help="Attempt to use Unsloth for 2x faster training.")
    return parser.parse_args()

def train():
    args = parse_args()
    
    print(f"Loading datasets:\n  Train: {args.train_data}\n  Eval:  {args.eval_data}")
    dataset = load_dataset("json", data_files={"train": args.train_data, "eval": args.eval_data})

    # Verify formatting matches Gemma official chat template turn structure
    def format_prompts(batch):
        formatted = []
        for messages in batch["messages"]:
            # Format turns using typical Gemma 2 format
            prompt_str = ""
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    # Official Gemma 2 template folds system into user's first turn
                    prompt_str += f"<start_of_turn>user\n{content}\n\n"
                elif role == "user":
                    if prompt_str.startswith("<start_of_turn>user\n"):
                        prompt_str += f"{content}<end_of_turn>\n"
                    else:
                        prompt_str += f"<start_of_turn>user\n{content}<end_of_turn>\n"
                elif role == "assistant":
                    prompt_str += f"<start_of_turn>model\n{content}<end_of_turn>\n"
            formatted.append(prompt_str)
        return {"text": formatted}

    dataset = dataset.map(format_prompts, batched=True)

    max_seq_length = 2048

    if args.use_unsloth:
        try:
            from unsloth import FastLanguageModel
            print("Initializing FastLanguageModel via Unsloth...")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=args.model_id,
                max_seq_length=max_seq_length,
                dtype=None,
                load_in_4bit=True,
            )
            
            model = FastLanguageModel.get_peft_model(
                model,
                r=args.lora_r,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                lora_alpha=args.lora_alpha,
                lora_dropout=0,
                bias="none",
                use_gradient_checkpointing="unsloth",
                random_state=42,
                use_rslora=False,
                loftq_config=None,
            )
        except ImportError:
            print("Unsloth is not installed. Falling back to standard PEFT/Transformers...")
            args.use_unsloth = False

    if not args.use_unsloth:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        
        print("Initializing standard AutoModelForCausalLM with 4-bit QLoRA...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
        )
        
        tokenizer = AutoTokenizer.from_pretrained(args.model_id)
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"
        
        model = prepare_model_for_kbit_training(model)
        
        peft_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, peft_config)

    model.print_trainable_parameters()

    from transformers import TrainingArguments
    from trl import SFTTrainer

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        evaluation_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        report_to="none",
        gradient_checkpointing=True,
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("Starting fine-tuning...")
    trainer.train()

    print(f"Saving fine-tuned adapter to {args.output_dir}...")
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print("Training complete!")

if __name__ == "__main__":
    train()
