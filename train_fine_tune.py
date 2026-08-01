"""
Day 15 Step 1 — Fine-tune Qwen2.5-1.5B-Instruct with LoRA on the 25 training
examples curated in Day 14.

RUN FROM ft_env, NOT .venv. Requires:
  pip install torch transformers peft datasets accelerate sentencepiece

Design choices:

  - Qwen2.5-1.5B-Instruct as base. Apache 2.0 (no HuggingFace token gate),
    same family as our production qwen2.5-coder:7b so behavior transfers as
    directly as possible on a 16GB Mac. Fine-tuning the 7B production model
    directly is not feasible on this hardware — this is the tradeoff of
    Path B (open-source local) noted at the start of Day 15.

  - LoRA, not full fine-tuning. We're training ~2M parameters out of 1.5B
    total (~0.1%). Full FT would blow past our 16GB RAM budget; LoRA on
    q_proj + v_proj is the standard cheap-and-cheerful choice.

  - MPS (Apple Silicon GPU), float16. bitsandbytes/QLoRA is CUDA-only, so
    QLoRA is unavailable on Mac. Regular LoRA in float16 is the equivalent
    working setup.

  - 3 epochs. With 25 examples that's 75 total training steps. More epochs
    overfit hard on a set this small; fewer don't move the weights meaningfully.

  - Output goes to ./adapters/ (LoRA weights, ~15MB — safe to keep local).
    The full model is not saved; Day 15 Step 3 loads base + adapter together.
"""

import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
TRAIN_FILE = "fine_tune_train.jsonl"
ADAPTER_DIR = "adapters"

# Sanity check upfront — fail loud, not deep in the training loop.
device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"Device: {device}")
if device == "cpu":
    print("WARNING: MPS not available — training will be much slower.")

assert Path(TRAIN_FILE).exists(), f"{TRAIN_FILE} not found in current directory"

# ---------------------------------------------------------------------------
# Load base model + tokenizer
# ---------------------------------------------------------------------------
print(f"\nLoading base model {BASE_MODEL}...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map={"": device},
)

# Qwen tokenizer has no pad token by default. Use eos as pad — standard practice.
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# ---------------------------------------------------------------------------
# Attach LoRA adapters
# ---------------------------------------------------------------------------
lora_config = LoraConfig(
    r=8,                            # rank — 8 is a good default for small datasets
    lora_alpha=16,                  # scaling; alpha=2*r is a common heuristic
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj"],  # attention query & value projections
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ---------------------------------------------------------------------------
# Load and format the training data
# ---------------------------------------------------------------------------
print(f"\nLoading training data from {TRAIN_FILE}...")

def load_examples(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

raw_examples = load_examples(TRAIN_FILE)
print(f"Loaded {len(raw_examples)} training examples")


def format_and_tokenize(example):
    """Turn a messages-format example into a single tokenized sequence.

    Qwen has its own chat template — using it directly means our fine-tune
    respects Qwen's expected turn markers at inference time.
    """
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    tokenized = tokenizer(
        text,
        truncation=True,
        max_length=1024,
        padding=False,  # DataCollator will pad per-batch
    )
    tokenized["labels"] = tokenized["input_ids"].copy()
    return tokenized


dataset = Dataset.from_list(raw_examples)
dataset = dataset.map(format_and_tokenize, remove_columns=["messages"])
print(f"Formatted {len(dataset)} examples")

# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
training_args = TrainingArguments(
    output_dir=ADAPTER_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=1,      # keep memory small on 16GB Mac
    gradient_accumulation_steps=4,      # effective batch size = 4
    learning_rate=2e-4,                  # LoRA tolerates higher LR than full FT
    warmup_steps=5,
    logging_steps=5,
    save_strategy="epoch",
    save_total_limit=1,                  # keep only the latest checkpoint
    report_to="none",                    # no wandb/tensorboard
    fp16=False,                          # MPS uses its own mixed-precision handling
    optim="adamw_torch",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
)

print("\nStarting training. This will take roughly 3-8 min on M-series 16GB.\n")
trainer.train()

# ---------------------------------------------------------------------------
# Save just the LoRA adapter (small — ~15MB — not the whole model)
# ---------------------------------------------------------------------------
model.save_pretrained(ADAPTER_DIR)
tokenizer.save_pretrained(ADAPTER_DIR)
print(f"\nAdapter saved to ./{ADAPTER_DIR}/")
print("Next: run evaluate_fine_tune.py to compare base vs fine-tuned on the 5 held-out examples.")
