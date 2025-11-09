import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const ChatPanel = () => {
  //const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([
   // { role: 'assistant', content: "Hey! Ask me about yesterday's convo." },
  //]);
  const [input, setInput] = useState('');

  type ChatMessage = {
    role: 'user' | 'assistant';
    content: string;
    };

    const [messages, setMessages] = useState<ChatMessage[]>([]);

    const send = async () => {
    if (!input.trim()) return;

    const userMsg: ChatMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    // later when you get an answer
    const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: "I'll search your meeting data for: " + input,
    };
    setMessages((prev) => [...prev, assistantMsg]);
    };


  return (
    <div className="flex flex-col gap-4 h-[80vh] border rounded-lg bg-card p-4">
      <div className="flex-1 overflow-y-auto space-y-3">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`max-w-[80%] px-3 py-2 rounded-md ${
              m.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'bg-muted'
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a meeting…"
          onKeyDown={(e) => e.key === 'Enter' && send()}
        />
        <Button onClick={send}>Send</Button>
      </div>
    </div>
  );
};

export default ChatPanel;
