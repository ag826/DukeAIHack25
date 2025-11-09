from LLM_json_generator import generate_conversation_mindmap_json
from vdb import prepare_chunks_for_embedding, embed_chunks, build_faiss_index, query_faiss, make_rag_make_sense
import json

############################################
transcript_path = "afjiv_transcript.txt"
############################################

# Load transcript
with open(transcript_path, "r", encoding="utf-8") as f:
    transcript_text = f.read()

# Generate mindmap JSON
mindmap_data = generate_conversation_mindmap_json(transcript_text, source_file=transcript_path)
output_path = "mindmap.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(mindmap_data, f, indent=2)
print(f"✅ Mind map JSON generated and saved to {output_path}")

# Load JSON
with open(output_path, "r", encoding="utf-8") as f:
    mindmap_json = json.load(f)

# Prepare chunks
chunks = prepare_chunks_for_embedding(mindmap_json)

# Generate embeddings
chunks, embeddings = embed_chunks(chunks)

# Build FAISS index
index = build_faiss_index(embeddings)
print("✅ FAISS index built with", len(chunks), "chunks")

history={}

# ------------------ Interactive loop ------------------
print("\nEnter your questions about the conversation (type 'exit' to quit):")

while True:
    query = input("\nYour query: ").strip()
    if query.lower() in ["exit", "quit"]:
        print("Exiting interactive session.")
        break
    
    # Retrieve top chunks from FAISS
    results = query_faiss(index, query, chunks)

    # Get concise answer from Gemini/LLM
    concise_result = make_rag_make_sense(query, results, history)

    # Print results
    print("\n✅ Concise Answer:")
    print(concise_result)
    history[query] = concise_result
    
    print("\n✅ Chat History:")
    print(history)
    

