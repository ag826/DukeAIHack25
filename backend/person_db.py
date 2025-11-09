import json
import uuid
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from datetime import datetime
import os

class PersonDatabase:
    """
    Standalone Person Database with FAISS indexing
    Can be used independently and continuously updated
    """
    
    def __init__(self, model_name="all-MiniLM-L6-v2", db_path="person_db"):
        """
        Initialize Person Database
        
        Args:
            model_name: SentenceTransformer model for embeddings
            db_path: Directory to save database files
        """
        self.persons = {}
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.chunks = []
        self.db_path = db_path
        
        # Create directory if it doesn't exist
        os.makedirs(db_path, exist_ok=True)
        
        # File paths
        self.data_file = os.path.join(db_path, "persons.json")
        self.index_file = os.path.join(db_path, "persons.faiss")
        self.chunks_file = os.path.join(db_path, "person_chunks.json")
        self.metadata_file = os.path.join(db_path, "metadata.json")
    
    # ==================== CRUD Operations ====================
    
    def add_person(self, person_id, name, description, source, rebuild_index=True):
        """
        Add or update a person in the database
        
        Args:
            person_id: Unique identifier for the person
            name: Person's name
            description: Text scraped from LinkedIn, website, etc.
            source: Where the description came from (e.g., 'linkedin', 'website', 'twitter')
            rebuild_index: Whether to rebuild FAISS index after adding
        
        Returns:
            dict: The updated person record
        """
        if person_id not in self.persons:
            self.persons[person_id] = {
                "id": person_id,
                "name": name,
                "descriptions": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        
        # Check if description from this source already exists
        existing_sources = [d["source"] for d in self.persons[person_id]["descriptions"]]
        if source in existing_sources:
            # Update existing description
            for desc in self.persons[person_id]["descriptions"]:
                if desc["source"] == source:
                    desc["text"] = description
                    desc["updated_at"] = datetime.now().isoformat()
                    break
        else:
            # Add new description
            self.persons[person_id]["descriptions"].append({
                "text": description,
                "source": source,
                "added_at": datetime.now().isoformat()
            })
        
        self.persons[person_id]["updated_at"] = datetime.now().isoformat()
        
        # Auto-save and rebuild index
        self.save_data()
        if rebuild_index:
            self.build_index()
        
        print(f"✅ Added/Updated {name} ({source})")
        return self.persons[person_id]
    
    def add_person_batch(self, persons_list):
        """
        Add multiple persons at once (more efficient)
        
        Args:
            persons_list: List of dicts with keys: person_id, name, description, source
        """
        for person in persons_list:
            self.add_person(
                person["person_id"],
                person["name"],
                person["description"],
                person["source"],
                rebuild_index=False  # Don't rebuild after each add
            )
        
        # Rebuild index once after all additions
        self.build_index()
        print(f"✅ Batch added {len(persons_list)} person records")
    
    def update_person_description(self, person_id, source, new_description):
        """Update a specific description for a person"""
        if person_id not in self.persons:
            raise ValueError(f"Person {person_id} not found")
        
        updated = False
        for desc in self.persons[person_id]["descriptions"]:
            if desc["source"] == source:
                desc["text"] = new_description
                desc["updated_at"] = datetime.now().isoformat()
                updated = True
                break
        
        if not updated:
            raise ValueError(f"Source {source} not found for person {person_id}")
        
        self.persons[person_id]["updated_at"] = datetime.now().isoformat()
        self.save_data()
        self.build_index()
        
        print(f"✅ Updated {self.persons[person_id]['name']} ({source})")
    
    def delete_person(self, person_id):
        """Delete a person from the database"""
        if person_id in self.persons:
            name = self.persons[person_id]["name"]
            del self.persons[person_id]
            self.save_data()
            self.build_index()
            print(f"✅ Deleted {name}")
        else:
            print(f"⚠️ Person {person_id} not found")
    
    def get_person(self, person_id):
        """Get a person's full record"""
        return self.persons.get(person_id)
    
    def get_person_by_name(self, name):
        """Find person by name (case-insensitive)"""
        name_lower = name.lower()
        for person in self.persons.values():
            if person["name"].lower() == name_lower:
                return person
        return None
    
    def list_all_persons(self):
        """List all persons with basic info"""
        result = []
        for person in self.persons.values():
            result.append({
                "id": person["id"],
                "name": person["name"],
                "num_sources": len(person["descriptions"]),
                "sources": [d["source"] for d in person["descriptions"]],
                "updated_at": person.get("updated_at", "N/A")
            })
        return result
    
    # ==================== FAISS Index Operations ====================
    
    def build_index(self):
        """Build FAISS index for all persons"""
        if not self.persons:
            print("⚠️ No persons in database. Index not built.")
            return
        
        self.chunks = []
        
        for person in self.persons.values():
            # Create a combined chunk with all descriptions
            all_descriptions = " ".join([
                f"[{desc['source']}] {desc['text']}" 
                for desc in person["descriptions"]
            ])
            
            self.chunks.append({
                "id": person["id"],
                "text": f"Person: {person['name']}. {all_descriptions}",
                "metadata": {
                    "type": "person_combined",
                    "name": person["name"],
                    "person_id": person["id"]
                }
            })
            
            # Create individual chunks for each description
            for desc in person["descriptions"]:
                self.chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": f"{person['name']} ({desc['source']}): {desc['text']}",
                    "metadata": {
                        "type": "person_description",
                        "name": person["name"],
                        "person_id": person["id"],
                        "source": desc["source"]
                    }
                })
        
        # Generate embeddings
        texts = [c["text"] for c in self.chunks]
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        
        # Add embeddings to chunks
        for i, c in enumerate(self.chunks):
            c["embedding"] = embeddings[i]
        
        # Build FAISS index
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(embeddings)
        
        # Auto-save index
        self.save_index()
        
        print(f"✅ FAISS index built with {len(self.chunks)} chunks for {len(self.persons)} persons")
    
    def search(self, query_text, top_k=5, filter_by_source=None):
        """
        Search the person database using FAISS
        
        Args:
            query_text: Search query
            top_k: Number of results to return
            filter_by_source: Optional - filter results by source (e.g., 'linkedin')
        
        Returns:
            List of matching chunks with metadata and distances
        """
        if self.index is None:
            raise ValueError("Index not built. Call build_index() first or load existing index.")
        
        query_embedding = self.model.encode([query_text], convert_to_numpy=True)
        
        # Search more than needed if filtering
        search_k = top_k * 3 if filter_by_source else top_k
        distances, indices = self.index.search(query_embedding, search_k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            chunk = self.chunks[idx]
            
            # Apply source filter if specified
            if filter_by_source:
                if chunk["metadata"].get("source") != filter_by_source:
                    continue
            
            results.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "distance": float(dist)
            })
            
            if len(results) >= top_k:
                break
        
        return results
    
    # ==================== Persistence Operations ====================
    
    def save_data(self):
        """Save person data to JSON"""
        data = {
            "persons": list(self.persons.values()),
            "metadata": {
                "total_persons": len(self.persons),
                "last_updated": datetime.now().isoformat(),
                "model_name": self.model_name
            }
        }
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Data saved to {self.data_file}")
    
    def load_data(self):
        """Load person data from JSON"""
        if not os.path.exists(self.data_file):
            print(f"⚠️ No existing data file found at {self.data_file}")
            return False
        
        with open(self.data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.persons = {p["id"]: p for p in data["persons"]}
        print(f"✅ Loaded {len(self.persons)} persons from {self.data_file}")
        return True
    
    def save_index(self):
        """Save FAISS index and chunks to disk"""
        if self.index is None:
            print("⚠️ No index to save")
            return
        
        # Save FAISS index
        faiss.write_index(self.index, self.index_file)
        
        # Save chunks (without embeddings to save space)
        chunks_without_embeddings = [
            {k: v for k, v in chunk.items() if k != "embedding"}
            for chunk in self.chunks
        ]
        with open(self.chunks_file, "w", encoding="utf-8") as f:
            json.dump(chunks_without_embeddings, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Index saved to {self.index_file}")
    
    def load_index(self):
        """Load FAISS index and chunks from disk"""
        if not os.path.exists(self.index_file) or not os.path.exists(self.chunks_file):
            print(f"⚠️ Index files not found. Building new index...")
            self.build_index()
            return False
        
        self.index = faiss.read_index(self.index_file)
        with open(self.chunks_file, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
        
        print(f"✅ Index loaded from {self.index_file}")
        return True
    
    def load_complete(self):
        """Load both data and index"""
        self.load_data()
        self.load_index()
    
    # ==================== Statistics & Info ====================
    
    def get_statistics(self):
        """Get database statistics"""
        total_descriptions = sum(len(p["descriptions"]) for p in self.persons.values())
        sources = set()
        for person in self.persons.values():
            for desc in person["descriptions"]:
                sources.add(desc["source"])
        
        return {
            "total_persons": len(self.persons),
            "total_descriptions": total_descriptions,
            "unique_sources": list(sources),
            "avg_descriptions_per_person": total_descriptions / len(self.persons) if self.persons else 0,
            "index_size": len(self.chunks) if self.chunks else 0
        }
    
    def print_statistics(self):
        """Print formatted statistics"""
        stats = self.get_statistics()
        print("\n" + "="*60)
        print("📊 Person Database Statistics")
        print("="*60)
        print(f"Total Persons: {stats['total_persons']}")
        print(f"Total Descriptions: {stats['total_descriptions']}")
        print(f"Average Descriptions per Person: {stats['avg_descriptions_per_person']:.2f}")
        print(f"Unique Sources: {', '.join(stats['unique_sources'])}")
        print(f"FAISS Index Size: {stats['index_size']} chunks")
        print("="*60 + "\n")
    
    # ==================== Web Search Integration ====================
    
    def add_from_search_results(self, search_json, person_id=None, name=None):
        """
        Add person from web search results JSON
        
        JSON Structure:
        {
            "query": "Person Name",           # The person's name
            "total_results": 10,
            "texts": [                        # Scraped text from each source
                "Text from source 1...",
                "Text from source 2...",
                ...
            ],
            "links": [                        # URLs in same order as texts
                "https://source1.com",
                "https://source2.com",
                ...
            ]
        }
        
        Args:
            search_json: Dict with 'query' (name), 'texts' (scraped content), 'links' (source URLs)
                        Note: texts[i] corresponds to links[i]
            person_id: Optional custom ID (auto-generated from name if not provided)
            name: Optional custom name (uses 'query' field if not provided)
        
        Returns:
            dict: The created/updated person record
        """
        # Extract name from query if not provided
        if name is None:
            name = search_json.get("query", "Unknown")
        
        # Generate person_id if not provided
        if person_id is None:
            # Create a clean ID from the name
            person_id = "p_" + "".join(c.lower() if c.isalnum() else "_" for c in name)
        
        # Get texts and combine them
        texts = search_json.get("texts", [])
        
        if not texts:
            print("⚠️ No 'texts' field found in search results")
            return None
        
        # Combine all texts into a single description
        combined_text = " ".join(texts)
        
        # Add as web_search source with combined text
        self.add_person(
            person_id=person_id,
            name=name,
            description=combined_text,
            source="web_search",
            rebuild_index=True
        )
        
        # Optionally, add structured data grouped by domain
        # texts[i] corresponds to links[i] (same order)
        links = search_json.get("links", [])
        if links and len(links) == len(texts):
            self._add_structured_results(person_id, name, texts, links)
        
        print(f"✅ Added {name} from web search results ({len(texts)} text snippets)")
        return self.get_person(person_id)
    
    def _add_structured_results(self, person_id, name, texts, links):
        """
        Add structured information from individual search result snippets
        Groups snippets by domain for better organization
        
        Important: texts[i] corresponds to links[i] (same order)
        
        Args:
            person_id: Person identifier
            name: Person's name
            texts: List of text snippets scraped from sources
            links: List of URLs (in same order as texts)
        """
        if not texts or not links:
            return
        
        # Group texts by domain - texts[i] came from links[i]
        domain_snippets = {}
        for text, link in zip(texts, links):
            if not text or not link:
                continue
            
            # Extract domain
            try:
                from urllib.parse import urlparse
                domain = urlparse(link).netloc
                # Clean domain (remove www.)
                domain = domain.replace("www.", "")
            except:
                domain = "other"
            
            if domain not in domain_snippets:
                domain_snippets[domain] = []
            domain_snippets[domain].append(text)
        
        # Add grouped snippets as separate sources (limit to top domains)
        top_domains = sorted(domain_snippets.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        
        for domain, snippets in top_domains:
            combined_snippet = " | ".join(snippets)
            self.add_person(
                person_id=person_id,
                name=name,
                description=combined_snippet,
                source=f"web_{domain}",
                rebuild_index=False  # Don't rebuild after each
            )
        
        # Rebuild index once after all additions
        if top_domains:
            self.build_index()
    
    def add_from_search_results_batch(self, search_results_list):
        """
        Add multiple persons from a list of search result JSONs
        
        Args:
            search_results_list: List of search result dicts
        """
        for search_json in search_results_list:
            self.add_from_search_results(search_json, person_id=None, name=None)
        
        print(f"✅ Batch processed {len(search_results_list)} search results")


# ==================== Example Usage ====================

def demo_usage():
    """Demonstrate how to use the Person Database"""
    
    print("🚀 Starting Person Database Demo\n")
    
    # Initialize database
    db = PersonDatabase(db_path="my_person_db")
    
    # Try to load existing data
    db.load_complete()
    
    # ========== Example 1: Manual Adding ==========
    print("\n" + "="*70)
    print("📝 Example 1: Manually adding persons")
    print("="*70)
    
    db.add_person(
        person_id="p001",
        name="Alice Johnson",
        description="Senior Software Engineer at TechCorp. Expert in Python, Machine Learning, and distributed systems. 8 years of experience building scalable applications.",
        source="linkedin"
    )
    
    # ========== Example 2: Adding from Web Search Results ==========
    print("\n" + "="*70)
    print("📝 Example 2: Adding from web search results JSON (NEW FORMAT)")
    print("="*70)
    
    # Your actual search result JSON with new structure
    search_result_json = {
        "query": "Mobasserul Haque",
        "total_results": 10,
        "texts": [
            "Mobasserul Haque. Mobasser Haque. Graduation year : 2026 · LinkedIn.",
            "Related People · Greg Herschlag · Cayden Tu · James Li · Rachel Song · Yizhe (Leo) Chen · Mobasserul Haque · Ammemah Naeem.",
            "Mohammed Mobasserul Haque; Divyansh Agrawal; Pranat Dixit; Budhaditya Bhattacharyya. All Authors. Sign In or Purchase. 2. Cites in. Papers. 284. Full. Text ...",
            "Mobasserul Haque. MS Data Science Student@ Duke University'26 | GenAI Research @ Duke University. 8mo. Report this ...",
            "Mohammed Mobasserul Haque Student of Vellore Institute of. Technology, 3rd-year Electronics and Communication Engineering. M. Manimozhi ..."
        ],
        "links": [
            "https://datascience.duke.edu/people/mobasser-haque/",
            "https://bigdata.duke.edu/projects/alumni-engagement-forecasting/",
            "https://ieeexplore.ieee.org/document/9885574/",
            "https://www.linkedin.com/posts/xianjing-jin-huang_award-ai-machinelearning-activity-7299536739532980225-DYpd",
            "https://www.ijitee.org/wp-content/uploads/papers/v8i11/J90770881019.pdf"
        ]
    }
    
    # Add person from search results
    db.add_from_search_results(search_result_json)
    
    # ========== Example 3: Batch Adding Multiple Search Results ==========
    print("\n" + "="*70)
    print("📝 Example 3: Batch adding multiple search results")
    print("="*70)
    
    multiple_search_results = [
        {
            "query": "Bob Smith",
            "texts": [
                "Product Manager with focus on AI/ML products. Former engineer turned PM.",
                "Led product launches at Google and Microsoft."
            ],
            "links": [
                "https://linkedin.com/in/bobsmith",
                "https://bobsmith.com"
            ]
        },
        {
            "query": "Carol White",
            "texts": [
                "Data Scientist specializing in NLP and computer vision. PhD in Machine Learning from Stanford.",
                "Author of 'Deep Learning in Practice'."
            ],
            "links": [
                "https://linkedin.com/in/carolwhite",
                "https://carolwhite.com"
            ]
        }
    ]
    
    db.add_from_search_results_batch(multiple_search_results)
    
    # Show statistics
    db.print_statistics()
    
    # List all persons
    print("\n👥 All persons in database:")
    for person in db.list_all_persons():
        print(f"  • {person['name']} ({person['id']}) - {person['num_sources']} sources: {', '.join(person['sources'])}")
    
    # Search examples
    print("\n🔍 Search Examples:\n")
    
    queries = [
        "Who has Duke University experience?",
        "Find someone with machine learning research",
        "Who is a product manager?",
        "Deep learning and 5G systems"
    ]
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        print("-" * 60)
        results = db.search(query, top_k=3)
        for i, result in enumerate(results, 1):
            print(f"{i}. [{result['metadata']['name']}] {result['text'][:80]}...")
            print(f"   Distance: {result['distance']:.4f}")
    
    # Get specific person
    print("\n\n👤 Get specific person (Mobasserul Haque):")
    print("-" * 60)
    person = db.get_person_by_name("Mobasserul Haque")
    if person:
        print(f"Name: {person['name']}")
        print(f"ID: {person['id']}")
        print(f"Descriptions:")
        for desc in person['descriptions']:
            print(f"  [{desc['source']}] {desc['text'][:100]}...")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    demo_usage()