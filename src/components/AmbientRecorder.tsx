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

          // Simulate an absolute file path on your local filesystem
          // Replace this base path with your real data folder path on disk
          
          const absoluteFilePath = "C:/Users/slneha/Documents/AI Hackathon 2025/data/recording_"+timestamp+".webm";

          console.log('🗂 File saved at (absolute path):', absoluteFilePath);

          // Pass only the absolute file path to backend
          if (user) {
            const formData = new FormData();
            formData.append('userId', user.uid);
            formData.append('timestamp', timestamp);
            formData.append('filePath', blob, absoluteFilePath); // pass absolute path

            try {
              const res = await fetch('http://localhost:8000/process-audio', {
                method: 'POST',
                body: formData,
              });


              const responseText = await res.text();
              console.log("Raw response:", res);

              try {
                const data = JSON.parse(responseText);
                console.log("Parsed JSON:", data);
                toast.success('Recording processed successfully!');
              } catch (e) {
                console.error("Failed to parse JSON:", e);
                toast.error('Invalid JSON response from server.');
              }
            } catch (error) {
              console.error('❌ Failed to process audio:', error);
              toast.error('Error processing recording.');
            }
          }

          chunksRef.current = [];
          setIsRecording(false);
          console.log('✅ Recording finished and processed.');
        } catch (error) {
          console.error('Error saving recording:', error);
          toast.error('Error saving recording.');
        }

        // Stop all tracks
        if (mediaRecorderRef.current) {
          mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
        }
        resolve();
      });

      mediaRecorderRef.current.stop();
    });
  };

  useEffect(() => {
    startRecording();
  }, []);

  return (
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
  );
};

export default AmbientRecorder;