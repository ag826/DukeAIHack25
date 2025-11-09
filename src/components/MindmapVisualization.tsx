import { useCallback, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  NodeMouseHandler,
  EdgeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ConversationGraph } from '@/pages/Home';
import { Card } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { X } from 'lucide-react';

interface MindmapVisualizationProps {
  graph: ConversationGraph;
}

export const MindmapVisualization = ({ graph }: MindmapVisualizationProps) => {
  const [density, setDensity] = useState([100]);
  const [selectedItem, setSelectedItem] = useState<{
    type: 'node' | 'edge';
    conversation: string;
  } | null>(null);

  const initialNodes: Node[] = graph.nodes.map((node, index) => ({
    id: node.id,
    data: { label: node.label },
    position: { x: (index % 3) * 200, y: Math.floor(index / 3) * 150 },
    style: {
      background: 'hsl(var(--primary))',
      color: 'hsl(var(--primary-foreground))',
      border: '1px solid hsl(var(--border))',
      borderRadius: '8px',
      padding: '10px',
    },
  }));

  const initialEdges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    style: { stroke: 'hsl(var(--border))' },
  }));

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onNodeMouseEnter: NodeMouseHandler = useCallback((_, node) => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === node.id
          ? { ...n, style: { ...n.style, opacity: 0.8 } }
          : n
      )
    );
  }, [setNodes]);

  const onNodeMouseLeave: NodeMouseHandler = useCallback(() => {
    setNodes((nds) =>
      nds.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } }))
    );
  }, [setNodes]);

  const onNodeClick: NodeMouseHandler = useCallback((_, node) => {
    const nodeData = graph.nodes.find((n) => n.id === node.id);
    if (nodeData) {
      setSelectedItem({ type: 'node', conversation: nodeData.conversation });
    }
  }, [graph.nodes]);

  const onEdgeClick: EdgeMouseHandler = useCallback((_, edge) => {
    const edgeData = graph.edges.find((e) => e.id === edge.id);
    if (edgeData) {
      setSelectedItem({ type: 'edge', conversation: edgeData.conversation });
    }
  }, [graph.edges]);

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-border">
        <h3 className="text-lg font-semibold text-foreground mb-2">Conversation Map</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Density:</span>
          <Slider
            value={density}
            onValueChange={setDensity}
            max={100}
            step={1}
            className="flex-1"
          />
        </div>
      </div>

      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>

        {selectedItem && (
          <Card className="absolute bottom-4 left-4 right-4 p-4 bg-background/95 backdrop-blur">
            <div className="flex justify-between items-start mb-2">
              <h4 className="font-medium text-foreground">
                {selectedItem.type === 'node' ? 'Topic' : 'Connection'}
              </h4>
              <button onClick={() => setSelectedItem(null)}>
                <X className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground">{selectedItem.conversation}</p>
          </Card>
        )}
      </div>
    </div>
  );
};
