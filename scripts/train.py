#!/usr/bin/env python3
# scripts/train.py
"""Stage-4 LoRA fine-tune — Gemma 4 E4B elevator dispatcher.

Target: ``google/gemma-4-E4B-it`` — the EXACT HuggingFace source of the served
Ollama ``gemma4:e4b`` (digest c6eb396dbd59, Q4_K_M). This was confirmed by a
fingerprint match between the local GGUF and the HF ``config.json``
(``Gemma4ForConditionalGeneration``; hidden 2560, 42 layers, 8/2 heads, head_dim
256, vocab 262144, 131072 ctx, vision 768/16 + audio 1024/12 towers; PLE
``embedding_length_per_layer_input=256`` → ``e4b`` = effective 4B of 8.0B raw).

Text-tower-only QLoRA: the vision and audio towers are FROZEN (dead weight for a
text-only dispatch task), so LoRA targets only the language model's attention +
MLP projections.

=========================================================================
CRITICAL Gemma-4 format facts (verified against the local GGUF vocab AND
google/gemma-4-E4B-it/chat_template.jinja — two independent sources that agree):

  * Gemma 4 CHANGED its turn delimiters. It does NOT use Gemma-2/3's
    ``<start_of_turn>`` / ``<end_of_turn>`` — those strings are NOT tokens in the
    Gemma-4 vocab. The scheme is ``<|turn>ROLE\n … <turn|>\n`` (open ``<|turn>``
    id 105, close/turn-EOS ``<turn|>`` id 106), with ``<bos>`` once at the top
    and a real ``<|turn>system`` turn (Gemma 4 added native system-role support).
    The official render of one (system,user,assistant) sample is:
        <bos><|turn>system\n{sys}<turn|>\n<|turn>user\n{usr}<turn|>\n
        <|turn>model\n{target}<turn|>\n
    Hand-rolling a turn-marker f-string (as the prior Gemma-2-style scaffold did)
    tokenizes those literals as RAW TEXT and silently poisons train==prod — the
    #1 SFT killer. We therefore format ONLY via ``tokenizer.apply_chat_template``
    (the official template), which is the SAME formatting Ollama's built-in
    ``RENDERER gemma4`` applies at serve time → train render == serve render. The
    render-identity gate (tests/test_structural_agent.py) proves it.

  * EOS-stop bug (Unsloth #5386): after Gemma-4 SFT the merge can reset
    ``eos_token`` to ``<eos>`` (id 1) instead of the turn-ender ``<turn|>``
    (id 106), so the served model NEVER STOPS. We pin ``tokenizer.eos_token =
    '<turn|>'`` so it persists into the saved tokenizer_config / GGUF.

  * Double-BOS: the chat template emits ``<bos>`` itself, so the pre-rendered
    text must be tokenized with ``add_special_tokens=False`` (else two ``<bos>``).
=========================================================================

Toolchain notes (checked at research time — RE-VERIFY at execution, gemma4 is new):
  * Unsloth: load with ``FastModel`` (the unified multimodal loader), NOT
    ``FastLanguageModel``; ``unsloth/gemma-4-E4B-it`` prequant repo exists.
  * Plain HF: model_type ``gemma4`` → ``AutoModelForCausalLM`` resolves to the
    MULTIMODAL ``Gemma4ForConditionalGeneration``; we LoRA-target only
    ``language_model.*`` projections and freeze the rest. transformers >= 5.12.
  * GGUF export (Stage 5): llama.cpp current master supports gemma4
    (``conversion/gemma.py``: Gemma4ForConditionalGeneration → GEMMA4, PLE +
    separate vision/audio mmproj so the text GGUF stays text-only); Q4_K_M works.

This is the Stage-4 driver; Stage-5 (GGUF convert + ``ollama create`` from the
version-controlled ``Modelfile``) is documented in docs/training-plan.md.
"""

import argparse
import os
import sys

# Gemma-4 turn-control tokens (see module docstring). Used for the EOS pin and
# completion-only loss masking — these must be byte-exact or masking misfires.
GEMMA4_EOT = "<turn|>"            # turn-ending EOS, token id 106
GEMMA4_USER_OPEN = "<|turn>user\n"
GEMMA4_MODEL_OPEN = "<|turn>model\n"
DEFAULT_MODEL_ID = "google/gemma-4-E4B-it"


