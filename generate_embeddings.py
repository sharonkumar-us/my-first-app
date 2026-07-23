from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(text):
    """Return a numeric vector (embedding) for the input string."""
    return model.encode(text)

# --- Quick test ---
test_vector = embed("Gold PPO plan with a $2000 deductible")
print(f"Embedding shape: {test_vector.shape}")
print(f"First 5 values: {test_vector[:5]}")
import json
import numpy as np

# --- Load all chunks from knowledge_base.jsonl ---
records = []
with open("knowledge_base.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line))

print(f"\nLoaded {len(records)} chunks from knowledge_base.jsonl")

# --- Embed every chunk's text ---
texts = [r["text"] for r in records]
embeddings = model.encode(texts, show_progress_bar=True)

print(f"Generated embeddings array with shape: {embeddings.shape}")

# --- Save as a parallel array, index i matches records[i] ---
np.save("embeddings.npy", embeddings)
print("Saved embeddings.npy")
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

# --- Reduce to 2D ---
pca = PCA(n_components=2)
embeddings_2d = pca.fit_transform(embeddings)

# --- Color-code by section ---
section_colors = {
    "coverage": "tab:blue",
    "exclusions": "tab:red",
    "claims": "tab:green",
    "enrollment": "tab:orange",
}
colors = [section_colors.get(r["section"], "gray") for r in records]

plt.figure(figsize=(8, 6))
for section, color in section_colors.items():
    xs = [embeddings_2d[i, 0] for i, r in enumerate(records) if r["section"] == section]
    ys = [embeddings_2d[i, 1] for i, r in enumerate(records) if r["section"] == section]
    plt.scatter(xs, ys, c=color, label=section, s=80)

plt.legend()
plt.title("Knowledge Base Embeddings (PCA 2D projection)")
plt.xlabel("PC1")
plt.ylabel("PC2")
plt.savefig("embeddings_2d.png", dpi=150, bbox_inches="tight")
print("\nSaved embeddings_2d.png")
plt.show()