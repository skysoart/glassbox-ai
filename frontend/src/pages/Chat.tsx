import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

// Specialized trace card renderer adhering to Flight Recorder aesthetic
function renderTraceCard(trace: any) {
  if (trace.step_type === 'RAG_RETRIEVAL') {
    const raw = typeof trace.output_data === 'string' ? trace.output_data : JSON.stringify(trace.output_data);
    const parts = raw.split('--- From ');
    const query = trace.input_data?.query || '';
    
    return (
      <div className="space-y-2">
        {query && (
          <div className="text-[10px] text-[var(--color-muted)] border-b border-[var(--color-hairline)] pb-1">
            QUERY: <span className="text-[var(--color-ink)] font-medium font-mono">"{query}"</span>
          </div>
        )}
        {parts.length > 1 ? (
          parts.slice(1).map((part: string, pIdx: number) => {
            const lines = part.split(' ---\n');
            const docName = lines[0];
            const content = lines.slice(1).join(' ---\n').trim();
            return (
              <div key={pIdx} className="bg-[var(--color-surface)] border border-[var(--color-hairline)] p-2 text-[10px]">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="bg-[var(--color-ink)] text-[var(--color-paper)] px-1 py-0.2 font-mono text-[9px]">
                    DOC
                  </span>
                  <span className="font-mono text-[var(--color-ink)] font-medium">{docName}</span>
                </div>
                <div className="text-[var(--color-muted)] leading-relaxed line-clamp-4 hover:line-clamp-none">
                  {content}
                </div>
              </div>
            );
          })
        ) : (
          <div className="bg-[var(--color-surface)] border border-[var(--color-hairline)] p-2.5 font-mono text-[10px] text-[var(--color-muted)]">
            <div className="text-[var(--color-ink)] font-medium mb-0.5">[ NO CONTEXT INJECTED ]</div>
            <div>Query is conversational or contains no matching documentation keywords. LLM context kept clean.</div>
          </div>
        )}
      </div>
    );
  }

  if (trace.step_type === 'CONTEXT_SELECTION') {
    const meta = trace.metadata_json || trace.metadata || {};
    return (
      <div className="space-y-1 text-[10px]">
        <div className="flex justify-between border-b border-[var(--color-hairline)] pb-0.5">
          <span className="text-[var(--color-muted)]">BUDGET</span>
          <span className="text-[var(--color-ink)] font-mono">{meta.budget || '500,000'} tokens</span>
        </div>
        <div className="flex justify-between border-b border-[var(--color-hairline)] pb-0.5">
          <span className="text-[var(--color-muted)]">RETAINED TURNS</span>
          <span className="text-[var(--color-ink)] font-mono">{meta.retained_turns ?? meta.turn_count ?? 'All'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--color-muted)]">REDUCTION</span>
          <span className="text-[#2c7a4b] font-mono font-medium">{meta.reduction_percentage ? `${meta.reduction_percentage.toFixed(1)}%` : '0%'}</span>
        </div>
      </div>
    );
  }

  if (trace.step_type === 'LLM_CALL') {
    return (
      <div className="space-y-1.5 text-[10px]">
        <div className="flex justify-between border-b border-[var(--color-hairline)] pb-0.5">
          <span className="text-[var(--color-muted)]">MODEL</span>
          <span className="text-[var(--color-ink)] font-mono">{trace.model || 'gemini-3.5-flash-lite'}</span>
        </div>
        <div className="flex justify-between border-b border-[var(--color-hairline)] pb-0.5">
          <span className="text-[var(--color-muted)]">TOKENS (IN/OUT)</span>
          <span className="text-[var(--color-ink)] font-mono">
            {trace.token_usage?.prompt_tokens || 0} / {trace.token_usage?.completion_tokens || 0}
          </span>
        </div>
        <div className="flex justify-between border-b border-[var(--color-hairline)] pb-0.5">
          <span className="text-[var(--color-muted)]">LATENCY</span>
          <span className="text-[var(--color-ink)] font-mono">{trace.duration_ms ? `${trace.duration_ms.toFixed(0)}ms` : '—'}</span>
        </div>
        <div className="text-[var(--color-muted)] mt-1 pt-1 line-clamp-3 text-[9px] font-mono">
          {trace.output_data?.content || ''}
        </div>
      </div>
    );
  }

  return (
    <div className="text-[var(--color-ink)] whitespace-pre-wrap break-words">
      {trace.output_data ? (typeof trace.output_data === 'string' ? trace.output_data : JSON.stringify(trace.output_data, null, 2)) : (trace.error ? JSON.stringify(trace.error) : '...')}
    </div>
  );
}

