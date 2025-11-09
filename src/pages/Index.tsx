import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import AmbientRecorder from '@/components/AmbientRecorder';
import HomePage from '@/components/HomePage';
import VoiceCalibration from '@/components/VoiceCalibration';
import MicrophonePermission from '@/components/MicrophonePermission';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import Home from '@/pages/Home'

const Index = () => {
  const { user, loading, logout, hasVoiceProfile } = useAuth();
  const [micGranted, setMicGranted] = useState<boolean | null>(null);
  const navigate = useNavigate();

  // Check mic permission once user loads
  useEffect(() => {
    navigator.permissions
      .query({ name: 'microphone' as PermissionName })
      .then((res) => {
        setMicGranted(res.state === 'granted');
        res.onchange = () => {
          setMicGranted(res.state === 'granted');
        };
      })
      .catch(() => setMicGranted(false));
  }, []);

  // Redirect if not logged in
  useEffect(() => {
    if (!loading && !user) {
      navigate('/auth');
    }
  }, [user, loading, navigate]);

  if (loading || micGranted === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) return null;

  // If no microphone access, show permission screen
  if (!micGranted) {
    return <MicrophonePermission onPermissionGranted={() => setMicGranted(true)} />;
  }

  // ✅ After mic access granted
  return (
    <div className="min-h-screen">
      <div className="absolute top-4 right-4">
        <Button onClick={logout} variant="outline" size="sm">
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>
      {!hasVoiceProfile ? <VoiceCalibration /> : <Home />}
    </div>
  );
};

export default Index;
