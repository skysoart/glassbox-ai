import { useState, useEffect } from 'react';
import { api, describeError, formatCost, totalCost, type Run } from '../lib/api';

interface ModelRow {
  model: string;
  calls: number;
  cost: number;
  cost_known: boolean;
  input_tokens: number;
  output_tokens: number;
}

function BarChart({ data, width = 600, height = 200 }: { data: number[], width?: number, height?: number }) {
  const max = Math.max(...data, 0.0001);
  const barWidth = Math.max((width / Math.max(data.length, 1)) - 4, 2);

  return (
    <svg width={width} height={height} className="overflow-visible block">
      {/* Y Axis line */}
      <line x1="0" y1="0" x2="0" y2={height} stroke="var(--color-hairline)" strokeWidth="1" />
      {/* X Axis line */}
      <line x1="0" y1={height} x2={width} y2={height} stroke="var(--color-hairline)" strokeWidth="1" />

      {/* Y Axis labels */}
      <text x="-10" y="10" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-muted)" textAnchor="end">${max.toFixed(4)}</text>
      <text x="-10" y={height} fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-muted)" textAnchor="end">$0</text>

      {/* Grid line max */}
      <line x1="0" y1="0" x2={width} y2="0" stroke="var(--color-hairline)" strokeWidth="1" strokeDasharray="2 4" />

      {/* Bars */}
      {data.map((d, i) => {
        const x = (i * (width / data.length)) + 2;
        const barH = (d / max) * height;
        const y = height - barH;

        return (
          <g key={i} className="group">
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barH}
              fill="transparent"
              stroke="var(--color-ink)"
              strokeWidth="1"
              className="transition-all hover:fill-[var(--color-hairline)]"
            />
            {/* Tooltip text */}
            <text x={x + barWidth / 2} y={y - 10} fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink)" textAnchor="middle" opacity="0" className="group-hover:opacity-100 transition-opacity">
              ${d.toFixed(4)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function CostView() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [models, setModels] = useState<ModelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.get('/api/runs'), api.get('/api/stats/models')])
      .then(([runsRes, modelsRes]) => {
        setRuns(runsRes.data);
        setModels(modelsRes.data);
      })
      .catch(err => setError(describeError(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING COSTS... ]</div>;
  if (error) return <div className="p-6 font-mono text-[13px] text-[var(--color-oxblood)]">[ ERROR ] {error}</div>;

  const { total: totalSpend, complete: spendComplete } = totalCost(runs);
  const totalTokensIn = runs.reduce((acc, r) => acc + (r.total_input_tokens || 0), 0);
  const totalTokensOut = runs.reduce((acc, r) => acc + (r.total_output_tokens || 0), 0);
  const unpricedModels = models.filter(m => !m.cost_known).map(m => m.model);

  // Cost per run, oldest first.
  const runCosts = runs.map(r => r.total_cost).reverse();

  return (
    <div className="h-full bg-[var(--color-paper)] overflow-y-auto p-12">
      <div className="max-w-4xl mx-auto">
        <h1 className="font-serif text-3xl text-[var(--color-ink)] mb-4">Cost &amp; Token Analysis</h1>

        {unpricedModels.length > 0 && (
          <div className="mb-8 border border-[var(--color-oxblood)] bg-[var(--color-oxblood)]/5 px-4 py-3 font-mono text-[12px] text-[var(--color-ink)]">
            <span className="text-[var(--color-oxblood)]">[ INCOMPLETE ]</span>{' '}
            No price is configured for {unpricedModels.join(', ')}, so totals below are a lower bound.
            Add the model to <span className="text-[var(--color-muted)]">backend/pricing.json</span> or set{' '}
            <span className="text-[var(--color-muted)]">LLM_PRICE_INPUT</span> /{' '}
            <span className="text-[var(--color-muted)]">LLM_PRICE_OUTPUT</span>.
          </div>
        )}

        <div className="mb-16">
          <h2 className="small-caps text-[var(--color-muted)] mb-8">Cost Per Run (Lifetime)</h2>
          <div className="ml-12 mt-8">
            <BarChart data={runCosts} width={800} height={200} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-12">
          <div>
            <h2 className="small-caps text-[var(--color-muted)] mb-4">Breakdown by Model</h2>
            <table className="w-full text-left border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-[var(--color-hairline)] text-[var(--color-muted)] font-normal">
                  <th className="py-2 font-normal">Model</th>
                  <th className="py-2 font-normal text-right">Calls</th>
                  <th className="py-2 font-normal text-right">Tokens In</th>
                  <th className="py-2 font-normal text-right">Tokens Out</th>
                  <th className="py-2 font-normal text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {models.length === 0 ? (
                  <tr><td colSpan={5} className="py-2 text-[var(--color-muted)]">No model activity recorded.</td></tr>
                ) : models.map(m => (
                  <tr key={m.model} className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                    <td className="py-2">{m.model}</td>
                    <td className="py-2 text-right">{m.calls}</td>
                    <td className="py-2 text-right">{m.input_tokens.toLocaleString()}</td>
                    <td className="py-2 text-right">{m.output_tokens.toLocaleString()}</td>
                    <td className={`py-2 text-right ${m.cost_known ? '' : 'text-[var(--color-muted)]'}`}>
                      {formatCost(m.cost, m.cost_known)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h2 className="small-caps text-[var(--color-muted)] mb-4">Aggregate Metrics</h2>
            <table className="w-full text-left border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-[var(--color-hairline)] text-[var(--color-muted)] font-normal">
                  <th className="py-2 font-normal">Metric</th>
                  <th className="py-2 font-normal text-right">Value</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                <tr className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                  <td className="py-2">Total Runs</td>
                  <td className="py-2 text-right">{runs.length}</td>
                </tr>
                <tr className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                  <td className="py-2">Total Tokens</td>
                  <td className="py-2 text-right">{(totalTokensIn + totalTokensOut).toLocaleString()}</td>
                </tr>
                <tr className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                  <td className="py-2">Total Spent</td>
                  <td className="py-2 text-right">
                    {formatCost(totalSpend)}{spendComplete ? '' : ' +'}
                  </td>
                </tr>
              </tbody>
            </table>
            {!spendComplete && (
              <p className="mt-2 text-[11px] font-mono text-[var(--color-muted)]">
                &ldquo;+&rdquo; marks a lower bound: some calls used an unpriced model.
              </p>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
