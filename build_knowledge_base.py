import sqlite3

# --- Load Day 5 raw text files ---
raw_text_files = {
    "benefits.txt": "benefits",
    "claims_process.txt": "claims_process",
    "enrollment.txt": "enrollment",
}

raw_texts = {}
for filename, key in raw_text_files.items():
    with open(f"raw_text/{filename}", "r", encoding="utf-8") as f:
        raw_texts[key] = f.read()

for key, text in raw_texts.items():
    print(f"{key}: {len(text)} chars loaded")

# --- Load Day 4 plans from coverage.db, format as one sentence per plan ---
conn = sqlite3.connect("coverage.db")
cur = conn.cursor()
cur.execute("SELECT plan_id, plan_name, monthly_premium, annual_deductible, copay_pct, network_tier FROM plans")
plan_rows = cur.fetchall()
conn.close()

plan_chunks = []
for plan_id, plan_name, premium, deductible, copay_pct, network_tier in plan_rows:
    sentence = (
        f"{plan_name} ({plan_id}): ${premium}/month premium, "
        f"${deductible} annual deductible, {copay_pct}% copay, "
        f"network tier: {network_tier}."
    )
    plan_chunks.append({
        "plan_id": plan_id,
        "text": sentence,
    })

print(f"\n{len(plan_chunks)} plan summary chunks created:")
for p in plan_chunks:
    print(f"  - {p['text']}")
    from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

def split_by_sections(text):
    """Split on our documents' known headers so each topic (Overview, Covered
    Services, etc.) stays together as its own section before chunking further."""
    lines = text.split("\n")
    sections = []
    current_header = "Introduction"
    current_lines = []

    # A line is treated as a header if it's short and doesn't end in punctuation
    for line in lines:
        stripped = line.strip()
        is_header = (
            stripped
            and len(stripped) < 60
            and not stripped.endswith((".", ",", ":"))
            and not stripped.startswith(("SYNTHETIC", "This document"))
        )
        if is_header and current_lines:
            sections.append((current_header, "\n".join(current_lines).strip()))
            current_header = stripped
            current_lines = []
        elif is_header:
            current_header = stripped
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_header, "\n".join(current_lines).strip()))
    return sections

text_chunks = []
for source_key, text in raw_texts.items():
    sections = split_by_sections(text)
    for section_name, section_text in sections:
        if not section_text:
            continue
        sub_chunks = splitter.split_text(section_text)
        for sub_chunk in sub_chunks:
            text_chunks.append({
                "source_file": f"raw_text/{source_key}.txt",
                "section": section_name,
                "text": sub_chunk,
            })

print(f"\n{len(text_chunks)} text chunks created from policy documents:")
for c in text_chunks:
    print(f"\n--- [{c['source_file']}] Section: {c['section']} ({len(c['text'])} chars) ---")
    print(c['text'])
    from datetime import datetime, timezone

def map_section(header):
    """Map our documents' actual headers into the 4 allowed section categories."""
    header_lower = header.lower()
    if "exclu" in header_lower:
        return "exclusions"
    if "claim" in header_lower:
        return "claims"
    if "enroll" in header_lower:
        return "enrollment"
    # Everything else (Overview, Covered Services, Member Support, Plan Overview, etc.)
    return "coverage"

ingested_at = datetime.now(timezone.utc).isoformat()

knowledge_base = []

# --- Plan rows (structured) ---
for i, p in enumerate(plan_chunks):
    knowledge_base.append({
        "id": f"plan::{p['plan_id']}",
        "text": p["text"],
        "source_file": "coverage.db",
        "source_type": "structured",
        "plan_type": p["plan_id"],
        "section": "coverage",
        "ingested_at": ingested_at,
    })

# --- Policy text chunks (unstructured) ---
for i, c in enumerate(text_chunks):
    knowledge_base.append({
        "id": f"{c['source_file']}::chunk{i}",
        "text": c["text"],
        "source_file": c["source_file"],
        "source_type": "unstructured",
        "plan_type": None,
        "section": map_section(c["section"]),
        "ingested_at": ingested_at,
    })

print(f"\nTotal knowledge base records: {len(knowledge_base)}")
print("\nSample record:")
print(knowledge_base[0])
print("\nSection distribution:")
from collections import Counter
print(Counter(r["section"] for r in knowledge_base))
import json

with open("knowledge_base.jsonl", "w", encoding="utf-8") as f:
    for record in knowledge_base:
        f.write(json.dumps(record) + "\n")

print(f"\nSaved {len(knowledge_base)} records to knowledge_base.jsonl")
import random

print(f"\n=== Sanity check: 5 random chunks out of {len(knowledge_base)} ===")
sample = random.sample(knowledge_base, min(5, len(knowledge_base)))
for i, record in enumerate(sample):
    print(f"\n--- Sample {i+1} ---")
    print(f"id: {record['id']}")
    print(f"section: {record['section']}")
    print(f"source_type: {record['source_type']}")
    print(f"text: {record['text']}")