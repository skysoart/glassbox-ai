import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api, describeError, type Run } from '../lib/api';

export default function Incidents() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get('/api/runs')
      .then(res => setRuns(res.data))
      .catch(err => setError(describeError(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING INCIDENTS... ]</div>;
  if (error) return <div className="p-6 font-mono text-[13px] text-[var(--color-oxblood)]">[ ERROR ] {error}</div>;

  const failedRuns = runs.filter(r => r.status === 'FAILED');
  // Runs that hit a failure but still produced an answer. These used to be
  // indistinguishable from clean runs, because nothing ever set RECOVERED.
  const recoveredRuns = runs.filter(r => r.status === 'RECOVERED');

  return (
    <div className="h-full bg-[var(--color-paper)] overflow-y-auto p-12">
      <div className="max-w-3xl mx-auto">
        <h1 className="font-serif text-3xl text-[var(--color-ink)] mb-4 flex items-center gap-4">
          Incident Reports
          <span className="bg-[var(--color-oxblood)] text-[var(--color-paper)] text-[12px] font-mono px-2 py-0.5 align-middle">
            {failedRuns.length} OPEN
          </span>
          {recoveredRuns.length > 0 && (
            <span className="border border-[var(--color-hairline)] text-[var(--color-muted)] text-[12px] font-mono px-2 py-0.5 align-middle">
              {recoveredRuns.length} RECOVERED
            </span>
          )}
        </h1>

        <p className="text-[13px] text-[var(--color-muted)] mb-12">
          Open incidents are runs that ended without an answer. Recovered runs hit a
          validation or tool failure and still completed.
        </p>

        <div className="space-y-12">
          {failedRuns.length === 0 ? (
            <div className="text-[var(--color-muted)] font-mono text-[13px]">No open incidents.</div>
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
                  Failures: {r.failure_count || 0}<br />
                  Retries: {r.retry_count || 0}<br />
                  Latency: {((r.total_latency_ms || 0) / 1000).toFixed(2)}s
                </div>
              </div>
            </div>
          ))}
        </div>

        {recoveredRuns.length > 0 && (
          <div className="mt-16">
            <h2 className="small-caps text-[var(--color-muted)] mb-4">Recovered</h2>
            <table className="w-full text-left border-collapse text-[13px] font-mono">
              <thead>
                <tr className="border-b border-[var(--color-hairline)] text-[var(--color-muted)]">
                  <th className="py-2 font-normal">Run</th>
                  <th className="py-2 font-normal">Started</th>
                  <th className="py-2 font-normal text-right">Failures</th>
                  <th className="py-2 font-normal text-right">Retries</th>
                </tr>
              </thead>
              <tbody>
                {recoveredRuns.map(r => (
                  <tr key={r.run_id} className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                    <td className="py-2">
                      <Link to={`/runs/${r.run_id}`} className="underline hover:text-[var(--color-oxblood)]">
                        {r.run_id.split('-')[0]}
                      </Link>
                    </td>
                    <td className="py-2 text-[var(--color-muted)]">{new Date(r.start_time).toLocaleString()}</td>
                    <td className="py-2 text-right">{r.failure_count || 0}</td>
                    <td className="py-2 text-right">{r.retry_count || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
