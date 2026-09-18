import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';



export default function RunsIndex() {
  const [runs, setRuns] = useState<any[]>([]);
  const [sortField, setSortField] = useState<string>('start_time');
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/runs').then(res => {
      setRuns(res.data);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setRuns(prev => prev.filter(r => r.run_id !== id));
  };

  const sortedRuns = [...runs].sort((a, b) => {
    let valA = a[sortField];
    let valB = b[sortField];
    if (valA < valB) return -1 * sortDir;
    if (valA > valB) return 1 * sortDir;
    return 0;
  });

  const toggleSort = (field: string) => {
    if (sortField === field) setSortDir(sortDir === 1 ? -1 : 1);
    else { setSortField(field); setSortDir(-1); }
  };

  // Aggregates
  const totalRuns = runs.length;
  const totalTokens = runs.reduce((acc, r) => acc + r.total_tokens, 0);
  const totalSpend = runs.reduce((acc, r) => acc + r.total_cost, 0);
  const totalFailures = runs.filter(r => r.status === 'FAILED').length;

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING TELEMETRY... ]</div>;

  return (
    <div className="flex flex-col h-full bg-[var(--color-paper)] p-6 overflow-auto">
      
      <div className="mb-6 flex justify-between items-end">
        <h1 className="font-serif text-3xl text-[var(--color-ink)]">Runs</h1>
        
        {/* Global Metrics Strip */}
        <div className="flex gap-8 font-mono text-[13px] border border-[var(--color-hairline)] bg-[var(--color-surface)] px-4 py-2 rounded-[2px]">
          <div className="flex flex-col">
            <span className="small-caps text-[var(--color-muted)]">Total Runs</span>
            <span className="text-[var(--color-ink)]">{totalRuns}</span>
          </div>
          <div className="flex flex-col">
            <span className="small-caps text-[var(--color-muted)]">Tokens</span>
            <span className="text-[var(--color-ink)]">{totalTokens.toLocaleString()}</span>
          </div>
          <div className="flex flex-col">
            <span className="small-caps text-[var(--color-muted)]">Spend</span>
            <span className="text-[var(--color-ink)]">${totalSpend.toFixed(4)}</span>
          </div>
          <div className="flex flex-col">
            <span className="small-caps text-[var(--color-muted)]">Failures</span>
            <span className={totalFailures > 0 ? "text-[var(--color-oxblood)] font-medium" : "text-[var(--color-ink)]"}>
              {totalFailures}
            </span>
          </div>
        </div>
      </div>

      <div className="border border-[var(--color-hairline)] bg-[var(--color-surface)] rounded-[2px] overflow-hidden">
        <table className="w-full text-[13px] text-left border-collapse">
          <thead>
            <tr className="border-b border-[var(--color-hairline)] bg-[var(--color-paper)]">
              <th className="py-2 px-3 font-medium cursor-pointer hover:bg-[var(--color-hairline)]" onClick={() => toggleSort('run_id')}>Run ID</th>
              <th className="py-2 px-3 font-medium cursor-pointer hover:bg-[var(--color-hairline)]" onClick={() => toggleSort('conversation_id')}>Name</th>
              <th className="py-2 px-3 font-medium cursor-pointer hover:bg-[var(--color-hairline)]" onClick={() => toggleSort('start_time')}>Started</th>
              <th className="py-2 px-3 font-medium cursor-pointer hover:bg-[var(--color-hairline)]" onClick={() => toggleSort('status')}>Status</th>
              <th className="py-2 px-3 font-medium text-right cursor-pointer hover:bg-[var(--color-hairline)]">Turns</th>
              <th className="py-2 px-3 font-medium text-right cursor-pointer hover:bg-[var(--color-hairline)]">Tokens</th>
              <th className="py-2 px-3 font-medium text-right cursor-pointer hover:bg-[var(--color-hairline)]" onClick={() => toggleSort('total_cost')}>Cost</th>
              <th className="py-2 px-3 font-medium text-right">Latency</th>
              <th className="py-2 px-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {sortedRuns.map((r) => (
              <tr key={r.run_id} className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-paper)] group">
                <td className="py-2 px-3 text-[var(--color-ink)] font-medium group-hover:underline">
                  <Link to={`/runs/${r.run_id}`}>{r.run_id.split('-')[0]}</Link>
                </td>
                <td className="py-2 px-3 text-[var(--color-muted)] truncate max-w-[150px]">
                  {r.conversation_id}
                </td>
                <td className="py-2 px-3 text-[var(--color-muted)]">
                  {new Date(r.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </td>
                <td className="py-2 px-3">
                  <span className={`inline-flex items-center gap-1 ${r.status !== 'SUCCESS' ? 'text-[var(--color-oxblood)]' : 'text-[var(--color-ink)]'}`}>
                    {r.status !== 'SUCCESS' ? '×' : '✓'} {r.status}
                  </span>
                </td>
                <td className="py-2 px-3 text-right">{r.llm_call_count || 1}</td>
                <td className="py-2 px-3 text-right text-[var(--color-muted)]">
                  {(r.total_tokens / 1000).toFixed(1)}k
                </td>
                <td className="py-2 px-3 text-right">${r.total_cost.toFixed(4)}</td>
                <td className="py-2 px-3 text-right text-[var(--color-muted)]">
                  {(r.total_latency_ms / 1000).toFixed(2)}s
                </td>
                <td className="py-2 px-3 text-right">
                  <button 
                    onClick={(e) => handleDelete(r.run_id, e)}
                    className="text-[var(--color-muted)] hover:text-[var(--color-oxblood)] opacity-0 group-hover:opacity-100 transition-opacity small-caps"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
