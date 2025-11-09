import { useState } from 'react';
import { ConversationSidebar } from '@/components/ConversationSidebar';
import { ChatInterface } from '@/components/ChatInterface';
import { MindmapVisualization } from '@/components/MindmapVisualization';
import AmbientRecorder from '@/components/AmbientRecorder';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

export interface ConversationGraph {
  nodes: Array<{
    id: string;
    label: string;
    conversation: string;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    conversation: string;
  }>;
}

const Home = () => {
  const { logout } = useAuth();
  const [selectedConversation, setSelectedConversation] = useState<{
    id: string;
    graph: ConversationGraph;
  } | null>(null);

  return (
    <div className="min-h-screen bg-background">
      {/* Ambient recorder runs silently in background */}
      <AmbientRecorder />
      
      <div className="absolute top-4 right-4 z-10">
        <Button onClick={logout} variant="outline" size="sm">
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>

      <div className="flex h-screen">
        <ConversationSidebar onSelectConversation={setSelectedConversation} />
        
        <div className={`flex-1 transition-all duration-300 ${selectedConversation ? 'mr-96' : ''}`}>
          <ChatInterface />
        </div>

        {selectedConversation && (
          <div className="w-96 border-l border-border bg-background">
            <MindmapVisualization graph={selectedConversation.graph} />
          </div>
        )}
      </div>
    </div>
  );
};

export default Home;
