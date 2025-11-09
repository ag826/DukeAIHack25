import { useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { toast } from '@/hooks/use-toast';
import { Mic, MicOff, Check, Play, RotateCcw, Square } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { doc, updateDoc } from 'firebase/firestore';
import { ref, uploadBytes } from 'firebase/storage';
import { db, storage } from '@/lib/firebase';
import { useNavigate } from 'react-router-dom';

const REQUIRED_SAMPLES = 3;
const MAX_RECORDING_DURATION = 30000; // 30 seconds

const VoiceCalibration = () => {
  const [currentSample, setCurrentSample] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [recordedSamples, setRecordedSamples] = useState<Blob[]>([]);
  const [saving, setSaving] = useState(false);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const { user, setHasVoiceProfile } = useAuth();
  const navigate = useNavigate();

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setRecordedSamples((prev) => [...prev, blob]);
        setCurrentSample((prev) => prev + 1);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);

      // stop automatically after 30s max
      setTimeout(() => {
        if (mediaRecorderRef.current?.state === 'recording') {
          stopRecording();
        }
      }, MAX_RECORDING_DURATION);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to access microphone',
        variant: 'destructive',
      });
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      toast({
        title: 'Recording Stopped',
        description: 'Your sample has been saved.',
      });
    }
  };

  const playSample = (index: number) => {
    const sample = recordedSamples[index];
    if (!sample) return;

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    const audio = new Audio(URL.createObjectURL(sample));
    audioRef.current = audio;
    setPlayingIndex(index);

    audio.onended = () => {
      setPlayingIndex(null);
      audioRef.current = null;
    };

    audio.play();
  };

  const retakeSample = (index: number) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlayingIndex(null);

    const newSamples = [...recordedSamples];
    newSamples.splice(index, 1);
    setRecordedSamples(newSamples);
    setCurrentSample(index);

    toast({ title: 'Sample removed', description: 'Record a new sample' });
  };

  const saveVoiceProfile = async () => {
  if (!user || recordedSamples.length < REQUIRED_SAMPLES) {
    console.warn("❌ Missing user or insufficient samples");
    toast({
      title: "Error",
      description: "Please record all required samples before saving.",
      variant: "destructive",
    });
    return;
  }

  setSaving(true);
  console.log("🟡 Starting voice profile upload for:", user.uid);
  console.log(`🟡 Sending ${recordedSamples.length} samples to backend...`);

  try {
    const formData = new FormData();
    formData.append("user_id", user.uid);
    recordedSamples.forEach((sample, index) => {
      console.log(`📦 Appending sample ${index} (${(sample.size / 1024).toFixed(1)} KB)`);
      formData.append("sample_" + index, sample, `sample-${index}.webm`);
    });

    console.log("🌐 Sending request to backend...");
    const res = await fetch("http://localhost:8000/voice-profile", {
      method: "POST",
      body: formData,
    });

    console.log("📡 Response status:", res.status);
    let data = null;
    try {
      data = await res.json();
      console.log("📨 Response body:", data);
    } catch (jsonErr) {
      console.warn("⚠️ Could not parse JSON response:", jsonErr);
    }

    if (!res.ok) {
      console.error("❌ Backend returned non-OK status:", res.status);
      throw new Error(`Backend error ${res.status}: ${data?.error || "unknown error"}`);
    }

    // ✅ Backend success
    console.log("✅ Backend processed successfully:", data);
    setHasVoiceProfile(true);
    toast({ title: "Voice profile saved successfully!" });
    navigate("/");
  } catch (error) {
    console.error("🚨 Error saving voice profile:", error);
    toast({
      title: "Backend Error",
      description: `Failed to save voice profile: ${error.message}`,
      variant: "destructive",
    });

    // Continue for now
    console.log("⚙️ Proceeding optimistically despite backend error...");
    setHasVoiceProfile(true);
    navigate("/");
  } finally {
    setSaving(false);
    console.log("🟢 saveVoiceProfile completed.");
  }
};



  const progress = (currentSample / REQUIRED_SAMPLES) * 100;
  const isComplete = currentSample >= REQUIRED_SAMPLES;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 p-4">
      <Card className="w-full max-w-2xl border-border/50 shadow-elegant">
        <CardHeader className="space-y-4">
          <div className="flex justify-center">
            <div className="rounded-full bg-primary/10 p-4 animate-pulse-glow">
              <Mic className="h-12 w-12 text-primary" />
            </div>
          </div>
          <CardTitle className="text-center text-3xl">Voice Calibration</CardTitle>
          <CardDescription className="text-center text-base">
            Record up to 30 seconds for each of {REQUIRED_SAMPLES} samples. You can stop early if you want.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                Sample {currentSample} of {REQUIRED_SAMPLES}
              </span>
              <span className="text-primary font-medium">{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} className="h-2" />
          </div>

          <div className="space-y-4">
            {Array.from({ length: REQUIRED_SAMPLES }).map((_, index) => (
              <div
                key={index}
                className={`flex items-center gap-4 p-4 rounded-lg border transition-all ${
                  index < currentSample
                    ? 'border-primary/50 bg-primary/5'
                    : index === currentSample
                    ? 'border-primary bg-primary/10'
                    : 'border-border/50'
                }`}
              >
                <div
                  className={`rounded-full p-2 ${
                    index < currentSample ? 'bg-primary' : 'bg-muted'
                  }`}
                >
                  {index < currentSample ? (
                    <Check className="h-5 w-5 text-primary-foreground" />
                  ) : (
                    <Mic className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div className="flex-1">
                  <p className="font-medium">
                    Sample {index + 1}
                    {index === currentSample && isRecording && (
                      <span className="ml-2 text-sm text-primary animate-pulse">Recording...</span>
                    )}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {index < currentSample
                      ? 'Completed'
                      : index === currentSample
                      ? 'Read the prompt below naturally'
                      : 'Waiting...'}
                  </p>
                </div>
                {index < currentSample && recordedSamples[index] && (
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => playSample(index)}
                      disabled={playingIndex !== null || isRecording}
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => retakeSample(index)}
                      disabled={isRecording || saving}
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {!isComplete && (
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="pt-6">
                <p className="text-center text-foreground/90 leading-relaxed">
                  "Hello, I'm setting up my voice profile for this application. This sample will help
                  the system recognize my unique voice patterns and distinguish me from other speakers
                  during conversations."
                </p>
              </CardContent>
            </Card>
          )}

          <div className="flex gap-4">
            <Button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={saving || (isComplete && !isRecording)}
              className="flex-1"
              size="lg"
              variant={isRecording ? 'destructive' : 'default'}
            >
              {isRecording ? (
                <>
                  <Square className="mr-2 h-5 w-5" />
                  Stop Recording
                </>
              ) : (
                <>
                  <Mic className="mr-2 h-5 w-5" />
                  {currentSample === 0 ? 'Start Recording' : 'Record Next Sample'}
                </>
              )}
            </Button>

            {isComplete && (
              <Button onClick={saveVoiceProfile} disabled={saving} className="flex-1" size="lg">
                {saving ? 'Saving...' : 'Complete Setup'}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default VoiceCalibration;
