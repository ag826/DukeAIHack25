import json
import uuid
import faiss
from sentence_transformers import SentenceTransformer

# ------------------- Step 1: Prepare JSON chunks -------------------

def prepare_chunks_for_embedding(json_data):
    chunks = []

    for topic in json_data["main_topics"]:
        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"Topic: {topic['topic']} introduced by {topic['introduced_by']} at {topic['introduced_at']}. Sentiment: {topic['sentiment']}.",
            "metadata": {"type": "topic"}
        })

        for sub in topic.get("subtopics", []):
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": f"Subtopic: {sub['subtopic']} introduced by {sub['introduced_by']} ({sub['stance']} toward {sub['targeted_at']}). Discussed by {', '.join(sub['discussed_by'])}. Sentiment: {sub['sentiment']}",
                "metadata": {"type": "subtopic"}
            })

    for rel in json_data.get("relationships", []):
        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"Relationship: {rel['from']} {rel['type']} {rel['to']} (initiated by {rel['initiated_by']})",
            "metadata": {"type": "relationship"}
        })

    return chunks

# ------------------- Step 2: Generate embeddings -------------------

def embed_chunks(chunks, model_name="all-MiniLM-L6-v2"):
    model = SentenceTransformer(model_name)
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True)
    for i, c in enumerate(chunks):
        c["embedding"] = embeddings[i]
    return chunks, embeddings

# ------------------- Step 3: Build FAISS index -------------------

def build_faiss_index(embeddings):
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)  # L2 distance
    index.add(embeddings)
    return index

# ------------------- Step 4: Query FAISS -------------------

def query_faiss(index, query_text, chunks, model_name="all-MiniLM-L6-v2", top_k=5):
    model = SentenceTransformer(model_name)
    query_embedding = model.encode([query_text], convert_to_numpy=True)
    distances, indices = index.search(query_embedding, top_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        chunk = chunks[idx]
        results.append({
            "text": chunk["text"],
            "metadata": chunk["metadata"],
            "distance": float(dist)
        })
    return results

# ------------------- Step 5: Test main function -------------------

def main():
    # Load a sample JSON (replace with your actual mindmap JSON)
    with open("mindmap.json", "r", encoding="utf-8") as f:
        mindmap_json = json.load(f)

    # Prepare chunks
    chunks = prepare_chunks_for_embedding(mindmap_json)

    # Generate embeddings
    chunks, embeddings = embed_chunks(chunks)

    # Build FAISS index
    index = build_faiss_index(embeddings)

    print("✅ FAISS index built with", len(chunks), "chunks")

    # Test a query
    query = "Who initially introduces the topic of Cincinnati Tech Community and what is the sentiment?"
    results = query_faiss(index, query, chunks)

    print("\nTop results for query:", query)
    for r in results:
        print(f"- [{r['metadata']['type']}] {r['text']} (distance={r['distance']:.4f})")

if __name__ == "__main__":
    main()
