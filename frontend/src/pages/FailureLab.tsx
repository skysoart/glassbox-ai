import { useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

interface TestResult {
  runId?: string;
  response?: string;
  error?: string;
  durationMs?: number;
}

export default function FailureLab() {
  const [runningWrongTool, setRunningWrongTool] = useState(false);
  const [wrongToolResult, setWrongToolResult] = useState<TestResult | null>(null);

  const [runningStressTest, setRunningStressTest] = useState(false);
  const [stressTestResult, setStressTestResult] = useState<TestResult | null>(null);

  const runWrongToolTest = async () => {
    setRunningWrongTool(true);
    setWrongToolResult(null);
    const start = performance.now();
    try {
      const res = await axios.post('http://localhost:8000/api/tests/failure-wrong-tool');
      const duration = performance.now() - start;
      setWrongToolResult({
        runId: res.data.run_id,
        response: res.data.response,
        error: res.data.error,
        durationMs: duration
      });
    } catch (err: any) {
      setWrongToolResult({
        error: err.response?.data?.detail || err.message || 'Request failed'
      });
    } finally {
      setRunningWrongTool(false);
    }
  };

  const runStressTest = async () => {
    setRunningStressTest(true);
    setStressTestResult(null);
    const start = performance.now();
    try {
      const res = await axios.post('http://localhost:8000/api/tests/stress-test');
      const duration = performance.now() - start;
      setStressTestResult({
        runId: res.data.run_id,
        response: res.data.response,
        error: res.data.error,
        durationMs: duration
      });
    } catch (err: any) {
      setStressTestResult({
        error: err.response?.data?.detail || err.message || 'Request failed'
      });
    } finally {
      setRunningStressTest(false);
    }
  };

  return (
    <div className="h-full bg-[var(--color-paper)] overflow-y-auto p-8 lg:p-12">
      <div className="max-w-4xl mx-auto space-y-12">
        
        {/* Header */}
        <div>
          <div className="text-[11px] font-mono text-[var(--color-muted)] uppercase tracking-widest mb-1">
            Diagnostic Test Harness • ISO/IEC 25010 Observability
          </div>
          <h1 className="font-serif text-3xl text-[var(--color-ink)]">Failure Lab & Benchmarks</h1>
          <p className="text-[13px] text-[var(--color-muted)] mt-2 leading-relaxed">
            Execute reproducible failure injections and stress-test scenarios against the live agent pipeline.
            Every test records a persistent trace in SQLite with full validation, replanning, and context reduction telemetry.
          </p>
        </div>

        {/* Test Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          
          {/* Test 01: Wrong Tool Recovery */}
          <div className="border border-[var(--color-hairline)] bg-[var(--color-surface)] p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-[var(--color-hairline)] pb-3 mb-4">
                <span className="font-mono text-[11px] text-[var(--color-oxblood)] font-bold tracking-wider">
                  DIAGNOSTIC 01
                </span>
                <span className="font-mono text-[10px] text-[var(--color-muted)]">VALIDATOR REPLAN</span>
              </div>
              
              <h3 className="font-serif text-xl text-[var(--color-ink)] mb-2">Wrong-Tool Recovery</h3>
              <p className="text-[12px] text-[var(--color-muted)] leading-relaxed mb-6">
                Injects a request demanding a non-existent tool (<code className="text-[var(--color-ink)]">send_email</code>).
                The validator intercepts the hallucinated capability, registers a <code className="text-[var(--color-ink)]">VALIDATION: FAILED</code> step, triggers a <code className="text-[var(--color-ink)]">REPLAN</code>, and returns a transparent recovery message.
              </p>
            </div>

            <div>
              <button
                onClick={runWrongToolTest}
                disabled={runningWrongTool}
                className="w-full py-2.5 px-4 bg-[var(--color-ink)] text-[var(--color-paper)] text-[11px] font-mono uppercase tracking-widest hover:bg-[var(--color-muted)] disabled:opacity-40 transition-colors"
              >
                {runningWrongTool ? '[ RUNNING INJECTION... ]' : 'EXECUTE WRONG-TOOL TEST'}
              </button>

              {wrongToolResult && (
                <div className="mt-4 border border-[var(--color-hairline)] bg-[var(--color-paper)] p-3 font-mono text-[11px] space-y-2">
                  <div className="flex justify-between items-center border-b border-[var(--color-hairline)] pb-1">
                    <span className="text-[var(--color-muted)]">STATUS</span>
                    <span className={wrongToolResult.error ? "text-[var(--color-oxblood)] font-bold" : "text-[#2c7a4b] font-bold"}>
                      {wrongToolResult.error ? 'FAILED' : 'RECOVERED'}
                    </span>
                  </div>
                  {wrongToolResult.durationMs && (
                    <div className="flex justify-between text-[var(--color-muted)]">
                      <span>DURATION</span>
                      <span>{(wrongToolResult.durationMs / 1000).toFixed(2)}s</span>
                    </div>
                  )}
                  {wrongToolResult.runId && (
                    <div className="flex justify-between items-center">
                      <span className="text-[var(--color-muted)]">TRACE</span>
                      <Link 
                        to={`/runs/${wrongToolResult.runId}`}
                        className="text-[var(--color-ink)] underline hover:text-[var(--color-oxblood)]"
                      >
                        Run {wrongToolResult.runId.split('-')[0]} ?
                      </Link>
                    </div>
                  )}
                  <div className="text-[11px] text-[var(--color-ink)] pt-1 border-t border-[var(--color-hairline)] whitespace-pre-wrap">
                    {wrongToolResult.response || wrongToolResult.error}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Test 02: 20-Turn Stress Test */}
          <div className="border border-[var(--color-hairline)] bg-[var(--color-surface)] p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-[var(--color-hairline)] pb-3 mb-4">
                <span className="font-mono text-[11px] text-[#2c7a4b] font-bold tracking-wider">
                  DIAGNOSTIC 02
                </span>
                <span className="font-mono text-[10px] text-[var(--color-muted)]">20+ TURN DRIFT</span>
              </div>
              
              <h3 className="font-serif text-xl text-[var(--color-ink)] mb-2">Context Retention Benchmark</h3>
              <p className="text-[12px] text-[var(--color-muted)] leading-relaxed mb-6">
                Injects an early critical memory (<code className="text-[var(--color-ink)]">OMEGA-99</code>), generates 20 conversational filler turns to induce context drift, and queries the secret on turn 21. Tests token pruning and memory recall under load.
              </p>
            </div>

            <div>
              <button
                onClick={runStressTest}
                disabled={runningStressTest}
                className="w-full py-2.5 px-4 bg-[var(--color-ink)] text-[var(--color-paper)] text-[11px] font-mono uppercase tracking-widest hover:bg-[var(--color-muted)] disabled:opacity-40 transition-colors"
              >
                {runningStressTest ? '[ BENCHMARKING 20 TURNS... ]' : 'EXECUTE 20-TURN STRESS TEST'}
              </button>

              {stressTestResult && (
                <div className="mt-4 border border-[var(--color-hairline)] bg-[var(--color-paper)] p-3 font-mono text-[11px] space-y-2">
                  <div className="flex justify-between items-center border-b border-[var(--color-hairline)] pb-1">
                    <span className="text-[var(--color-muted)]">RECALL STATUS</span>
                    <span className={stressTestResult.response?.includes('OMEGA-99') ? "text-[#2c7a4b] font-bold" : "text-[var(--color-oxblood)] font-bold"}>
                      {stressTestResult.response?.includes('OMEGA-99') ? 'ACCURATE (OMEGA-99 FOUND)' : 'DEGRADED'}
                    </span>
                  </div>
                  {stressTestResult.durationMs && (
                    <div className="flex justify-between text-[var(--color-muted)]">
                      <span>DURATION</span>
                      <span>{(stressTestResult.durationMs / 1000).toFixed(2)}s</span>
                    </div>
                  )}
                  {stressTestResult.runId && (
                    <div className="flex justify-between items-center">
                      <span className="text-[var(--color-muted)]">TRACE</span>
                      <Link 
                        to={`/runs/${stressTestResult.runId}`}
                        className="text-[var(--color-ink)] underline hover:text-[var(--color-oxblood)]"
                      >
                        Run {stressTestResult.runId.split('-')[0]} ?
                      </Link>
                    </div>
                  )}
                  <div className="text-[11px] text-[var(--color-ink)] pt-1 border-t border-[var(--color-hairline)] whitespace-pre-wrap">
                    {stressTestResult.response || stressTestResult.error}
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Technical Architecture Footnote */}
        <div className="border-t border-[var(--color-hairline)] pt-6 font-mono text-[11px] text-[var(--color-muted)] space-y-1">
          <div>TELEMETRY PIPELINE: SQLite (runs, trace_steps) via SQLAlchemy ORM</div>
          <div>BOUNDING POLICY: ContextManager strict token pruning with system instruction preservation</div>
        </div>

      </div>
    </div>
  );
}

