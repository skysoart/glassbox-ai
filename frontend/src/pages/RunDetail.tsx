import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';

// --- Types ---
type SpanStatus = "ok" | "warn" | "error";

interface Span {
  id: string;
  type: string;
  startMs: number;
  endMs: number;
  status: SpanStatus;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number;
  input: any;
  output: any;
  error?: string;
}

interface ContextSegment {
  kind: string;
  tokens: number;
  note?: string;
}

interface Turn {
  index: number;
  userMessage: string;
  assistantMessage: string;
  spans: Span[];
  context: { limit: number; segments: ContextSegment[] };
}

// --- Subcomponents ---

function ContextMeter({ context }: { context: Turn['context'] }) {
  const total = context.limit;
  
  return (
    <div className="w-full h-[18px] bg-[var(--color-hairline)] flex overflow-hidden rounded-[1px] group relative">
      {context.segments.map((seg, i) => {
        const pct = (seg.tokens / total) * 100;
        const isTrimmed = seg.note === 'Trimmed';
        
        const bgColors: Record<string, string> = {
          'system': 'var(--color-ink)',
          'summary': 'var(--color-muted)',
          'retrieved': '#9e9b94',
          'recent': '#cfccbe'
        };
        const bg = bgColors[seg.kind] || 'var(--color-muted)';

        return (
          <div 
            key={i} 
            style={{ 
              width: `${pct}%`, 
              backgroundColor: bg,
              backgroundImage: isTrimmed ? 'repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(255,255,255,0.2) 2px, rgba(255,255,255,0.2) 4px)' : 'none'
            }}
            className="h-full border-r border-[var(--color-paper)] relative transition-all"
            title={`${seg.kind}: ${seg.tokens} tokens ${seg.note ? `(${seg.note})` : ''}`}
          >
            <div className="absolute opacity-0 group-hover:opacity-100 top-full mt-1 bg-[var(--color-ink)] text-[var(--color-paper)] font-mono text-[10px] px-1 py-0.5 whitespace-nowrap z-50 pointer-events-none transition-opacity">
              {seg.kind}: {seg.tokens}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Copyable({ text, children }: { text: string, children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group cursor-pointer inline-flex" onClick={handleCopy}>
      {children}
      <span className={`absolute -top-6 left-1/2 -translate-x-1/2 bg-[var(--color-ink)] text-[var(--color-paper)] text-[10px] px-1.5 py-0.5 rounded-[2px] transition-opacity ${copied ? 'opacity-100' : 'opacity-0'}`}>
        copied
      </span>
    </div>
  );
}

export default function RunDetail() {
  const { id } = useParams();
  
  const [run, setRun] = useState<any>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedTurnIdx, setSelectedTurnIdx] = useState(0);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'input'|'output'|'metrics'|'context'>('input');
  
  useEffect(() => {
    async function fetchData() {
      try {
        const runRes = await axios.get(`http://localhost:8000/api/runs/${id}`);
        const tracesRes = await axios.get(`http://localhost:8000/api/runs/${id}/traces`);
        
        setRun(runRes.data);
        
        // Map backend flat traces into a single "Turn" for now, or split by LLM_CALL.
        // To be safe and show all spans, we will bundle them into one Turn called "Session".
        const spans: Span[] = tracesRes.data.map((t: any) => ({
          id: t.step_id,
          type: t.step_type,
          startMs: new Date(t.timestamp_start).getTime(),
          endMs: new Date(t.timestamp_end).getTime(),
          status: t.status === 'SUCCESS' ? 'ok' : 'error',
          model: t.model,
          tokensIn: t.token_usage?.prompt_tokens,
          tokensOut: t.token_usage?.completion_tokens,
          costUsd: t.cost,
          input: t.input_data,
          output: t.output_data,
          error: t.error ? JSON.stringify(t.error) : undefined
        }));

        let contextSegments: ContextSegment[] = [
          { kind: "recent", tokens: runRes.data.total_tokens || 0 }
        ];

        setTurns([{
          index: 1,
          userMessage: runRes.data.conversation_id,
          assistantMessage: "Telemetry trace recorded for this session.",
          spans: spans,
          context: { limit: 8192, segments: contextSegments }
        }]);

      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [id]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'j') {
        setSelectedTurnIdx(prev => Math.min(prev + 1, turns.length - 1));
      } else if (e.key === 'k') {
        setSelectedTurnIdx(prev => Math.max(prev - 1, 0));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [turns.length]);

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING TRACE... ]</div>;
  if (!run || turns.length === 0) return <div className="p-6 font-mono text-[13px] text-[var(--color-oxblood)]">Trace not found.</div>;

  const selectedTurn = turns[selectedTurnIdx];
  const selectedSpan = selectedTurn?.spans.find(s => s.id === selectedSpanId) || selectedTurn?.spans[0];

  const maxEndMs = Math.max(...(selectedTurn?.spans.map(s => s.endMs) || [1000]));
  const minStartMs = Math.min(...(selectedTurn?.spans.map(s => s.startMs) || [0]));
  const totalDuration = Math.max(maxEndMs - minStartMs, 1);

  return (
    <div className="flex flex-col h-full bg-[var(--color-surface)]">
      
      {/* Top Header */}
      <div className="border-b border-[var(--color-hairline)] bg-[var(--color-paper)] p-3 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-[var(--color-muted)] hover:text-[var(--color-ink)] text-sm">← Back</Link>
          <h2 className="font-serif text-xl text-[var(--color-ink)]">Run {run.run_id.split('-')[0]}</h2>
          <span className={`px-2 py-0.5 text-[11px] font-mono border ${run.status !== 'SUCCESS' ? 'border-[var(--color-oxblood)] text-[var(--color-oxblood)] bg-[var(--color-oxblood)]/10' : 'border-[var(--color-hairline)] text-[var(--color-ink)]'}`}>
            {run.status.toUpperCase()}
          </span>
        </div>
        <div className="font-mono text-[12px] text-[var(--color-muted)]">
          {run.total_latency_ms.toFixed(2)}ms • ${run.total_cost.toFixed(4)}
        </div>
      </div>

      {/* 3 Pane Layout */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* Pane 1: Chat Margin */}
        <div className="w-[30%] border-r border-[var(--color-hairline)] bg-[var(--color-paper)] overflow-y-auto flex flex-col">
          <div className="p-3 border-b border-[var(--color-hairline)] sticky top-0 bg-[var(--color-paper)] z-10">
            <h3 className="small-caps text-[var(--color-muted)]">Session Overview</h3>
          </div>
          <div className="flex-1 p-4 space-y-4">
            {turns.map((turn, idx) => (
              <div 
                key={turn.index} 
                className={`relative pl-8 pr-2 py-2 cursor-pointer transition-colors ${idx === selectedTurnIdx ? 'bg-[var(--color-hairline)]/30' : 'hover:bg-[var(--color-surface)]'}`}
                onClick={() => { setSelectedTurnIdx(idx); setSelectedSpanId(null); }}
              >
                <div className={`absolute left-0 top-0 bottom-0 w-6 border-r border-[var(--color-hairline)] flex items-start justify-center pt-2 font-mono text-[11px] ${idx === selectedTurnIdx ? 'text-[var(--color-ink)] font-bold bg-[var(--color-hairline)]/50' : 'text-[var(--color-muted)]'}`}>
                  {turn.index}
                </div>
                
                <div className="text-[13px] text-[var(--color-ink)] mb-2 font-medium break-all">
                  {turn.userMessage}
                </div>
                <div className="text-[13px] text-[var(--color-muted)] line-clamp-3 leading-relaxed">
                  {turn.assistantMessage}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pane 2: Waterfall */}
        <div className="w-[40%] border-r border-[var(--color-hairline)] flex flex-col bg-[var(--color-surface)]">
          <div className="p-3 border-b border-[var(--color-hairline)] bg-[var(--color-paper)] shrink-0 space-y-2">
            <h3 className="small-caps text-[var(--color-muted)] flex justify-between">
              <span>Trace Waterfall</span>
              <span>Total Spans: {selectedTurn?.spans.length}</span>
            </h3>
            {selectedTurn && (
              <div className="flex flex-col gap-1">
                <ContextMeter context={selectedTurn.context} />
                <div className="flex justify-between font-mono text-[10px] text-[var(--color-muted)]">
                  <span>0 tokens</span>
                  <span>{selectedTurn.context.limit} max</span>
                </div>
              </div>
            )}
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 space-y-1">
            <div className="flex border-b border-[var(--color-hairline)] mb-2 pb-1 font-mono text-[10px] text-[var(--color-muted)]">
              <div className="w-[120px]">Span</div>
              <div className="flex-1 relative">
                <span className="absolute left-0">0ms</span>
                <span className="absolute right-0">{totalDuration}ms</span>
              </div>
            </div>

            {selectedTurn?.spans.map((span) => {
              const isSelected = selectedSpanId === span.id || (!selectedSpanId && selectedTurn.spans[0]?.id === span.id);
              const leftPct = ((span.startMs - minStartMs) / totalDuration) * 100;
              const widthPct = Math.max(((span.endMs - span.startMs) / totalDuration) * 100, 1);
              
              const isError = span.status === 'error';
              const isWarn = span.status === 'warn';

              return (
                <div 
                  key={span.id}
                  onClick={() => setSelectedSpanId(span.id)}
                  className={`flex items-center text-[12px] group cursor-pointer ${isSelected ? 'bg-[var(--color-hairline)]/40' : 'hover:bg-[var(--color-hairline)]/20'}`}
                >
                  <div className="w-[120px] shrink-0 font-mono text-[10px] truncate pr-2 flex items-center gap-1">
                    {isError ? <span className="text-[var(--color-oxblood)] font-bold">×</span> : isWarn ? <span className="text-[#a67a00] font-bold">!</span> : null}
                    <span className={isError ? 'text-[var(--color-oxblood)]' : 'text-[var(--color-ink)]'}>
                      {span.type}
                    </span>
                  </div>
                  <div className="flex-1 h-6 relative flex items-center">
                    <div className="absolute left-0 right-0 h-[1px] bg-[var(--color-hairline)]/50"></div>
                    <div 
                      className={`absolute h-3 transition-all ${isError ? 'bg-[var(--color-oxblood)]' : isWarn ? 'bg-[#a67a00]' : isSelected ? 'bg-[var(--color-ink)]' : 'bg-[var(--color-muted)]'}`}
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                    ></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Pane 3: Inspector */}
        <div className="w-[30%] bg-[var(--color-paper)] flex flex-col overflow-hidden">
          <div className="p-3 border-b border-[var(--color-hairline)] flex gap-4 text-[12px] font-medium text-[var(--color-muted)] bg-[var(--color-paper)] shrink-0">
            {(['input', 'output', 'metrics', 'context'] as const).map(tab => (
              <button 
                key={tab}
                onClick={() => setInspectorTab(tab)}
                className={`uppercase tracking-widest ${inspectorTab === tab ? 'text-[var(--color-ink)] border-b border-[var(--color-ink)] pb-1' : 'hover:text-[var(--color-ink)]'}`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-4 font-mono text-[12px]">
            {selectedSpan ? (
              <>
                <div className="mb-4 flex items-center gap-2">
                  <span className="small-caps text-[var(--color-muted)]">Span ID</span>
                  <Copyable text={selectedSpan.id}><span className="text-[var(--color-ink)] hover:underline truncate inline-block w-48">{selectedSpan.id}</span></Copyable>
                </div>

                {inspectorTab === 'input' && (
                  <div>
                    <h4 className="small-caps text-[var(--color-muted)] mb-2">Input Payload</h4>
                    <pre className="bg-[var(--color-surface)] border border-[var(--color-hairline)] p-3 rounded-[2px] overflow-x-auto whitespace-pre-wrap text-[var(--color-ink)] leading-relaxed">
                      {selectedSpan.input ? (typeof selectedSpan.input === 'string' ? selectedSpan.input : JSON.stringify(selectedSpan.input, null, 2)) : 'null'}
                    </pre>
                  </div>
                )}

                {inspectorTab === 'output' && (
                  <div>
                    <h4 className="small-caps text-[var(--color-muted)] mb-2">Output Payload</h4>
                    {selectedSpan.error && (
                      <div className="bg-[var(--color-oxblood)]/10 text-[var(--color-oxblood)] border border-[var(--color-oxblood)] p-3 mb-4 whitespace-pre-wrap">
                        {selectedSpan.error}
                      </div>
                    )}
                    <pre className="bg-[var(--color-surface)] border border-[var(--color-hairline)] p-3 rounded-[2px] overflow-x-auto whitespace-pre-wrap text-[var(--color-ink)] leading-relaxed">
                      {selectedSpan.output ? (typeof selectedSpan.output === 'string' ? selectedSpan.output : JSON.stringify(selectedSpan.output, null, 2)) : 'null'}
                    </pre>
                  </div>
                )}

                {inspectorTab === 'metrics' && (
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[var(--color-hairline)]">
                        <td className="py-2 text-[var(--color-muted)]">Model</td>
                        <td className="py-2 text-right">{selectedSpan.model || '-'}</td>
                      </tr>
                      <tr className="border-b border-[var(--color-hairline)]">
                        <td className="py-2 text-[var(--color-muted)]">Duration</td>
                        <td className="py-2 text-right">{selectedSpan.endMs - selectedSpan.startMs}ms</td>
                      </tr>
                      <tr className="border-b border-[var(--color-hairline)]">
                        <td className="py-2 text-[var(--color-muted)]">Tokens In</td>
                        <td className="py-2 text-right">{selectedSpan.tokensIn || '-'}</td>
                      </tr>
                      <tr className="border-b border-[var(--color-hairline)]">
                        <td className="py-2 text-[var(--color-muted)]">Tokens Out</td>
                        <td className="py-2 text-right">{selectedSpan.tokensOut || '-'}</td>
                      </tr>
                      <tr>
                        <td className="py-2 text-[var(--color-muted)]">Cost</td>
                        <td className="py-2 text-right">${selectedSpan.costUsd?.toFixed(6) || '-'}</td>
                      </tr>
                    </tbody>
                  </table>
                )}

                {inspectorTab === 'context' && (
                  <div>
                    <h4 className="small-caps text-[var(--color-muted)] mb-2">Context Breakdown</h4>
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-[var(--color-hairline)] text-[var(--color-muted)]">
                          <th className="py-2 font-normal">Segment</th>
                          <th className="py-2 font-normal text-right">Tokens</th>
                          <th className="py-2 font-normal text-right">Note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedTurn?.context.segments.map((s, i) => (
                          <tr key={i} className="border-b border-[var(--color-hairline)]">
                            <td className="py-2">{s.kind}</td>
                            <td className="py-2 text-right">{s.tokens}</td>
                            <td className="py-2 text-right text-[var(--color-muted)]">{s.note || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <div className="text-[var(--color-muted)]">Select a span to inspect.</div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Transport Bar */}
      <div className="h-12 border-t border-[var(--color-hairline)] bg-[var(--color-paper)] flex items-center px-4 justify-between shrink-0 font-mono text-[12px] text-[var(--color-ink)]">
        <div className="flex gap-4 items-center">
          <button 
            className="hover:text-[var(--color-oxblood)] transition-colors disabled:opacity-30" 
            onClick={() => setSelectedTurnIdx(0)}
            disabled={selectedTurnIdx === 0}
          >
            ⏮
          </button>
          <button 
            className="hover:text-[var(--color-oxblood)] transition-colors disabled:opacity-30"
            onClick={() => setSelectedTurnIdx(prev => Math.max(prev - 1, 0))}
            disabled={selectedTurnIdx === 0}
          >
            ◀ <span className="text-[10px] text-[var(--color-muted)] ml-1">K</span>
          </button>
          
          <span className="w-32 text-center bg-[var(--color-surface)] border border-[var(--color-hairline)] py-1 rounded-[2px]">
            turn {selectedTurnIdx + 1} / {turns.length}
          </span>
          
          <button 
            className="hover:text-[var(--color-oxblood)] transition-colors disabled:opacity-30"
            onClick={() => setSelectedTurnIdx(prev => Math.min(prev + 1, turns.length - 1))}
            disabled={selectedTurnIdx === turns.length - 1}
          >
            ▶ <span className="text-[10px] text-[var(--color-muted)] ml-1">J</span>
          </button>
          <button 
            className="hover:text-[var(--color-oxblood)] transition-colors disabled:opacity-30"
            onClick={() => setSelectedTurnIdx(turns.length - 1)}
            disabled={selectedTurnIdx === turns.length - 1}
          >
            ⏭
          </button>
        </div>
        
        <div className="text-[var(--color-muted)] text-[10px]">
          [SPACE] play/pause
        </div>
      </div>

    </div>
  );
}