def parse_args():
    p = argparse.ArgumentParser(
        description="Stage-4 LoRA fine-tune of gemma-4-E4B-it as the elevator dispatcher."
    )
    p.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=(
            "HF base to fine-tune. Default is the EXACT source of the served "
            "gemma4:e4b. With --use-unsloth, 'unsloth/gemma-4-E4B-it' is the "
            "prequantized mirror."
        ),
    )
    p.add_argument("--train-data", default="data/sft_train.jsonl")
    p.add_argument("--eval-data", default="data/sft_heldout.jsonl")
    p.add_argument("--output-dir", default="outputs/elevator-gemma-lora")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--max-seq-length", type=int, default=2048,
                   help="Ample: assembled samples max ~200 tokens.")
    p.add_argument("--use-unsloth", action="store_true",
                   help="Use Unsloth FastModel (recommended; 2x faster, less VRAM).")
    p.add_argument("--pilot", type=int, default=0,
                   help="If >0, train on only this many samples (the Stage-4 pilot).")
    p.add_argument("--export-gguf", action="store_true",
                   help="(Unsloth only) after training, export a merged Q4_K_M GGUF "
                        "for the Stage-5 Modelfile.")
    return p.parse_args()


def _load_chat_dataset(args):
    """Load the assembled SFT JSONL. Only the ``messages`` field is used for
    training; ``descriptor`` / ``rationale`` are out-of-band metadata and MUST
    NOT enter the training text (the rationale would corrupt what the model emits).
    """
    from datasets import load_dataset

    print(f"Loading datasets:\n  train: {args.train_data}\n  eval:  {args.eval_data}")
    ds = load_dataset(
        "json", data_files={"train": args.train_data, "eval": args.eval_data}
    )
    if args.pilot and args.pilot > 0:
        n = min(args.pilot, len(ds["train"]))
        print(f"PILOT: training on {n} samples (data-format sanity before the full run).")
        ds["train"] = ds["train"].select(range(n))
    return ds


def _render_text_column(ds, tokenizer):
    """Map each sample's ``messages`` to a single ``text`` string via the model's
    OWN chat template (the official Gemma-4 template). No hand-rolled markers."""

    def _fmt(batch):
        texts = []
        for messages in batch["messages"]:
            texts.append(
                tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            )
        return {"text": texts}

    # Drop all other columns so only `text` reaches the collator.
    return ds.map(_fmt, batched=True, remove_columns=ds["train"].column_names)


def _pin_eos_to_turn_end(tokenizer):
    """Guard Unsloth #5386: ensure EOS is the turn-ender <turn|> (id 106), not
    <eos> (id 1), so the fine-tuned model learns to stop and the saved
    tokenizer_config / GGUF carry the correct stop token for Ollama."""
    if GEMMA4_EOT in tokenizer.get_vocab():
        tokenizer.eos_token = GEMMA4_EOT
        print(f"Pinned eos_token={tokenizer.eos_token!r} (id {tokenizer.eos_token_id}).")
    else:
        # Not the expected Gemma-4 tokenizer — fail loud rather than train on a
        # mismatched base (the whole point of the render-identity discipline).
        raise SystemExit(
            f"FATAL: {GEMMA4_EOT!r} not in the tokenizer vocab — this is not the "
            f"gemma4 base. Refusing to train a wrong-base model (train != prod)."
        )


def _train_unsloth(args, ds):
    from unsloth import FastModel
    from unsloth.chat_templates import train_on_responses_only
    from trl import SFTConfig, SFTTrainer

    print("Loading via Unsloth FastModel (4-bit QLoRA)...")
    model, tokenizer = FastModel.from_pretrained(
        model_name=args.model_id,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
        full_finetuning=False,
    )
    _pin_eos_to_turn_end(tokenizer)

    model = FastModel.get_peft_model(
        model,
        # Text-tower-only: freeze the vision AND audio towers.
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    ds = _render_text_column(ds, tokenizer)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds["train"],
        eval_dataset=ds["eval"],
        args=SFTConfig(
            output_dir=args.output_dir,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.learning_rate,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=100,
            optim="adamw_8bit",
            report_to="none",
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            # The chat template already emits <bos>; don't let the tokenizer add
            # a second one.
            dataset_kwargs={"add_special_tokens": False},
        ),
    )

    # Completion-only loss: mask the prompt, train only on the model's turn — so
    # the model learns to EMIT the plan, not to regurgitate the (constant) system
    # prompt. Markers are the byte-exact Gemma-4 turn openers.
    trainer = train_on_responses_only(
        trainer,
        instruction_part=GEMMA4_USER_OPEN,
        response_part=GEMMA4_MODEL_OPEN,
    )
    return model, tokenizer, trainer


