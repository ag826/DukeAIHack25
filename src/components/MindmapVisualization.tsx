import { useState, useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';

interface MindmapVisualizationProps {
  conversationId: string | null;
  userId: string;
}

export const MindmapVisualization = ({ conversationId, userId }: MindmapVisualizationProps) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [htmlContent, setHtmlContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!conversationId || !userId) {
      setHtmlContent(null);
      return;
    }

    const fetchHtml = async () => {
      setLoading(true);
      try {
        // ✅ use conv_id to match FastAPI
        const res = await fetch(
          `http://localhost:8000/mindmap-viewer?user_id=${encodeURIComponent(
            userId
          )}&conv_id=${encodeURIComponent(conversationId)}`
        );

        if (!res.ok) {
          console.error('Failed to fetch mindmap HTML:', res.status);
          setHtmlContent(null);
          return;
        }

        const html = await res.text();
        setHtmlContent(html);
      } catch (err) {
        console.error('Error fetching mindmap HTML:', err);
        setHtmlContent(null);
      } finally {
        setLoading(false);
      }
    };

    fetchHtml();
  }, [conversationId, userId]);

  if (!conversationId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Select a conversation to view its mindmap
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground gap-2">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span>Loading mindmap...</span>
      </div>
    );
  }

  if (!htmlContent) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Failed to load mindmap visualization
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <iframe
        // ✅ force remount when convo changes
        key={conversationId}
        ref={iframeRef}
        srcDoc={htmlContent}
        className="w-full h-full border-0"
        title="Mindmap Visualization"
      />
    </div>
  );
};