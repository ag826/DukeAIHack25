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


import firebase_admin
from firebase_admin import credentials, firestore

import tempfile

from . import Audio_to_text
from . import LLM_json_generator

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

@app.get("/get-conversations")
def get_conversations(
    user_id: str = Query(..., description="Firebase Auth UID"),
):
    """
    Return conversations for a user, but also parse the `mindmap` field if it's a JSON string.
    """
    # try to order by timestamp, fallback if no index
    try:
        convs_ref = (
            db.collection("conversations")
            .where("userId", "==", user_id)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )
    except Exception:
        convs_ref = db.collection("conversations").where("userId", "==", user_id)

    docs = convs_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id

        # normalize timestamp
        if "timestamp" in data:
            data["timestamp"] = normalize_timestamp(data["timestamp"])

        # ---------- NEW PART: parse mindmap ----------
        parsed_mindmap = None
        graph = None
        speakers = data.get("speakers")

        mindmap_val = data.get("mindmap")
        if isinstance(mindmap_val, str):
            # it's a JSON string, try to parse
            try:
                parsed = json.loads(mindmap_val)
                # expect a list like your example
                if isinstance(parsed, list) and len(parsed) > 0:
                    parsed_mindmap = parsed
                    # take speakers from first block if not already set
                    if not speakers and isinstance(parsed[0], dict):
                        speakers = parsed[0].get("speakers")
                    # take graph from first block
                    first_graph = parsed[0].get("graph") if isinstance(parsed[0], dict) else None
                    if first_graph:
                        graph = first_graph
            except json.JSONDecodeError:
                # leave parsed_mindmap = None
                parsed_mindmap = None
        elif isinstance(mindmap_val, list):
            # somehow already stored as array
            parsed_mindmap = mindmap_val
            if len(mindmap_val) > 0 and isinstance(mindmap_val[0], dict):
                if not speakers:
                    speakers = mindmap_val[0].get("speakers")
                graph = mindmap_val[0].get("graph")

        # set cleaned fields
        data["speakers"] = speakers or []
        if parsed_mindmap is not None:
            data["mindmap"] = parsed_mindmap
        # expose a top-level graph so React can do conv.graph
        if graph is not None:
            data["graph"] = graph

        results.append(data)

    return {
        "count": len(results),
        "conversations": results,
    }
    
    

    
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

'''

def webm_bytes_to_tensor(file_bytes: bytes) -> torch.Tensor:
    """
    Try to convert a .webm to a 16k mono tensor using pydub/ffmpeg.
    If ffmpeg is not installed, this will raise.
    """
    from pydub import AudioSegment  # import here so we can catch errors above

    audio = AudioSegment.from_file(io.BytesIO(file_bytes), format="webm")
    audio = audio.set_channels(1).set_frame_rate(16000)
    out_io = io.BytesIO()
    audio.export(out_io, format="wav")
    out_io.seek(0)

    # turn wav bytes into numpy
    audio_wav = AudioSegment.from_wav(out_io)
    samples = np.array(audio_wav.get_array_of_samples()).astype(np.float32)
    samples = samples / (2 ** 15)
    tensor = torch.from_numpy(samples).unsqueeze(0)
    return tensor


def wav_bytes_to_tensor(file_bytes: bytes) -> torch.Tensor:
    """
    Simpler path: if the frontend already gives us 16k mono wav, use this.
    """
    from pydub import AudioSegment

    audio = AudioSegment.from_file(io.BytesIO(file_bytes), format="wav")
    audio = audio.set_channels(1).set_frame_rate(16000)
    samples = np.array(audio.get_array_of_samples()).astype(np.float32)
    samples = samples / (2 ** 15)
    tensor = torch.from_numpy(samples).unsqueeze(0)
    return tensor


def average_embeddings(embs: List[np.ndarray]) -> np.ndarray:
    stacked = np.stack(embs, axis=0)
    return stacked.mean(axis=0).astype("float32")
    
@app.post("/voice-profile")
async def create_voice_profile(
    user_id: str = Form(...),
    sample_0: Optional[UploadFile] = None,
    sample_1: Optional[UploadFile] = None,
    sample_2: Optional[UploadFile] = None,
):
    # collect uploaded files
    files = [sample_0, sample_1, sample_2]
    file_bytes_list: List[bytes] = []

    for f in files:
        if f is None:
            continue
        b = await f.read()
        file_bytes_list.append(b)

    if not file_bytes_list:
        # frontend sent nothing
        raise HTTPException(status_code=400, detail="no samples uploaded")

    emb_list: List[np.ndarray] = []

    for idx, b in enumerate(file_bytes_list):
        # try webm first
        wav_tensor: torch.Tensor
        try:
            print(f"[backend] trying to decode sample {idx} as webm...")
            wav_tensor = webm_bytes_to_tensor(b)
        except Exception as e_webm:
            # if that fails, try wav
            print(f"[backend] webm decode failed: {e_webm!r}")
            try:
                print(f"[backend] trying to decode sample {idx} as wav instead...")
                wav_tensor = wav_bytes_to_tensor(b)
            except Exception as e_wav:
                print(f"[backend] wav decode also failed: {e_wav!r}")
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Could not decode audio. Make sure ffmpeg is installed "
                        "or send 16k mono wav from the frontend."
                    ),
                )

        # now we have a tensor -> embedding
        with torch.no_grad():
            emb = spk_model.encode_batch(wav_tensor)
        emb_list.append(emb.squeeze().cpu().numpy())

    # avg embedding for stability
    avg_emb = average_embeddings(emb_list)

    # save ONLY the embedding to Firestore
    db.collection("users").document(user_id).set(
        {
            "hasVoiceProfile": True,
            "voiceEmbedding": 
            "voiceEmbeddingModel": "speechbrain/spkrec-ecapa-voxceleb",
        },
        merge=True,
    )

    return {"status": "ok", "dim": len(avg_emb)}
'''