def _train_plain_hf(args, ds):
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer
    from trl import DataCollatorForCompletionOnlyLM

    print("Loading via plain HF transformers + PEFT (4-bit QLoRA)...")
    print("NOTE: model_type 'gemma4' resolves to the MULTIMODAL "
          "Gemma4ForConditionalGeneration; LoRA is scoped to language_model.*.")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    # AutoModelForCausalLM -> Gemma4ForConditionalGeneration for this checkpoint.
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    _pin_eos_to_turn_end(tokenizer)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = "<pad>"  # Gemma reserves <pad> (id 0); never reuse EOS.

    # Freeze the vision + audio towers explicitly (belt-and-suspenders alongside
    # the LoRA scoping below).
    for name, param in model.named_parameters():
        if "language_model" not in name:
            param.requires_grad = False

    model = prepare_model_for_kbit_training(model)
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        # Regex: target ONLY the text tower's attention + MLP projections, so the
        # frozen vision/audio towers (which also have q_proj/etc.) get no adapter.
        target_modules=r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$",
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)

    ds = _render_text_column(ds, tokenizer)

    # Completion-only masking via the model-turn opener (no {% generation %}
    # markers needed in the template).
    collator = DataCollatorForCompletionOnlyLM(
        response_template=GEMMA4_MODEL_OPEN, tokenizer=tokenizer
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds["train"],
        eval_dataset=ds["eval"],
        data_collator=collator,
        args=SFTConfig(
            output_dir=args.output_dir,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.learning_rate,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=100,
            bf16=torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
            fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
            optim="adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
            report_to="none",
            gradient_checkpointing=True,
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            dataset_kwargs={"add_special_tokens": False},
        ),
    )
    return model, tokenizer, trainer


def train():
    args = parse_args()
    ds = _load_chat_dataset(args)

    if args.use_unsloth:
        try:
            model, tokenizer, trainer = _train_unsloth(args, ds)
        except ImportError:
            print("Unsloth not installed — falling back to plain HF transformers/PEFT.")
            args.use_unsloth = False
    if not args.use_unsloth:
        model, tokenizer, trainer = _train_plain_hf(args, ds)

    model.print_trainable_parameters()
    print("Starting fine-tuning...")
    trainer.train()

    print(f"Saving LoRA adapter + tokenizer to {args.output_dir} ...")
    os.makedirs(args.output_dir, exist_ok=True)
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)  # carries the pinned <turn|> EOS

    if args.export_gguf and args.use_unsloth:
        gguf_dir = os.path.join(args.output_dir, "gguf")
        print(f"Exporting merged Q4_K_M GGUF to {gguf_dir} (Unsloth)...")
        # Unsloth merges the adapter and runs llama.cpp conversion to Q4_K_M,
        # matching the served gemma4:e4b footprint.
        model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")

    print(
        "\nTraining complete.\n"
        "Stage 5 (deploy):\n"
        "  1. Convert the merged adapter to Q4_K_M GGUF (Unsloth --export-gguf, or\n"
        "     llama.cpp current master: convert_hf_to_gguf.py — gemma4 supported).\n"
        "  2. Point the version-controlled ./Modelfile FROM at that GGUF, then\n"
        "     `ollama create elevator-gemma -f Modelfile`.\n"
        "  3. Confirm the EOS pin survived: served model must stop on <turn|>\n"
        "     (Unsloth #5386), and run the render-identity gate with\n"
        "     GEMMA4_RENDER_IDENTITY_STRICT=1 (it needs transformers + this base\n"
        "     tokenizer) BEFORE trusting the eval.\n"
    )


if __name__ == "__main__":
    sys.exit(train())
