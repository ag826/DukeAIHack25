import os
import re
import json
import time
import unicodedata
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Optional: load .env if it exists
try:
    import dotenv
    dotenv.load_dotenv()
except Exception:
    pass

# ----------- Configuration -----------
# input_path = "speaker.txt"         # transcript file
# out_dir = "out_speakers"           # where to save outputs
# pages = 1                          # Google pages per speaker (10 results/page)
# pause = 1.5                        # seconds between API calls
# query_template = '"{name}"'        # search pattern
# dry_run = False                    # True = skip Google API calls (for testing)
# # ------------------------------------

# HEADER_RE = re.compile(r"^\s*([A-Za-z\s]+):", flags=re.MULTILINE) # re.compile(r"^\[\s*([^\]]+?)\s*:\]", flags=re.MULTILINE)

# def extract_raw_headers(text):
#     return HEADER_RE.findall(text)

SPEAKER_RE = re.compile(r'^(?!\s*\[)\s*([^:\n]+?):', flags=re.MULTILINE)

def extract_speakers(text):
    # findall returns appearances in order; use this to get unique names while preserving order
    seen = set()
    ordered = []
    for name in SPEAKER_RE.findall(text):
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered

def normalize_header_to_name(h):
    """Normalize bracket headers into canonical speaker names."""
    s = unicodedata.normalize("NFKC", h)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = s.split(" ")

    def has_non_lower(ts):
        return any(not re.fullmatch(r"[a-z]+", t) for t in ts)

    while tokens and re.fullmatch(r"[a-z]+", tokens[-1]):
        if has_non_lower(tokens[:-1]):
            tokens.pop()
        else:
            break
    s = " ".join(tokens).strip()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^0-9A-Za-z\s\.\-\'&]", " ", s)
    s = re.sub(r"[.,:;!?\u2026\-–—]+$", "", s).strip()
    s = re.sub(r"\s*\.\s*", ".", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def unique_preserve_order(items):
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

# -------- Helper to scrape full page text --------
def scrape_link_text(url, max_chars=15000):
    """Fetch visible text from a webpage using BeautifulSoup."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # remove scripts/styles
        for s in soup(["script", "style", "header", "footer", "nav", "aside"]):
            s.decompose()
        text = " ".join(t.strip() for t in soup.stripped_strings)
        return text[:max_chars]  # truncate to max_chars to avoid huge JSON
    except Exception as e:
        return f"Error fetching content: {e}"

# -------- Google search + scrape helper --------
GOOGLE_API = "https://www.googleapis.com/customsearch/v1"

def google_search_person(query_template, person_name, api_key, cx, num_pages=1, pause=1.5):
    links, texts = [], []
    rendered_q = query_template.format(name=person_name).strip()

    for page in range(num_pages):
        start = page * 10 + 1
        params = {"key": api_key, "cx": cx, "q": rendered_q, "start": start}
        resp = requests.get(GOOGLE_API, params=params, timeout=20)
        if resp.status_code == 429:
            print("Rate limited — sleeping before retry...")
            time.sleep(3 + page)
            resp = requests.get(GOOGLE_API, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break

        for it in items:
            link = it.get("link") or ""
            if link:
                links.append(link)
                text = scrape_link_text(link)
                texts.append(text)
                time.sleep(max(0.0, pause))  # be polite

    return {
        "query": person_name,
        "rendered_query": rendered_q,
        "total_results": len(links),
        "texts": texts,
        "links": links,
    }

# # ----------- Main pipeline -----------
# API_KEY = os.getenv("CUSTOM_SEARCH_API_KEY", "").strip()
# CX = os.getenv("CUSTOM_SEARCH_ENGINE_ID", "").strip()

# text = Path(input_path).read_text(encoding="utf-8", errors="ignore")

# raw_headers = extract_raw_headers(text)
# names = [normalize_header_to_name(h) for h in raw_headers if h.strip()]
# speakers = unique_preserve_order(names)

# out_dir = Path(out_dir)
# (out_dir / "profiles").mkdir(parents=True, exist_ok=True)

# print(f"✅ Found {len(speakers)} unique speakers:\n")
# for i, s in enumerate(speakers, 1):
#     print(f"{i:>2}. {s}")

# summary = {
#     "input": input_path,
#     "total_unique_speakers": len(speakers),
#     "query_template": query_template,
#     "pages": pages,
#     "pause": pause,
#     "speakers": [],
#     "generated_at": time.time(),
# }

# if dry_run:
#     Path(out_dir / "speakers_summary.json").write_text(
#         json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
#     )
#     print(f"\n--dry-run=True: wrote only {out_dir/'speakers_summary.json'}")
# else:
#     if not API_KEY or not CX:
#         raise SystemExit("❌ Missing CUSTOM_SEARCH_API_KEY or CUSTOM_SEARCH_ENGINE_ID (.env)")

#     for name in speakers:
#         print(f"\n[+] Fetching: {name}")
#         try:
#             info = google_search_person(
#                 person_name=name,
#                 api_key=API_KEY,
#                 cx=CX,
#                 num_pages=pages,
#                 pause=pause,
#                 query_template=query_template,
#             )
#         except Exception as e:
#             print(f"   ✗ Error for {name}: {e}")
#             info = {
#                 "query": name,
#                 "rendered_query": query_template.format(name=name),
#                 "total_results": 0,
#                 "texts": [],
#                 "links": [],
#                 "error": str(e),
#             }

#         slug = re.sub(r"[^0-9A-Za-z\-_]+", "_", name).strip("_")
#         out_file = out_dir / "profiles" / f"{slug}_info.json"
#         out_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

#         summary["speakers"].append({
#             "name": name,
#             "file": str(out_file),
#             "total_results": info.get("total_results", 0),
#         })

#     Path(out_dir / "speakers_summary.json").write_text(
#         json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
#     )

#     print(f"\n✅ Done.\nProfiles saved under: {out_dir/'profiles'}\nSummary: {out_dir/'speakers_summary.json'}")