// The Chat workspace in "flight recorder" aesthetic
export default function Chat() {
  const [conversations, setConversations] = useState<any[]>([]);
  const [currentRun, setCurrentRun] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(() => 'chat_ui_' + Date.now());

  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/conversations');
      setConversations(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const loadConversation = async (id: string) => {
    setConversationId(id);
    setCurrentRun(null);
    try {
      const res = await axios.get(`http://localhost:8000/api/conversations/${id}/history`);
      setMessages(res.data.history);
      
      // Optionally load the last run for telemetry
      if (res.data.history.length > 0) {
        const lastMsg = res.data.history[res.data.history.length - 1];
        if (lastMsg.run_id) {
          const runRes = await axios.get(`http://localhost:8000/api/runs/${lastMsg.run_id}`);
          const tracesRes = await axios.get(`http://localhost:8000/api/runs/${lastMsg.run_id}/traces`);
          setCurrentRun({ ...runRes.data, traces: tracesRes.data });
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const startNewChat = () => {
    setConversationId('chat_ui_' + Date.now());
    setMessages([]);
    setCurrentRun(null);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await axios.post('http://localhost:8000/api/chat', {
        conversation_id: conversationId,
        message: input,
        history: messages
      });
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response, run_id: res.data.run_id }]);
      
      const runRes = await axios.get(`http://localhost:8000/api/runs/${res.data.run_id}`);
      const tracesRes = await axios.get(`http://localhost:8000/api/runs/${res.data.run_id}/traces`);
      
      setCurrentRun({
        ...runRes.data,
        traces: tracesRes.data
      });
      fetchConversations();
    } catch (err: any) {
      console.error(err);
      const errorMsg = err.response?.data?.detail || err.message || 'Unknown error occurred.';
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `SYSTEM ERROR: ${errorMsg}` 
      }]);
    }
    setLoading(false);
  };

  return (
    <div className="flex h-full w-full bg-[var(--color-surface)]">
      
      {/* Left Column: Past Chats */}
      <div className="w-[220px] bg-[var(--color-surface)] border-r border-[var(--color-hairline)] flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-[var(--color-hairline)] flex justify-between items-center">
          <h3 className="font-serif text-lg text-[var(--color-ink)]">Sessions</h3>
          <button 
            onClick={startNewChat}
            className="text-[18px] text-[var(--color-ink)] hover:text-[var(--color-muted)] font-mono leading-none"
            title="New Chat"
          >
            +
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {conversations.map(conv => (
            <div 
              key={conv.conversation_id}
              onClick={() => loadConversation(conv.conversation_id)}
              className={`p-3 text-[11px] font-mono cursor-pointer border transition-colors ${conversationId === conv.conversation_id ? 'border-[var(--color-ink)] bg-[var(--color-paper)] text-[var(--color-ink)]' : 'border-[var(--color-hairline)] hover:border-[var(--color-muted)] text-[var(--color-muted)] hover:text-[var(--color-ink)]'}`}
            >
              <div className="truncate mb-1">{conv.conversation_id.replace('chat_ui_', 'Session ')}</div>
              <div className="text-[9px] opacity-70">{new Date(conv.last_activity).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Middle Column: Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[var(--color-paper)] border-r border-[var(--color-hairline)]">
        <div className="px-6 py-4 border-b border-[var(--color-hairline)] flex items-center justify-between shrink-0">
          <div>
            <h2 className="font-serif text-xl text-[var(--color-ink)]">Active Session</h2>
            <div className="text-[11px] text-[var(--color-muted)] font-mono uppercase tracking-wider mt-1 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#2c7a4b]"></span> Tx/Rx Online
            </div>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-[var(--color-muted)] font-mono text-sm">
              [ AWAITING INPUT ]
            </div>
          )}
          
          {messages.map((m, i) => (
            <div key={i} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`px-4 py-3 max-w-[80%] ${m.role === 'user' ? 'bg-[var(--color-ink)] text-[var(--color-paper)]' : 'bg-[var(--color-surface)] border border-[var(--color-hairline)] text-[var(--color-ink)]'} text-[13px] leading-relaxed whitespace-pre-wrap`}>
                {m.content}
              </div>
              {m.role === 'assistant' && m.run_id && (
                <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-[var(--color-muted)]">
                  <span>RUN: {m.run_id.split('-')[0]}</span>
                  <span>•</span>
                  <Link 
                    to={`/runs/${m.run_id}`} 
                    className="underline hover:text-[var(--color-oxblood)] text-[var(--color-ink)] flex items-center gap-1"
                  >
                    INSPECT TRACE →
                  </Link>
                </div>
              )}
            </div>
          ))}
          
          {loading && (
            <div className="flex justify-start">
              <div className="px-4 py-3 bg-[var(--color-surface)] border border-[var(--color-hairline)] text-[var(--color-ink)] text-[13px] font-mono">
                [ PROCESSING... ]
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-[var(--color-hairline)] bg-[var(--color-surface)]">
          <div className="flex gap-2 max-w-3xl mx-auto relative group">
            <input 
              type="text" 
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder="ENTER COMMAND..."
              className="flex-1 pl-4 pr-16 py-3 bg-[var(--color-paper)] border border-[var(--color-hairline)] text-[13px] font-mono text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-ink)] transition-colors rounded-none"
            />
            <button 
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="absolute right-1 top-1 bottom-1 px-4 bg-[var(--color-ink)] text-[var(--color-paper)] text-[11px] font-mono uppercase tracking-widest hover:bg-[var(--color-muted)] disabled:opacity-30 transition-colors rounded-none"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Right Column: RAG Pipeline & Thought Process */}
      <div className="w-[300px] xl:w-[350px] bg-[var(--color-surface)] flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-[var(--color-hairline)] bg-[var(--color-paper)] sticky top-0 flex justify-between items-center">
          <h3 className="font-serif text-lg text-[var(--color-ink)]">RAG Telemetry</h3>
          <span className="font-mono text-[10px] text-[var(--color-muted)]">LIVE</span>
        </div>
        
        <div className="p-5 overflow-y-auto flex-1 font-mono text-[11px]">
          {!currentRun ? (
            <div className="text-[var(--color-muted)] text-center py-10 border border-dashed border-[var(--color-hairline)]">
              [ NO ACTIVE PIPELINE ]
            </div>
          ) : (
            <div className="space-y-6">
              
              <div className="space-y-2">
                <h4 className="small-caps text-[var(--color-muted)] mb-3 border-b border-[var(--color-hairline)] pb-1">Thought Process</h4>
                {currentRun.traces && currentRun.traces.length > 0 ? (
                  currentRun.traces.map((trace: any, idx: number) => (
                    <div key={idx} className="bg-[var(--color-paper)] border border-[var(--color-hairline)] p-3 mb-2.5">
                      <div className="flex items-center justify-between border-b border-[var(--color-hairline)] pb-1 mb-2">
                        <span className="text-[10px] font-mono text-[var(--color-oxblood)] font-medium tracking-wide">
                          [{trace.step_type}]
                        </span>
                        {trace.duration_ms > 0 && (
                          <span className="text-[9px] font-mono text-[var(--color-muted)]">
                            {trace.duration_ms.toFixed(0)}ms
                          </span>
                        )}
                      </div>
                      {renderTraceCard(trace)}
                    </div>
                  ))
                ) : (
                  <div className="bg-[var(--color-paper)] border border-[var(--color-hairline)] p-3">
                    <div className="text-[10px] text-[var(--color-muted)] mb-1">[llm_call]</div>
                    <div className="text-[var(--color-ink)] text-[10px]">
                      Analyzing intent...<br/>
                      Formulating response...<br/>
                      Using {currentRun.total_tokens} context window...
                    </div>
                  </div>
                )}
              </div>
              
              <div className="space-y-2">
                <h4 className="small-caps text-[var(--color-muted)] mb-3 border-b border-[var(--color-hairline)] pb-1">Execution Metrics</h4>
                <div className="flex justify-between border-b border-[var(--color-hairline)] pb-1">
                  <span className="text-[var(--color-muted)]">RUN ID</span>
                  <span className="text-[var(--color-ink)]">{currentRun.run_id.split('-')[0]}</span>
                </div>
                <div className="flex justify-between border-b border-[var(--color-hairline)] pb-1">
                  <span className="text-[var(--color-muted)]">TOKENS</span>
                  <span className="text-[var(--color-ink)]">{currentRun.total_tokens}</span>
                </div>
                <div className="flex justify-between border-b border-[var(--color-hairline)] pb-1">
                  <span className="text-[var(--color-muted)]">LATENCY</span>
                  <span className="text-[var(--color-ink)]">{(currentRun.total_latency_ms / 1000).toFixed(2)}s</span>
                </div>
                <div className="flex justify-between border-b border-[var(--color-hairline)] pb-1">
                  <span className="text-[var(--color-muted)]">STATUS</span>
                  <span className={currentRun.status === 'SUCCESS' ? 'text-[#2c7a4b]' : 'text-[var(--color-oxblood)]'}>
                    {currentRun.status}
                  </span>
                </div>
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
