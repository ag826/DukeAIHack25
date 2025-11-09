import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import speech_recognition as sr

fs = 44100  # Sample rate
channels = 1

print("Press ENTER to start recording...")
input()

print("Recording... Press ENTER again to stop.")
recorded_chunks = []

# Callback for non-blocking recording
def callback(indata, frames, time, status):
    recorded_chunks.append(indata.copy())

stream = sd.InputStream(samplerate=fs, channels=channels, callback=callback)
with stream:
    input()  # Wait until user presses Enter
    # Exiting the 'with' block stops the stream

# Combine all chunks
audio_np = np.concatenate(recorded_chunks, axis=0)
write("input_audio.wav", fs, audio_np)

print("Saved recording to input_audio.wav")

# # Transcribe using speech_recognition
# r = sr.Recognizer()
# with sr.AudioFile("output.wav") as source:
#     audio = r.record(source)

# try:
#     text = r.recognize_google(audio)
#     print("\n--- Transcribed Text ---")
#     print(text)
# except sr.UnknownValueError:
#     print("Could not understand audio.")
# except sr.RequestError as e:
#     print(f"Request failed: {e}")
