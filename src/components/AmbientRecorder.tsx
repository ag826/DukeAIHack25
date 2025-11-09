import { useRef, useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Square } from 'lucide-react';
import { toast } from 'sonner';

const AmbientRecorder = () => {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const { user } = useAuth();
  const [isRecording, setIsRecording] = useState(false);

  // Speaker mapping UI state
  const [showSpeakerModal, setShowSpeakerModal] = useState(false);
  const [speakerMapping, setSpeakerMapping] = useState<Record<string, string>>({});
  const [speakerSummaries, setSpeakerSummaries] = useState<Record<string, string>>({});
  const [transcriptPath, setTranscriptPath] = useState<string | null>(null);
  const [phaseMeta, setPhaseMeta] = useState<{ userId: string; timestamp: string } | null>(
    null
  );

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.start(1000);
      setIsRecording(true);
      toast.success('Recording started');
      console.log('🎙 Ambient recording started');
    } catch (error) {
      console.error('Failed to start recording:', error);
      toast.error('Failed to start recording');
    }
  };

  const stopAndSaveRecording = async () => {
    console.log('🛑 Stopping recording...');
    if (mediaRecorderRef.current?.state !== 'recording') return;

    return new Promise<void>((resolve) => {
      if (!mediaRecorderRef.current) return resolve();

      mediaRecorderRef.current.addEventListener('stop', async () => {
        try {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const filename = `recording_${timestamp}.webm`;

          if (user) {
            const formData = new FormData();
            formData.append('userId', user.uid);
            formData.append('timestamp', timestamp);
            formData.append('filePath', blob, filename);

            try {
              const res = await fetch('http://localhost:8000/process-audio', {
                method: 'POST',
                body: formData,
              });

              const text = await res.text();
              console.log('📥 phase 1 raw:', text);

              if (!res.ok) {
                throw new Error(`phase 1 failed: ${res.status} ${text}`);
              }

              const phase1Json = JSON.parse(text);
              toast.success('Transcript ready. Please map speakers.');

              const tp = phase1Json.transcript_path as string;
              const speakerSummary = phase1Json.speaker_summary || {};

              // Parse speaker summaries: { "SPEAKER_00": "summary text", ... }
              const baseMapping: Record<string, string> = {};
              const summaries: Record<string, string> = {};
              
              if (speakerSummary && typeof speakerSummary === 'object') {
                Object.entries(speakerSummary).forEach(([speaker, summary]) => {
                  baseMapping[speaker] = speaker; // default name
                  summaries[speaker] = summary as string;
                });
              }

              setSpeakerMapping(baseMapping);
              setSpeakerSummaries(summaries);
              setTranscriptPath(tp);
              setPhaseMeta({ userId: user.uid, timestamp });
              setShowSpeakerModal(true);
            } catch (err) {
              console.error('❌ Failed to process audio (phase 1):', err);
              toast.error('Error processing recording.');
            }
          }

          chunksRef.current = [];
          setIsRecording(false);
          console.log('✅ Recording finished and phase 1 done.');
        } catch (error) {
          console.error('Error saving recording:', error);
          toast.error('Error saving recording.');
        }

        if (mediaRecorderRef.current) {
          mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
        }
        resolve();
      });

      mediaRecorderRef.current.stop();
    });
  };

  const handleConfirmMapping = async () => {
    if (!transcriptPath || !phaseMeta) {
      setShowSpeakerModal(false);
      return;
    }

    try {
      const res2 = await fetch('http://localhost:8000/process-audio-final', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transcript_path: transcriptPath,
          userId: phaseMeta.userId,
          timestamp: phaseMeta.timestamp,
          mapping: speakerMapping,
        }),
      });

      const text2 = await res2.text();
      console.log('📥 phase 2 raw:', text2);

      if (!res2.ok) {
        throw new Error(`phase 2 failed: ${res2.status} ${text2}`);
      }

      toast.success('Conversation processed and saved!');
    } catch (err) {
      console.error('❌ Failed to run phase 2:', err);
      toast.error('Error applying speaker names.');
    } finally {
      setShowSpeakerModal(false);
    }
  };

  useEffect(() => {
    startRecording();
  }, []);

  return (
    <>
      <Button
        onClick={stopAndSaveRecording}
        variant="destructive"
        size="sm"
        className="fixed bottom-4 right-4 z-50"
        disabled={!isRecording}
      >
        <Square className="mr-2 h-4 w-4" />
        Stop Recording
      </Button>

      {showSpeakerModal && (
        <div className="fixed inset-0 bg-black/40 z-[100] flex items-center justify-center p-4">
          <div className="bg-background rounded-lg shadow-lg p-6 w-full max-w-2xl space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Name the Speakers</h2>
            <p className="text-sm text-muted-foreground">
              We detected these speakers. Please give them names based on their summaries.
            </p>
            <div className="space-y-4 max-h-96 overflow-y-auto">
              {Object.keys(speakerMapping).length === 0 && (
                <p className="text-sm text-muted-foreground">No speakers detected.</p>
              )}
              {Object.entries(speakerMapping).map(([key, val]) => (
                <div key={key} className="border border-border rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-muted-foreground min-w-[100px]">
                      {key}
                    </span>
                    <input
                      className="flex-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="Enter name..."
                      value={val}
                      onChange={(e) =>
                        setSpeakerMapping((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                  {speakerSummaries[key] && (
                    <p className="text-xs text-muted-foreground bg-muted/50 rounded p-2">
                      {speakerSummaries[key]}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowSpeakerModal(false)}
              >
                Cancel
              </Button>
              <Button size="sm" onClick={handleConfirmMapping}>
                Save & Continue
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AmbientRecorder;
