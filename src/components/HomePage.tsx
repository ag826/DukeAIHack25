import AmbientRecorder from '@/components/AmbientRecorder';
import ChatPanel from '@/components/ChatPanel';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

const HomePage = () => {
  const { logout } = useAuth();

  return (
    <div className="min-h-screen flex bg-background">
      {/* top-right ambient status */}
      <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 shadow-sm">
        <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        <p className="text-sm text-emerald-900 font-medium">Ambient recording: ON</p>
      </div>

      {/* logout */}
      <div className="fixed top-4 left-4 z-50">
        <Button onClick={logout} variant="outline" size="sm">
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>

      {/* main layout */}
      <div className="flex-1 flex">
        {/* chat area */}
        <div className="flex-1 max-w-3xl mx-auto py-16 px-4">
          <ChatPanel />
        </div>
      </div>

      {/* invisible ambient recorder mounted on the page */}
      <AmbientRecorder />
    </div>
  );
};

export default HomePage;
