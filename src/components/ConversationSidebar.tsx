import { useEffect, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { ConversationGraph } from '@/pages/Home';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface Conversation {
  id: string;
  timestamp: string;
  speakers: string[];
  graph: ConversationGraph;
  // if your backend returns extra fields, you can add them here
}

interface ConversationSidebarProps {
  onSelectConversation: (conversation: { id: string; graph: ConversationGraph } | null) => void;
}

export const ConversationSidebar = ({ onSelectConversation }: ConversationSidebarProps) => {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    // no user yet -> don't fetch
    if (!user) return;

    const fetchConversations = async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `http://localhost:8000/get-conversations?user_id=${encodeURIComponent(user.uid)}`
        );
        if (!res.ok) {
          console.error('❌ backend returned non-OK for get-conversations', res.status);
          return;
        }
        const data = await res.json();
        console.log('📥 /get-conversations response:', data);

        // data shape from backend:
        // { count: number, conversations: [ { id, timestamp, speakers, graph, ... } ] }
        const convs = (data.conversations || []).map((c: any) => {
          // normalize timestamp
          const ts =
            typeof c.timestamp === 'string'
              ? c.timestamp
              : new Date().toISOString();

          return {
            id: c.id,
            timestamp: ts,
            speakers: Array.isArray(c.speakers) ? c.speakers : [],
            graph: (c.graph || c.mindmap || {}) as ConversationGraph,
          } as Conversation;
        });

        console.log('✅ parsed conversations:', convs.length);
        setConversations(convs);
      } catch (err) {
        console.error('🔥 error fetching conversations from backend:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchConversations();
  }, [user]);

  const handleSelectConversation = (conv: Conversation) => {
    if (selectedId === conv.id) {
      setSelectedId(null);
      onSelectConversation(null);
    } else {
      setSelectedId(conv.id);
      onSelectConversation({ id: conv.id, graph: conv.graph });
    }
  };

  return (
    <div className="h-full border-r border-border bg-background flex flex-col relative">
      <div className="p-4 border-b border-border flex items-center justify-between">
        {!isCollapsed && <h2 className="text-lg font-semibold text-foreground">Conversations</h2>}
        <Button 
          variant="ghost" 
          size="icon"
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="ml-auto"
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
      <ScrollArea className="h-[calc(100vh-73px)]">
        <div className={`p-4 space-y-2 ${isCollapsed ? 'hidden' : ''}`}>
          {conversations.length === 0 && !loading && (
            <p className="text-xs text-muted-foreground">No conversations found.</p>
          )}
          {conversations.map((conv) => (
            <Card
              key={conv.id}
              className={`p-3 cursor-pointer hover:bg-accent transition-colors ${
                selectedId === conv.id ? 'bg-accent' : ''
              }`}
              onClick={() => handleSelectConversation(conv)}
            >
              <div className="text-sm font-medium text-foreground">
                {new Date(conv.timestamp).toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {conv.speakers?.join(', ') || 'Unknown speakers'}
              </div>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
};
