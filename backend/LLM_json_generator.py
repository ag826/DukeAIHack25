import json
import datetime
import google.generativeai as genai
import os
import dotenv

dotenv.load_dotenv()


def generate_conversation_mindmap_json(conversation_txt, source_file="transcript.txt"):
    system_prompt = """You are an expert conversation analyst. Your task is to read a multi-speaker dialogue and extract structured information for a mind map.

You must:
- Identify the main topics, subtopics, and their relationships.
- Attribute who introduced each topic and when (approximate timestamp from transcript if available).
- Capture whether each speaker supports, challenges, or elaborates on ideas.
- Encode all information into a *strictly valid JSON* that follows the schema below.
- Do not include explanations or markdown. Only return valid JSON.
- Use the field names and structure exactly as shown.

{
  "conversation_title": "string",
  "participants": [
    {
      "name": "string",
      "role": "optional string"
    }
  ],
  "main_topics": [
    {
      "topic": "string",
      "introduced_by": "string",
      "introduced_at": "timestamp (e.g., 00:02:15)",
      "sentiment": "positive | neutral | negative",
      "subtopics": [
        {
          "subtopic": "string",
          "introduced_by": "string",
          "introduced_at": "timestamp",
          "stance": "support | challenge | question | elaboration | neutral",
          "targeted_at": "string (parent topic or subtopic)",
          "discussed_by": ["list of participant names"],
          "sentiment": "positive | neutral | negative"
        }
      ]
    }
  ],
  "relationships": [
    {
      "from": "string (topic or subtopic)",
      "to": "string (topic or subtopic)",
      "type": "support | challenge | elaboration | contrast | extension | resolution",
      "initiated_by": "string",
      "initiated_at": "timestamp"
    }
  ],
  "metadata": {
    "conversation_length": "timestamp (HH:MM:SS)",
    "source_file": "string",
    "generated_on": "ISO datetime",
    "llm_model": "string"
  }
}
"""

    user_prompt = f"Here is the conversation transcript:\n\n{conversation_txt}\n\nGenerate the mind map JSON as per the schema above."

    model = genai.GenerativeModel("gemini-2.5-flash")

    response = model.generate_content(
        [system_prompt, user_prompt],
        generation_config={"temperature": 0, "response_mime_type": "application/json"}
    )

    raw_output = response.text.strip()

    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        # Try to clean up any accidental text output
        raw_output = raw_output[raw_output.find("{"): raw_output.rfind("}") + 1]
        data = json.loads(raw_output)

    # add metadata
    data["metadata"]["source_file"] = source_file
    data["metadata"]["generated_on"] = datetime.datetime.utcnow().isoformat()
    data["metadata"]["llm_model"] = "gemini-1.5-pro"

    return data


def main():
    transcript_path = "transcript.txt"

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    mindmap_data = generate_conversation_mindmap_json(transcript_text, source_file=transcript_path)

    output_path = "mindmap.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mindmap_data, f, indent=2)

    print(f"✅ Mind map JSON generated and saved to {output_path}")


if __name__ == "__main__":
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    main()
