import json
import uuid
import faiss
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

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


# ------------------- Step 4: make RAG make sense -------------------

def make_rag_make_sense(query, retrieved_chunks, history, model_name="gemini-2.5-flash"):
    system_prompt = """You are an expert assistant. Your task is to answer questions concisely 
    based only on the provided context. Do not include explanations or unrelated text."""

    context_text = "\n".join(f"- {chunk['text']}" for chunk in retrieved_chunks)

    user_prompt = f"""
    You have the following context to help answer the user's query. Use Chat history to maintain continuity. Keep the answer concise and short:

    [CONTEXT STARTS]
    {context_text}
    [CONTEXT ENDS]

    [CHAT HISTORY STARTS]
    {history}
    [CHAT HISTORY ENDS]

    Here is the user query:
     {query}
    

    """

    # Initialize Gemini client
    model = genai.GenerativeModel("gemini-2.5-flash")

    # Generate response
    response = model.generate_content(
        contents=[system_prompt, user_prompt],
        generation_config={"temperature": 0, "max_output_tokens": 200}
    )

    concise_answer = response.text.strip()

    return concise_answer


# ------------------- Step 6: Test main function -------------------

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

    concise_result = make_rag_make_sense("Who initially introduces the topic of Cincinnati Tech Community and what is the sentiment?", results)
    print(concise_result)

    # print("\nTop results for query:", query)
    # for r in results:
    #     print(f"- [{r['metadata']['type']}] {r['text']} (distance={r['distance']:.4f})")

if __name__ == "__main__":
    main()
