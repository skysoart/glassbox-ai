import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

export default function Incidents() {
  const [failedRuns, setFailedRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/runs').then(res => {
      setFailedRuns(res.data.filter((r: any) => r.status === 'FAILED'));
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING INCIDENTS... ]</div>;

  return (
    <div className="h-full bg-[var(--color-paper)] overflow-y-auto p-12">
      <div className="max-w-3xl mx-auto">
        <h1 className="font-serif text-3xl text-[var(--color-ink)] mb-12 flex items-center gap-4">
          Incident Reports
          <span className="bg-[var(--color-oxblood)] text-[var(--color-paper)] text-[12px] font-mono px-2 py-0.5 align-middle">
            {failedRuns.length} OPEN
          </span>
        </h1>

        <div className="space-y-12">
          {failedRuns.length === 0 ? (
            <div className="text-[var(--color-muted)] font-mono text-[13px]">No incidents found.</div>
          ) : failedRuns.map((r) => (
            <div key={r.run_id} className="border border-[var(--color-oxblood)] bg-[var(--color-surface)]">
              <div className="border-b border-[var(--color-oxblood)] bg-[var(--color-oxblood)]/5 p-4 flex justify-between items-start">
                <div>
                  <div className="font-mono text-[11px] text-[var(--color-oxblood)] mb-1">
                    {new Date(r.start_time).toLocaleString()}
                  </div>
                  <h3 className="text-lg font-serif text-[var(--color-ink)]">Run <Link to={`/runs/${r.run_id}`} className="underline hover:text-[var(--color-oxblood)]">{r.run_id.split('-')[0]}</Link> Failed</h3>
                </div>
                <Link to={`/runs/${r.run_id}`} className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-ink)] hover:text-[var(--color-oxblood)] border border-[var(--color-ink)] hover:border-[var(--color-oxblood)] px-3 py-1">
                  Inspect Trace
                </Link>
              </div>
              <div className="p-6 text-[13px] text-[var(--color-ink)] leading-relaxed space-y-4">
                <p>
                  <strong>Context:</strong> Agent encountered a failure during conversation <em>{r.conversation_id}</em>.
                </p>
                <div className="bg-[var(--color-paper)] border border-[var(--color-hairline)] p-4 font-mono text-[11px] text-[var(--color-muted)]">
                  Tokens In: {r.total_input_tokens || 0}<br />
                  Tokens Out: {r.total_output_tokens || 0}<br />
                  Latency: {(r.total_latency_ms / 1000).toFixed(2)}s
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
