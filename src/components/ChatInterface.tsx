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
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export const ChatInterface = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) return;

    const messagesRef = collection(db, 'chat_messages');
    const q = query(messagesRef, where('userId', '==', user.uid), orderBy('timestamp', 'asc'));

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const msgs: Message[] = [];
      snapshot.forEach((doc) => {
        msgs.push({
          id: doc.id,
          ...doc.data()
        } as Message);
      });
      setMessages(msgs);
    });

    return unsubscribe;
  }, [user]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!input.trim() || !user || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    try {
      const messagesRef = collection(db, 'chat_messages');
      
      await addDoc(messagesRef, {
        userId: user.uid,
        role: 'user',
        content: userMessage,
        timestamp: new Date().toISOString()
      });

      // Add temporary "thinking" message
      const thinkingMessageRef = await addDoc(messagesRef, {
        userId: user.uid,
        role: 'assistant',
        content: '...',
        timestamp: new Date().toISOString()
      });

      // Call Python backend API
      try {
        const response = await fetch('/api/chat-python', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            userId: user.uid,
            message: userMessage,
            conversationHistory: messages
          })
        });

        if (!response.ok) {
          throw new Error('Python backend offline');
        }

        const data = await response.json();
        
        // Update the thinking message with actual response
        await addDoc(messagesRef, {
          userId: user.uid,
          role: 'assistant',
          content: data.response || data.text || 'No response',
          timestamp: new Date().toISOString()
        });
      } catch (error) {
        // Show detailed error for debugging
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        await addDoc(messagesRef, {
          userId: user.uid,
          role: 'assistant',
          content: `Internal error: ${errorMessage}. Please check backend connection.`,
          timestamp: new Date().toISOString()
        });
        console.error('Chat error:', error);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      toast.error('Failed to send message');
    } finally {
      setIsLoading(false);
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
