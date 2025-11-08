import librosa
from dotenv import load_dotenv
import assemblyai as aai
import os

# Load the .env file
load_dotenv()

aai.settings.api_key = os.getenv("API_Key")


def get_text(audio_file, out_path):

    config = aai.TranscriptionConfig(
        speech_model=aai.SpeechModel.universal,
        speaker_labels=True 
    )

    transcript = aai.Transcriber(config=config).transcribe(audio_file)

    if transcript.status == "error":
        raise RuntimeError(f"Transcription failed: {transcript.error}")

    with open(out_path, "w", encoding="utf-8") as f:
        for u in transcript.utterances:
            start = u.start / 1000
            end = u.end / 1000
            speaker = u.speaker
            text = u.text.replace("\n", " ")
            f.write(f"[ Start Time:{start} End Time:{end} ]\nSpeaker {speaker}: {text}\n")

    print(f"Wrote transcript to {out_path}")