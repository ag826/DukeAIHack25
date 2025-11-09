import dotenv

dotenv.load_dotenv()
import logging

logging.basicConfig(level=logging.DEBUG)
import sys, types
import json
import io
import os
from typing import List, Optional

import numpy as np
import torch

from fastapi import FastAPI, UploadFile, Form, HTTPException, Query, File
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment  # To convert WebM to WAV
from typing import Dict



import firebase_admin
from firebase_admin import credentials, firestore

import tempfile

from . import Audio_to_text
from . import LLM_json_generator
from . import Named_Transcript
from . import RAG_FRAMEWORK as RAGF

from pydantic import BaseModel


# ---- config ----
SERVICE_ACCOUNT = "backend/ai-hackathon-4e25e-firebase-adminsdk-fbsvc-5557fc6879.json"
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

# allow your frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Dummy utilities ----------------

def make_dummy_embedding(dim: int = 192) -> np.ndarray:
    """Generate a reproducible dummy embedding."""
    np.random.seed(42)
    return np.random.rand(dim).astype("float32")



def convert_webm_to_wav(webm_path: str, wav_path: str) -> None:
    """
    Convert a WebM file to WAV using pydub.
    """
    try:
        # Load WebM file
        audio = AudioSegment.from_file(webm_path, format="webm")
        # Export to WAV format
        audio.export(wav_path, format="wav")
        print(f"Converted {webm_path} to {wav_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert WebM to WAV: {e}")

def webm_to_mp3(webm_file, output_path):
    """Converts WebM file to MP3 format"""
    audio = AudioSegment.from_file(webm_file, format="webm")
    audio.export(output_path, format="wav")
    return output_path

