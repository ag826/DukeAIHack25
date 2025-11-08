import os
import json
import uuid
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import google.generativeai as genai

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

class PersonDatabase:
    """Person DB with consistent person_id, FAISS, and chunk management"""
    
    def __init__(self, model=None):
        self.persons = {}  # person_id -> data
        self.name_to_id = {}  # lowercase name -> person_id
        self.model = model or EMBED_MODEL
        self.chunks = []
        self.index = None

    def add_person(self, name: str, description: str, source: str):
        """
        Add or update a person.
        If name exists, reuse person_id; else create new.
        """
        name_clean = name.strip()
        pid = self.name_to_id.get(name_clean.lower())
        if pid is None:
            pid = name_clean.lower().replace(" ", "_")
            self.name_to_id[name_clean.lower()] = pid
            self.persons[pid] = {"name": name_clean, "descriptions": []}
        self.persons[pid]["descriptions"].append({"text": description, "source": source})
        return pid

    def load_from_scraper_json(self, json_data):
        """
        Load person from scraper JSON:
        {
          "query": "Name",
          "texts": [...],
          "links": [...]
        }
        """
        name = json_data["query"].strip()
        texts = json_data.get("texts", [])
        links = json_data.get("links", [])
        for i, text in enumerate(texts):
            source = links[i] if i < len(links) else "scraper"
            self.add_person(name, text, source)

    def build_person_chunks(self):
        """Build embedding-ready chunks for FAISS"""
        self.chunks = []
        for pid, pdata in self.persons.items():
            # Combined chunk
            combined_text = " ".join([f"[{d['source']}] {d['text']}" for d in pdata["descriptions"]])
            self.chunks.append({
                "id": str(uuid.uuid4()),
                "text": f"{pdata['name']}: {combined_text}",
                "metadata": {"type": "person_combined", "name": pdata["name"], "person_id": pid}
            })
            # Individual chunks
            for desc in pdata["descriptions"]:
                self.chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": f"{pdata['name']} ({desc['source']}): {desc['text']}",
                    "metadata": {"type": "person_description", "name": pdata["name"], "person_id": pid, "source": desc["source"]}
                })

    def create_faiss_index(self):
        """Encode chunks and build FAISS index"""
        if not self.chunks:
            self.build_person_chunks()
        embeddings = self.model.encode([c["text"] for c in self.chunks], convert_to_numpy=True)
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(embeddings)

    def search(self, query: str, top_k=5):
        if self.index is None:
            raise ValueError("FAISS index not built.")
        query_vec = self.model.encode([query], convert_to_numpy=True)
        distances, indices = self.index.search(query_vec, top_k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            chunk = self.chunks[idx]
            chunk["distance"] = float(dist)
            results.append(chunk)
        return results



# MINDMAP DATABASE
def prepare_mindmap_chunks(json_data, person_db: PersonDatabase = None):
    """Prepare mindmap chunks and link person_id if exists"""
    chunks = []

    for topic in json_data.get("main_topics", []):
        pid = None
        if person_db:
            for person_id, pdata in person_db.persons.items():
                if pdata["name"].lower() == topic["introduced_by"].lower():
                    pid = person_id
                    break

        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"Topic: {topic['topic']} introduced by {topic['introduced_by']} at {topic['introduced_at']}. Sentiment: {topic['sentiment']}.",
            "metadata": {"type": "topic", "introduced_by": topic["introduced_by"], "person_id": pid}
        })

        for sub in topic.get("subtopics", []):
            pid_sub = None
            if person_db:
                for person_id, pdata in person_db.persons.items():
                    if pdata["name"].lower() == sub["introduced_by"].lower():
                        pid_sub = person_id
                        break
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": f"Subtopic: {sub['subtopic']} introduced by {sub['introduced_by']} ({sub['stance']} toward {sub['targeted_at']}). Discussed by {', '.join(sub['discussed_by'])}. Sentiment: {sub['sentiment']}",
                "metadata": {"type": "subtopic", "introduced_by": sub["introduced_by"], "person_id": pid_sub}
            })

    for rel in json_data.get("relationships", []):
        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"Relationship: {rel['from']} {rel['type']} {rel['to']} (initiated by {rel['initiated_by']})",
            "metadata": {"type": "relationship"}
        })

    return chunks


def build_mindmap_index(chunks):
    embeddings = EMBED_MODEL.encode([c["text"] for c in chunks], convert_to_numpy=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    for i, c in enumerate(chunks):
        c["embedding"] = embeddings[i]
    return index


# QUERY BOTH DATABASES
def query_both_indexes(mindmap_index, mindmap_chunks, person_db: PersonDatabase, query_text, top_k_each=3):
    query_vec = EMBED_MODEL.encode([query_text], convert_to_numpy=True)
    results = []

    # Mindmap
    d_mind, i_mind = mindmap_index.search(query_vec, top_k_each)
    for dist, idx in zip(d_mind[0], i_mind[0]):
        chunk = mindmap_chunks[idx]
        chunk["distance"] = float(dist)
        chunk["source"] = "mindmap"
        results.append(chunk)

    # Person DB
    person_results = person_db.search(query_text, top_k=top_k_each)
    for r in person_results:
        r["source"] = "person_db"
        results.append(r)

    # Sort
    results.sort(key=lambda x: x["distance"])
    return results[:top_k_each * 2]


def make_rag_make_sense(query: str, retrieved_chunks: List[Dict], history):
    context = "\n".join(f"- {c['text']}" for c in retrieved_chunks)
    prompt = f"""
You have the following context to help answer the user's query. Use Chat history to maintain continuity. Keep the answer concise and short:

[CONTEXT STARTS]
{context}
[CONTEXT ENDS]

[CHAT HISTORY STARTS]
{history}
[CHAT HISTORY ENDS]

Here is the user query:
{query}
"""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text


def main():
    # Load person JSON from scraper
    person_db = PersonDatabase()
    json_folder= "out_speakers/profiles"
    
    # Iterate over all JSON files in the folder
    for filename in os.listdir(json_folder):
        if filename.endswith(".json"):
            json_path = os.path.join(json_folder, filename)
            print(f"Processing {json_path}...")
            with open(json_path, "r") as f:
                scraper_json = json.load(f)
            
            person_db.load_from_scraper_json(scraper_json)


    with open("person_scraped.json", "r") as f:
        scraper_json = json.load(f)

    person_db = PersonDatabase()
    person_db.load_from_scraper_json(scraper_json)

    # Manual add option
    person_db.add_person("John Doe", "Software engineer with 10 years experience.", "LinkedIn")

    # Build FAISS
    person_db.build_person_chunks()
    person_db.create_faiss_index()

    # Load mindmap
    with open("mindmap.json", "r") as f:
        mindmap_json = json.load(f)
    mindmap_chunks = prepare_mindmap_chunks(mindmap_json, person_db)
    mindmap_index = build_mindmap_index(mindmap_chunks)

    # Query example
    query = "Tell me about Mobasserul Haque"
    results = query_both_indexes(mindmap_index, mindmap_chunks, person_db, query)
    for r in results:
        print(f"{r['source']} | {r.get('person_id')} | {r['text'][:100]}...")

    # RAG answer
    answer = make_rag_make_sense(query, results, history={})
    print("\n💡 Answer:\n", answer)


if __name__ == "__main__":
    main()
