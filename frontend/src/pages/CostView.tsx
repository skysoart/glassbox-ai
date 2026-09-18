import { useState, useEffect } from 'react';
import axios from 'axios';

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
            <text x={x + barWidth/2} y={y - 10} fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink)" textAnchor="middle" opacity="0" className="group-hover:opacity-100 transition-opacity">
              ${d.toFixed(4)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function CostView() {
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('http://localhost:8000/api/runs').then(res => {
      setRuns(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-6 font-mono text-[13px] text-[var(--color-muted)]">[ LOADING COSTS... ]</div>;

  const totalSpend = runs.reduce((acc, r) => acc + r.total_cost, 0);
  const totalTokensIn = runs.reduce((acc, r) => acc + (r.total_input_tokens || 0), 0);
  const totalTokensOut = runs.reduce((acc, r) => acc + (r.total_output_tokens || 0), 0);
  
  // Cost per run
  const runCosts = runs.map(r => r.total_cost).reverse();

  return (
    <div className="h-full bg-[var(--color-paper)] overflow-y-auto p-12">
      <div className="max-w-4xl mx-auto">
        <h1 className="font-serif text-3xl text-[var(--color-ink)] mb-12">Cost & Token Analysis</h1>

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
                  <th className="py-2 font-normal text-right">Tokens In</th>
                  <th className="py-2 font-normal text-right">Tokens Out</th>
                  <th className="py-2 font-normal text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                <tr className="border-b border-[var(--color-hairline)] hover:bg-[var(--color-surface)]">
                  <td className="py-2">gemini-3.5-flash-lite</td>
                  <td className="py-2 text-right">{totalTokensIn.toLocaleString()}</td>
                  <td className="py-2 text-right">{totalTokensOut.toLocaleString()}</td>
                  <td className="py-2 text-right">${totalSpend.toFixed(4)}</td>
                </tr>
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
                  <td className="py-2 text-right">${totalSpend.toFixed(4)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
