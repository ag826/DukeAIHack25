
# Variables
PYTHON := python3
PIP := pip3
REQUIREMENTS := requirements.txt
TRANSCRIPT := transcript.txt
JSON_OUTPUT := mindmap.json

# Default target
all: install

# ----------------------
# 1. Install dependencies
# ----------------------
install:
	$(PIP) install -r $(REQUIREMENTS)

# ----------------------
# 3. Convert audio to text
# ----------------------
audio-to-text:
	$(PYTHON) Audio_to_text.py

# ----------------------
# 2. Generate mindmap JSON from transcript
# ----------------------
generate-json:
	$(PYTHON) LLM_json_generator.py


# ----------------------
# 4. Build or query vector DB
# ----------------------
vdb:
	$(PYTHON) vdb.py


full_pipeline:  audio-to-text generate-json vdb

