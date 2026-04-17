const riskColors = {
  Low: 'bg-low/20 text-low border-low/60',
  Medium: 'bg-medium/20 text-medium border-medium/60',
  High: 'bg-high/20 text-high border-high/60',
};

function LoadingPulse() {
  return (
    <div className="relative flex h-14 w-14 items-center justify-center">
      <span className="absolute h-14 w-14 rounded-full bg-cyan-300/25 animate-pulseRing" />
      <span className="h-4 w-4 rounded-full bg-cyan-200" />
    </div>
  );
}

export default function RiskCard({ result, loading, error }) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-white/15 bg-slate-900/75 p-6 shadow-panel">
        <div className="flex items-center gap-4">
          <LoadingPulse />
          <div>
            <p className="font-display text-lg text-cyan-100">Analyzing location...</p>
            <p className="text-sm text-slate-300">Running spatial checks on GIS layers.</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-high/50 bg-high/15 p-6 text-sm text-red-100 shadow-panel">
        {error}
      </div>
    );
  }

  if (!result) {
    return (
      <div className="rounded-2xl border border-white/15 bg-slate-900/75 p-6 shadow-panel">
        <p className="font-display text-xl text-slate-100">No report generated yet</p>
        <p className="mt-2 text-sm text-slate-300">
          Enter latitude and longitude, then run analysis to view the land safety report.
        </p>
      </div>
    );
  }

  const riskClass = riskColors[result.risk_level] ?? riskColors.Low;

  return (
    <div className="rounded-2xl border border-white/15 bg-slate-900/75 p-6 shadow-panel">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl text-white">Land Safety Report</h2>
        <span className={`rounded-full border px-3 py-1 text-sm font-semibold ${riskClass}`}>
          {result.risk_level}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-200">
        <div className="rounded-lg bg-slate-800/65 p-3">
          <p className="text-slate-400">Risk Score</p>
          <p className="font-display text-2xl">{result.risk_score}/100</p>
        </div>
        <div className="rounded-lg bg-slate-800/65 p-3">
          <p className="text-slate-400">Flags</p>
          <p className="font-display text-2xl">{result.flags.length}</p>
        </div>
      </div>

      <div className="mt-4">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-400">Risk Flags</p>
        {result.flags.length === 0 ? (
          <p className="mt-2 text-sm text-slate-300">No risk flags detected.</p>
        ) : (
          <ul className="mt-2 space-y-2 text-sm text-slate-100">
            {result.flags.map((flag) => (
              <li key={flag} className="rounded-md bg-slate-800/65 px-3 py-2">
                {flag}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4 rounded-lg bg-slate-800/65 p-4 text-sm leading-relaxed text-slate-100">
        {result.explanation}
      </div>
    </div>
  );
}
