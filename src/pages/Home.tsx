import { useState } from 'react';
import { ConversationSidebar } from '@/components/ConversationSidebar';
import { ChatInterface } from '@/components/ChatInterface';
import { MindmapVisualization } from '@/components/MindmapVisualization';
import AmbientRecorder from '@/components/AmbientRecorder';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

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
  const { logout, user } = useAuth();
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);

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

      <ResizablePanelGroup direction="horizontal" className="h-screen">
        <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
          <ConversationSidebar onSelectConversation={setSelectedConversationId} />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel defaultSize={selectedConversationId ? 50 : 80}>
          <ChatInterface />
        </ResizablePanel>

        {selectedConversationId && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={30} minSize={20} maxSize={50}>
              <MindmapVisualization 
                conversationId={selectedConversationId} 
                userId={user?.uid || ''} 
              />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </div>
  );
};

export default Home;
