import os
from dotenv import load_dotenv
import pickle
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from huggingface_hub import InferenceClient

# --------- Load ENV ---------
load_dotenv()
HF_API_TOKEN = os.getenv("HF_API_TOKEN")

# --------- HF Inference Client ---------
client = InferenceClient(
    model="meta-llama/Llama-3.1-8B-Instruct",
    token=HF_API_TOKEN
)

# --------- FAISS Paths and Model ---------
INDEX_PATH = Path(__file__).resolve().parent.parent / "kb" / "faiss_index.bin"
METADATA_PATH = Path(__file__).resolve().parent.parent / "kb" / "metadata.pkl"

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
embed_model = SentenceTransformer(EMBED_MODEL_NAME)

# --------- Load FAISS Index and Metadata ---------
def load_faiss_index_and_metadata():
    index = faiss.read_index(str(INDEX_PATH))
    with open(METADATA_PATH, "rb") as f:
        metadata = pickle.load(f)
    return index, metadata

index, metadata = load_faiss_index_and_metadata()

# --------- Retrieval Function ---------
def retrieve_top_k(query, k=3):
    q_emb = embed_model.encode([query])
    q_emb = np.array(q_emb).astype("float32")
    faiss.normalize_L2(q_emb)
    distances, indices = index.search(q_emb, k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        results.append({
            "doc_path": metadata[idx]["doc_path"],
            "content": metadata[idx]["content"],
            "score": float(dist),
        })
    return results

# --------- Prompt Builder ---------
def build_prompt(query, contexts):
    context_text = "\n\n---\n\n".join(
        [f"Source: {c['doc_path']}\n{c['content']}" for c in contexts]
    )
    return (
        "You are a helpful assistant. Answer the question strictly using ONLY the context provided below.\n\n"
        f"Context:\n{context_text}\n\n"
        f"Question: {query}\n\n"
        "If the answer cannot be found in the context, say: \"I don't know based on the provided information.\""
    )

# --------- Main RAG Function ---------
def answer_query(query, k=3):
    try:
        contexts = retrieve_top_k(query, k)
        prompt = build_prompt(query, contexts)

        response = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[
                {"role": "system", "content": "You answer only using provided context."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.2
        )

        answer = response.choices[0].message["content"].strip()
        return answer, contexts

    except Exception as e:
        print("HF Error:", e)
        raise RuntimeError("Failed to generate answer.")
