import json
import datetime
import google.generativeai as genai
import os
import dotenv
import re

dotenv.load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def summarize_speaker_content(transcript_text: str) -> dict:
    """
    Summarize what each speaker mainly talked about using Gemini.
    Returns a dict { "Speaker A": "summary of their topics", ... }
    Handles non-JSON responses gracefully.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""
        You are a summarization assistant.

        Here is a transcript with multiple speakers (Speaker A, B, C...).
        Summarize in 1-2 sentences what each speaker mainly talked about or contributed.

        Return ONLY valid JSON in this format:
        {{
        "Speaker A": "summary",
        "Speaker B": "summary"
        }}

        Transcript:
        {transcript_text}
        """

    response = model.generate_content(prompt)
    text = response.text.strip()
    print(text)

    # Try to extract JSON block if extra text is included
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
    else:
        json_str = "{}"  # fallback if no braces found

    try:
        speaker_summaries = json.loads(json_str)
    except json.JSONDecodeError:
        print("⚠️ Gemini response not valid JSON. Here's what it said:\n")
        print(text)
        speaker_summaries = {}

    return speaker_summaries

def prompt_user_for_names(speaker_summaries: dict) -> dict:
    """
    Interactively ask user to name each speaker based on the summary.
    Returns mapping { "Speaker A": "Real Name" }
    """
    mapping = {}
    print("\n🔍 Identify Speakers")
    print("="*60)
    for speaker, summary in speaker_summaries.items():
        print(f"\n🗣️ {speaker} talked about:\n   {summary}")
        name = input(f"👉 Who was {speaker}? (Press Enter to keep as-is): ").strip()
        mapping[speaker] = name if name else speaker
    print("="*60)
    return mapping


def apply_speaker_mapping(transcript_text: str, mapping: dict) -> str:
    """
    Replace placeholder speakers in the transcript with the real names.
    Keeps timestamps and structure identical.
    """
    replaced_text = transcript_text
    for placeholder, real_name in mapping.items():
        replaced_text = re.sub(
            rf"\b{placeholder}\b", real_name, replaced_text
        )
    return replaced_text


def rename_speakers_in_transcript(raw_out):
    """
    Main function to rename speakers in a transcript file.
    """
    named_out = "named"+raw_out # output file path

    with open(raw_out, "r", encoding="utf-8") as f:
        transcript = f.read()
    
    summaries = summarize_speaker_content(transcript)

    print(summaries)

    #Ask user to identify speakers
    mapping = prompt_user_for_names(summaries)
    print(f"\n✅ Final Speaker Mapping:\n{json.dumps(mapping, indent=2)}")

    # Step 4: Replace and save new transcript
    new_transcript = apply_speaker_mapping(transcript, mapping)
    with open(named_out, "w", encoding="utf-8") as f:
        f.write(new_transcript)

    print(f"🎯 Named transcript saved to {named_out}")

    return named_out


if __name__ == "__main__":
    raw_out = "REALTIME_transcript.txt"  # Input transcript file path
    rename_speakers_in_transcript(raw_out)