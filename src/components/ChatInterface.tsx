import { useState, useRef, useEffect } from 'react';
import { collection, addDoc, query, where, orderBy, onSnapshot } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Send } from 'lucide-react';
import { toast } from 'sonner';

interface Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  history?: JSON;
}

export const ChatInterface = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!input.trim() || !user || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    // ⿡ Add user message immediately
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);

    // ⿢ Add temporary "assistant thinking"
    setMessages((prev) => [...prev, { role: 'assistant', content: '...' }]);

    

    try {
  // 1️⃣ Get all conversations
  const res1 = await fetch(
    'http://localhost:8000/get-conversations?user_id=${encodeURIComponent(user.uid)}'
  );
  if (!res1.ok) {
    console.error('❌ backend returned non-OK for get-conversations', res1.status);
    return;
  }
  const data1 = await res1.json();
  console.log('📥 /get-conversations response:', data1);

  // 2️⃣ Extract mindmap info or summary text for context
  const history = (data1.conversations || []).map((conv) => ({
    role: 'assistant',
    content: JSON.stringify(conv.mindmap || conv.graph || conv.speakers || {}),
  }));

  // 3️⃣ Add current chat message
  history.push({ role: 'user', content: userMessage });

  // 4️⃣ Send to /chat
  const res = await fetch('http://localhost:8000/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      userId: user.uid,
      message: userMessage,
      history, // ✅ now properly formatted
    }),
  });

  const data = await res.json();
  const reply = data.reply || 'No response';
  console.log('LLM reply:', reply);

  // replace “...” in UI
  setMessages((prev) => {
    const updated = [...prev];
    updated[updated.length - 1] = { role: 'assistant', content: reply };
    return updated;
  });
} catch (error) {
      console.error('Chat error:', error);
      toast.error('Failed to reach backend.');
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: '⚠ Backend error — check server logs.',
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
      scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 border-b border-border">
        <h1 className="text-2xl font-bold text-foreground">Chat Assistant</h1>
        <p className="text-sm text-muted-foreground">Ask about your past conversations</p>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg p-3 ${
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          ))}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-border">
        <div className="max-w-3xl mx-auto flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder="Ask about your conversations..."
            className="min-h-[60px]"
            disabled={isLoading}
          />
          <Button onClick={handleSendMessage} disabled={isLoading || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};
