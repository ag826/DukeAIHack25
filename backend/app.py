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
from fastapi.responses import HTMLResponse



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
async def process_audio_phase1(
    userId: str = Form(...),
    timestamp: str = Form(...),
    filePath: UploadFile = File(...),
):
    """
    Phase 1:
    - receive audio
    - save it
    - convert to wav
    - transcribe to data/transcript_{timestamp}.txt
    - run Named_Transcript.summarize_speaker_content(...)
    - return the summary + transcript_path
    Frontend will show this summary to the user and collect a "real name" mapping.
    Then frontend will call /process-audio-final.
    """
    # 1) save uploaded file
    os.makedirs("data", exist_ok=True)
    raw_webm_path = f"data/recording_{timestamp}.webm"
    try:
        with open(raw_webm_path, "wb") as f:
            f.write(await filePath.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {e}")

    # 2) convert → wav
    wav_path = f"data/recording_{timestamp}.wav"
    try:
        webm_to_mp3(raw_webm_path, wav_path)  # your helper exports as wav
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert audio: {e}")

    # 3) transcribe
    transcript_path = f"data/transcript_{timestamp}.txt"
    try:
        Audio_to_text.get_text(wav_path, transcript_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    # 4) read transcript text
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read transcript: {e}")

    # 5) summarize speakers
    try:
        # adjust this line if your summarize function wants a path instead
        speaker_summary = Named_Transcript.summarize_speaker_content(transcript_text)
        # speaker_summary should be something like:
        # {
        #   "speakers": {
        #       "SPEAKER_00": ["talked about X", ...],
        #       "SPEAKER_01": ...
        #   }
        # }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to summarize speakers: {e}")

    # 6) return summary + transcript path so frontend can send it back
    return {
        "status": "ok",
        "transcript_path": transcript_path,
        "audio_path": wav_path,
        "speaker_summary": speaker_summary,
        "message": "Transcript created. Please map speakers and call /process-audio-final.",
    }
    
class SpeakerMapping(BaseModel):
    transcript_path: str
    userId: str
    timestamp: str
    mapping: Dict[str, str]  # e.g. {"SPEAKER_00": "Andre Cole", "SPEAKER_01": "Adil Gazder"}

@app.post("/process-audio-final")
def process_audio_phase2(payload: SpeakerMapping):
    """
    Phase 2 (after user mapped speakers):
    - load the transcript we saved in phase 1
    - apply Named_Transcript.apply_speaker_mapping(...)
    - run LLM_json_generator to build mindmap
    - save to Firestore
    - return result
    """
    transcript_path = payload.transcript_path
    user_id = payload.userId
    timestamp = payload.timestamp
    mapping = payload.mapping

    # 1) load transcript text
    if not os.path.exists(transcript_path):
        raise HTTPException(status_code=404, detail="Transcript not found, run /process-audio first")

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    # 2) apply mapping
    try:
        # adjust if your function wants a path instead of text
        final_transcript = Named_Transcript.apply_speaker_mapping(transcript_text, mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply speaker mapping: {e}")

    # (optional) overwrite transcript file with mapped names
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(final_transcript)

    # 3) run LLM to get mindmap
    try:
        mindmap_data = LLM_json_generator.generate_conversation_mindmap_json(
            final_transcript,
            source_file=os.path.basename(transcript_path),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM mindmap generation failed: {e}")

    # 4) extract speakers from mindmap
    speakers = []
    if "participants" in mindmap_data and isinstance(mindmap_data["participants"], list):
        speakers = [p.get("name") for p in mindmap_data["participants"] if p.get("name")]

    # 5) save to Firestore
    convo_doc = {
        "userId": user_id,
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

    return {
        "status": "ok",
        "speakers": speakers,
        "mindmap": mindmap_data,
    }
    
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
    
 
@app.get("/mindmap-viewer")
def mindmap_viewer(
    user_id: str = Query(..., description="Firebase Auth UID"),
    conv_id: Optional[str] = Query(None, description="Conversation document ID"),
):
    """
    Return an HTML page that renders the stored mindmap for this user/conversation.
    It mirrors your write_mindmap_html_with_edge_attribution.py template,
    but uses Firestore data instead of reading mindmap.json from disk.
    """
    # 1) get the conversation
    doc_data = None

    if conv_id:
        doc_ref = db.collection("conversations").document(conv_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
        doc_data = snap.to_dict()
        # optional: make sure it belongs to user
        if doc_data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Conversation does not belong to user")
    else:
        # pick latest for this user
        try:
            q = (
                db.collection("conversations")
                .where("userId", "==", user_id)
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
        except Exception:
            # if no composite index, fall back to just where
            q = db.collection("conversations").where("userId", "==", user_id).limit(1)

        docs = list(q.stream())
        if not docs:
            raise HTTPException(status_code=404, detail="No conversations for this user")
        doc_data = docs[0].to_dict()

    # 2) pull mindmap – in your Firestore it's already a JSON object
    mindmap_val = doc_data.get("mindmap")
    if mindmap_val is None:
        # just give an empty skeleton
        mindmap_val = {
            "conversation_title": "Empty Mindmap",
            "main_topics": [],
            "relationships": [],
            "metadata": {},
        }

    # if for some reason it was stored as string, parse it
    if isinstance(mindmap_val, str):
        try:
            mindmap_val = json.loads(mindmap_val)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="mindmap field is not valid JSON")

    # 3) turn it into js literal
    data_js = json.dumps(mindmap_val, ensure_ascii=False)

    # 4) build the same HTML you had
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Conversation Mind Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://unpkg.com/vis-network@9.1.7/dist/vis-network.min.js"></script>
<link href="https://unpkg.com/vis-network@9.1.7/styles/vis-network.min.css" rel="stylesheet"/>

<style>
  :root {{
    --bg: #ffffff;
    --fg: #263238;
    --edge: #CFD8DC;
    --root: #B2DFDB;
    --topic: #C5CAE9;
    --subtopic: #BBDEFB;
    --leaf: #E1F5FE;
    --highlight: #FFE082;
  }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }}
  .toolbar {{
    display:flex; gap:.75rem; flex-wrap:wrap; align-items:center;
    padding:.75rem 1rem; border-bottom:1px solid #ECEFF1; position:sticky; top:0; background:rgba(255,255,255,.97); z-index:10;
  }}
  .toolbar label {{ font-size:.9rem; opacity:.9; }}
  .toolbar input[type="range"] {{ width:160px; vertical-align:middle; }}
  .toolbar input[type="text"] {{ width:220px; padding:.4rem .55rem; border:1px solid #ECEFF1; border-radius:8px; }}
  .toolbar select {{ padding:.35rem .5rem; border:1px solid #ECEFF1; border-radius:8px; }}
  .pill {{ display:inline-block; padding:.15rem .45rem; font-size:.75rem; border-radius:999px; background:#EEF2F7; margin-left:.35rem; }}
  #graph {{ height: calc(100vh - 64px); }}
  .note {{ padding:.35rem 1rem; font-size:.85rem; color:#607D8B; border-top:1px dashed #ECEFF1; }}
</style>
</head>

<body>
  <div class="toolbar">
    <label>Branch
      <select id="topic"></select>
    </label>

    <label>Depth
      <input id="depth" type="range" min="1" max="8" step="1" value="8"/>
      <span id="depthVal" class="pill">8</span>
    </label>

    <label>Wrap
      <input id="wrap" type="range" min="14" max="36" step="1" value="36"/>
      <span id="wrapVal" class="pill">36</span>
    </label>

    <label>Layout
      <select id="direction">
        <option value="UD" selected>Top → Down</option>
        <option value="LR">Left → Right</option>
      </select>
    </label>

    <label><input id="hideX" type="checkbox" checked/> Hide cross-links</label>
    <label><input id="edgeLabels" type="checkbox" checked/> Show speaker labels on edges</label>

    <label>Highlight
      <input id="search" type="text" placeholder="type to highlight…"/>
    </label>

    <span id="stats" class="pill"></span>
  </div>

  <div id="graph"></div>
  <div class="note">Tip: Choose one branch (topic) and keep depth at 2–3 for clarity.</div>

<script>
  // -------- Embedded Data from Firestore --------
  const DATA = {data_js};

  const topicSel   = document.getElementById('topic');
  const depthEl    = document.getElementById('depth');
  const depthVal   = document.getElementById('depthVal');
  const wrapEl     = document.getElementById('wrap');
  const wrapVal    = document.getElementById('wrapVal');
  const dirEl      = document.getElementById('direction');
  const hideX      = document.getElementById('hideX');
  const edgeLabels = document.getElementById('edgeLabels');
  const searchEl   = document.getElementById('search');
  const statsEl    = document.getElementById('stats');

  const TOPICS = ["All Topics", ...(DATA.main_topics||[]).map(t => t.topic).filter(Boolean)];
  TOPICS.forEach(t => {{
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    topicSel.appendChild(opt);
  }});

  depthEl.addEventListener('input', () => depthVal.textContent = depthEl.value);
  wrapEl .addEventListener('input', () => wrapVal.textContent  = wrapEl.value);

  function wrapLabel(s, width) {{
    s = (s||"").trim().replace(/\\s+/g, " ");
    if (s.length <= width) return s;
    const out = []; let line = [], ln = 0;
    for (const w of s.split(" ")) {{
      const extra = line.length ? 1 : 0;
      if (ln + w.length + extra > width) {{
        out.push(line.join(" ")); line=[w]; ln = w.length;
      }} else {{ line.push(w); ln += w.length + extra; }}
    }}
    if (line.length) out.push(line.join(" "));
    return out.join("<br>");
  }}

  function tint(hex, sentiment) {{
    if (!sentiment || sentiment === "neutral") return hex;
    const r = parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
    let R=r,G=g,B=b;
    if (sentiment === "positive") {{ R=Math.min(255, Math.round(r*1.10)); G=Math.min(255, Math.round(g*1.10)); B=Math.min(255, Math.round(b*1.10)); }}
    if (sentiment === "negative") {{ R=Math.round(r*0.80); G=Math.round(g*0.80); B=Math.round(b*0.80); }}
    return "#" + [R,G,B].map(v => v.toString(16).padStart(2,"0")).join("");
  }}

  function truncateList(list, maxItems=3) {{
    if (!Array.isArray(list)) return "";
    const items = list.filter(Boolean);
    if (items.length <= maxItems) return items.join(", ");
    return items.slice(0, maxItems).join(", ") + " +" + (items.length - maxItems);
  }}

  function buildData(opts) {{
    const {{ selectedTopic = "All Topics", maxDepth = 10, hideCrosslinks = false, wrap = 36, showEdgeLabels = true }} = opts;
    const nodes = new vis.DataSet();
    const edges = new vis.DataSet();

    const palette = {{
      root:     getComputedStyle(document.documentElement).getPropertyValue('--root').trim(),
      topic:    getComputedStyle(document.documentElement).getPropertyValue('--topic').trim(),
      subtopic: getComputedStyle(document.documentElement).getPropertyValue('--subtopic').trim(),
      leaf:     getComputedStyle(document.documentElement).getPropertyValue('--leaf').trim()
    }};

    const addNode = (id, role, label, sentiment) => {{
      if (!id || nodes.get(id)) return;
      const color = tint(palette[role] || palette.leaf, sentiment);
      nodes.add({{
        id,
        label: wrapLabel(label||id, wrap),
        title: label||id,
        color,
        shape: "box",
        margin: 10,
        font: {{ multi: "html", size: 14 }}
      }});
    }};

    const addEdge = (from, to, label, title) => {{
      if (!from || !to) return;
      const e = {{ from, to }};
      if (showEdgeLabels && label) e.label = label;
      if (title) e.title = title;
      edges.add(e);
    }};

    const root = DATA.root || DATA.title || "Mind Map";
    addNode(root, "root", root);

    function addTopicBranch(topicObj) {{
      const tname = topicObj.topic;
      addNode(tname, "topic", tname, topicObj.sentiment);

      let topicEdgeLabel = "";
      let topicEdgeTitle = "";
      const introBy = topicObj.introduced_by;
      const introAt = topicObj.introduced_at;
      if (introBy) {{
        topicEdgeLabel = "introduced by " + introBy;
        topicEdgeTitle = "<b>introduced by</b>: " + introBy + (introAt ? "<br><b>at</b>: " + introAt : "");
      }}
      addEdge(root, tname, topicEdgeLabel, topicEdgeTitle);

      for (const s of (topicObj.subtopics || [])) {{
        const sname = s.subtopic;
        addNode(sname, "subtopic", sname, s.sentiment);

        const whoList = (s.discussed_by || []).filter(Boolean);
        const stance  = s.stance;
        const labelWho = truncateList(whoList, 2);
        let subEdgeLabel = "";
        let subEdgeTitle = "";
        if (labelWho || stance) {{
          const parts = [];
          if (labelWho) parts.push("discussed by " + labelWho);
          if (stance)   parts.push("stance: " + stance);
          subEdgeLabel = parts.join(" · ");
          subEdgeTitle = parts.map(p => "<b>" + p.split(":")[0] + "</b>: " + (p.split(":")[1] || "").trim()).join("<br>");
        }}
        addEdge(tname, sname, subEdgeLabel, subEdgeTitle);

        const entities = Array.isArray(s.entities) ? s.entities : [];
        const notes    = Array.isArray(s.notes) ? s.notes : [];
        const leaves   = [];
        for (const x of entities) {{
          if (typeof x === 'string') leaves.push(x);
          else if (x && (x.name || x.text)) leaves.push(x.name || x.text);
        }}
        for (const y of notes) {{
          if (typeof y === 'string') leaves.push(y);
          else if (y && (y.name || y.text)) leaves.push(y.name || y.text);
        }}
        for (const leaf of leaves) {{
          addNode(leaf, "leaf", leaf, null);
          addEdge(sname, leaf, "", "");
        }}
      }}
    }}

    if (selectedTopic === "All Topics") {{
      for (const t of (DATA.main_topics || [])) addTopicBranch(t);
    }} else {{
      const t = (DATA.main_topics || []).find(x => x.topic === selectedTopic);
      if (t) addTopicBranch(t);
    }}

    if (!hideCrosslinks) {{
      for (const r of (DATA.relationships || [])) {{
        const frm = r.from, to = r.to; if (!frm || !to) continue;
        addNode(frm, "leaf", frm, null);
        addNode(to,  "leaf", to,  null);
        let lbl = "";
        let ttl = "";
        if (r.type) lbl = r.type;
        const by = r.initiated_by, at = r.initiated_at;
        const extras = [];
        if (by) extras.push("by " + by);
        if (at) extras.push("at " + at);
        if (extras.length) lbl = (lbl ? lbl + " · " : "") + extras.join(" ");
        if (r.type) ttl += "<b>type</b>: " + r.type;
        if (by)     ttl += (ttl ? "<br>" : "") + "<b>by</b>: " + by;
        if (at)     ttl += (ttl ? "<br>" : "") + "<b>at</b>: " + at;
        addEdge(frm, to, lbl, ttl);
      }}
    }}

    // depth pruning
    const adj = new Map(); nodes.forEach(n => adj.set(n.id, []));
    edges.forEach(e => {{ if (adj.has(e.from)) adj.get(e.from).push(e.to); }});
    const keep = new Set([root]); let frontier = [root], d=0;
    while (frontier.length && d < maxDepth) {{
      const nxt = [];
      for (const u of frontier) {{
        const kids = adj.get(u) || [];
        for (const v of kids) if (!keep.has(v)) {{ keep.add(v); nxt.push(v); }}
      }}
      frontier = nxt; d += 1;
    }}
    const n2 = new vis.DataSet(nodes.get().filter(n => keep.has(n.id)));
    const kept = new Set(n2.getIds());
    const e2 = new vis.DataSet(edges.get().filter(e => kept.has(e.from) && kept.has(e.to)));

    return {{ nodes: n2, edges: e2 }};
  }}

  const container = document.getElementById('graph');

  function render() {{
    const opts = {{
      selectedTopic: topicSel.value || "All Topics",
      maxDepth: parseInt(depthEl.value, 10),
      hideCrosslinks: hideX.checked,
      wrap: parseInt(wrapEl.value, 10),
      showEdgeLabels: edgeLabels.checked
    }};
    const data = buildData(opts);

    const options = {{
      layout: {{
        hierarchical: {{
          enabled: true,
          direction: dirEl.value,
          sortMethod: "hubsize",
          levelSeparation: 230,
          nodeSpacing: 210,
          treeSpacing: 280
        }}
      }},
      physics: {{ enabled: false }},
      nodes: {{
        shape: "box",
        color: {{
          border: "#ECEFF1",
          highlight: {{ border: "#90CAF9", background: "#E3F2FD" }}
        }},
        widthConstraint: {{ maximum: 260 }}
      }},
      edges: {{
        smooth: {{ type: "continuous" }},
        color: {{ color: getComputedStyle(document.documentElement).getPropertyValue('--edge').trim() }},
        arrows: {{ to: {{ enabled: false }} }},
        font: {{ align: "top", size: 11, color: "#546E7A", background: "#FAFAFA" }}
      }},
      interaction: {{ hover: true, tooltipDelay: 80 }}
    }};

    container.innerHTML = "";
    const network = new vis.Network(container, data, options);

    const q = (searchEl.value || "").trim().toLowerCase();
    if (q) {{
      const ids = data.nodes.getIds();
      for (const id of ids) {{
        const n = data.nodes.get(id);
        const lbl = (n.title || "").toLowerCase();
        if (lbl.includes(q)) {{
          data.nodes.update({{ id, color: getComputedStyle(document.documentElement).getPropertyValue('--highlight').trim() }});
        }}
      }}
    }}

    statsEl.textContent = data.nodes.length + " nodes · " + data.edges.length + " edges";
  }}

  [topicSel, depthEl, wrapEl, dirEl, hideX, edgeLabels].forEach(el => el.addEventListener('input', render));
  searchEl.addEventListener('input', render);

  topicSel.value = "All Topics";
  render();
</script>
</body>
</html>
"""

    # return inline
    return HTMLResponse(content=html_doc, media_type="text/html")
    
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