@app.post("/process-audio")
async def process_audio(
    userId: str = Form(...),
    timestamp: str = Form(...),
    filePath: UploadFile = File(...),   # 👈 this was str before
):
    """
    Receive an uploaded audio file (sent as 'filePath' from frontend),
    save it locally, run transcription + LLM, save to Firestore.
    """
    try:
        # pick a safe filename
        original_name = os.path.basename(filePath.filename)
        # or build your own name from timestamp
        filename = f"data/recording_{timestamp}.webm"
        tmp_dir = tempfile.gettempdir()
        tmp_audio_path = f"data/recording_{timestamp}.webm"

        print(f"Saving audio to: {tmp_audio_path}")

        # save uploaded file to temp
        with open(tmp_audio_path, "wb") as f:
            f.write(await filePath.read())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {e}")

    # 2) Run the transcription script
    audio_file = webm_to_mp3(f"data/recording_{timestamp}.webm", f"data/recording_{timestamp}.wav")
    transcript_path = os.path.join("data/transcript.txt")
    
    try:
      Audio_to_text.get_text(audio_file, transcript_path)
      transcript_path= Named_Transcript.rename_speakers_in_transcript(transcript_path)

    except Exception as e:
      raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    # 3) Run LLM script for conversation mindmap
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

        mindmap_data = LLM_json_generator.generate_conversation_mindmap_json(
            transcript_text,
            source_file=os.path.basename(transcript_path),
        )
        output_path = "data/mindmap_test.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(mindmap_data, f, indent=2)

        print(f"✅ Mind map JSON generated and saved to {output_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM mindmap generation failed: {e}")


    speakers = []
    if "participants" in mindmap_data and isinstance(mindmap_data["participants"], list):
        speakers = [p.get("name") for p in mindmap_data["participants"] if p.get("name")]

    # 4) Save to Firestore
    convo_doc = {
        "userId": userId,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "speakers": speakers,
        "mindmap": mindmap_data,
        "graph": mindmap_data.get("graph") or {},
        "sourceTimestamp": timestamp,
    }

    try:
        db.collection("conversations").add(convo_doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save conversation: {e}")

    return {"status": "ok", "speakers": speakers}

 
    
def normalize_timestamp(ts):
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    if hasattr(ts, "to_datetime"):
        return ts.to_datetime().isoformat()
    return ts

def build_graph_from_mindmap(mindmap):
    """
    Your new mindmap looks like:
      {
        "participants": [...],
        "main_topics": [...],
        "relationships": [...]
      }

    We'll turn that into:
      {
        "nodes": [...],
        "edges": [...]
      }
    so React can keep using conv.graph
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # topics → nodes
    for idx, topic in enumerate(mindmap.get("main_topics", [])):
        nodes.append({
            "id": f"topic-{idx}",
            "label": topic.get("topic", f"Topic {idx+1}"),
            "speaker": topic.get("introduced_by"),
            "type": "Topic",
        })
        # subtopics → nodes + edge from topic
        for sidx, sub in enumerate(topic.get("subtopics", [])):
            sub_id = f"topic-{idx}-sub-{sidx}"
            nodes.append({
                "id": sub_id,
                "label": sub.get("subtopic", f"Subtopic {sidx+1}"),
                "speaker": sub.get("introduced_by"),
                "type": "Subtopic",
            })
            edges.append({
                "from": f"topic-{idx}",
                "to": sub_id,
                "type": sub.get("stance", "elaboration"),
            })

    # relationships → edges
    for rel in mindmap.get("relationships", []):
        edges.append({
            "from": rel.get("from"),
            "to": rel.get("to"),
            "type": rel.get("type", "relation"),
        })

    return {"nodes": nodes, "edges": edges}


@app.get("/get-conversations")
def get_conversations(
    user_id: str = Query(..., description="Firebase Auth UID"),
):
    # try to order by timestamp
    try:
        convs_ref = (
            db.collection("conversations")
            .where("userId", "==", user_id)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )
    except Exception:
        convs_ref = db.collection("conversations").where("userId", "==", user_id)

    docs = convs_ref.stream()

    results: List[Dict[str, Any]] = []

    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id

        # normalize timestamp
        if "timestamp" in data:
            data["timestamp"] = normalize_timestamp(data["timestamp"])

        mindmap_val = data.get("mindmap")
        speakers = data.get("speakers") or []

        parsed_mindmap: Optional[Dict[str, Any]] = None
        graph: Optional[Dict[str, Any]] = None

        # CASE 1: new style — already a dict
        if isinstance(mindmap_val, dict):
            parsed_mindmap = mindmap_val

            # extract speakers from participants if not already set
            if not speakers and isinstance(parsed_mindmap.get("participants"), list):
                speakers = [
                    p.get("name")
                    for p in parsed_mindmap["participants"]
                    if isinstance(p, dict) and p.get("name")
                ]

            # build a graph so frontend can do conv.graph
            graph = build_graph_from_mindmap(parsed_mindmap)

        # CASE 2: old style — JSON string
        elif isinstance(mindmap_val, str):
            try:
                tmp = json.loads(mindmap_val)
            except json.JSONDecodeError:
                tmp = None

            # if it was a list: [ { ... } ]
            if isinstance(tmp, list) and tmp:
                parsed_mindmap = tmp[0]
            elif isinstance(tmp, dict):
                parsed_mindmap = tmp

            if parsed_mindmap:
                if not speakers and isinstance(parsed_mindmap.get("participants"), list):
                    speakers = [
                        p.get("name")
                        for p in parsed_mindmap["participants"]
                        if isinstance(p, dict) and p.get("name")
                    ]
                graph = build_graph_from_mindmap(parsed_mindmap)

        # CASE 3: old style — list in Firestore
        elif isinstance(mindmap_val, list) and mindmap_val:
            # take first element
            first = mindmap_val[0]
            if isinstance(first, dict):
                parsed_mindmap = first
                if not speakers and isinstance(first.get("participants"), list):
                    speakers = [
                        p.get("name")
                        for p in first["participants"]
                        if isinstance(p, dict) and p.get("name")
                    ]
                graph = build_graph_from_mindmap(first)

        # write cleaned fields back
        data["speakers"] = speakers
        if parsed_mindmap is not None:
            data["mindmap"] = parsed_mindmap
        if graph is not None:
            data["graph"] = graph

        results.append(data)

    return {
        "count": len(results),
        "conversations": results,
    }
    
# we'll keep a global rag_engine
rag_engine = None

@app.on_event("startup")
def load_rag():
    """build once when server starts"""
    global rag_engine
    print("🟡 building RAG engine...")
    try:
        # you need to expose a function in RAG_FRAMEWORK that returns
        # (person_db, mindmap_index, mindmap_chunks)
        # I'll show the pattern below
        rag_engine = RAGF.build_rag_engine()
        print("✅ RAG engine ready")
    except Exception as e:
        print("❌ failed to build RAG engine:", e)
        rag_engine = None


@app.post("/chat")
async def chat(payload: dict):
    """
    payload = {
      "userId": "...",
      "message": "...",
      "history": [...]
    }
    """
    print("📩 /chat called with:", payload)
    if rag_engine is None:
      print('hi')
      raise HTTPException(status_code=500, detail="RAG not initialized")
    print("hi")
    user_msg = payload.get("message", "")
    history = payload.get("history", [])

    try:
        reply = RAGF.answer_with_rag(rag_engine, user_msg, history)
    except Exception as e:
        print("❌ RAG error:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"reply": reply}
    
@app.get("/user-profile")
def get_user_profile(user_id: str = Query(..., description="Firebase Auth UID"), email: str | None = None):
    """
    Return (and lazily create) the user profile document.
    This mirrors what the frontend was doing with Firestore directly.
    """
    users_ref = db.collection("users").document(user_id)
    snap = users_ref.get()

    if not snap.exists:
      # create a minimal user doc
      payload = {
          "hasVoiceProfile": False,
          "createdAt": firestore.SERVER_TIMESTAMP,
      }
      if email:
          payload["email"] = email
      users_ref.set(payload, merge=True)
      return {
          "userId": user_id,
          "email": email,
          "hasVoiceProfile": False,
          "created": True,
      }

    data = snap.to_dict() or {}
    return {
        "userId": user_id,
        "email": data.get("email", email),
        "hasVoiceProfile": bool(data.get("hasVoiceProfile", False)),
        "created": False,
    }
    
@app.post("/voice-profile")
async def create_voice_profile(
    user_id: str = Form(...),
    sample_0: Optional[UploadFile] = None,
    sample_1: Optional[UploadFile] = None,
    sample_2: Optional[UploadFile] = None,
):
    """
    Dummy version — doesn't process audio, just simulates embedding creation and saves to Firestore.
    """

    # (Optional) read one file just to verify data received
    total_bytes = 0
    for f in [sample_0, sample_1, sample_2]:
        if f:
            b = await f.read()
            total_bytes += len(b)

    # create fake embedding vector
    fake_emb = make_dummy_embedding(256)
    fake_metadata = {
        "hasVoiceProfile": True,
        "voiceEmbedding": fake_emb.tolist(),
        "voiceEmbeddingModel": "dummy-v0.1",
        "totalUploadedBytes": total_bytes,
        "status": "dummy_saved",
    }

    # save to Firestore
    try:
        db.collection("users").document(user_id).set(fake_metadata, merge=True)
        print(f"✅ Saved dummy embedding for {user_id} ({len(fake_emb)}-dim vector)")
    except Exception as e:
        print("🔥 Firestore write failed:", e)
        raise HTTPException(status_code=500, detail=f"Firestore error: {e}")

    return {
        "status": "ok",
        "dim": len(fake_emb),
        "uploaded_kb": round(total_bytes / 1024, 2),
        "message": "Dummy embedding saved to Firestore",
    }


@app.post("/voice-profile")
async def create_voice_profile(
    user_id: str = Form(...),
    sample_0: Optional[UploadFile] = None,
    sample_1: Optional[UploadFile] = None,
    sample_2: Optional[UploadFile] = None,
):

    return {"status": "ok", "dim": 5}
