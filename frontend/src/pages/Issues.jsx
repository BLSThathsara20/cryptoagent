import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchAPI, postAPI } from '../api';

const SEVERITY = {
  critical: { dot: 'bg-red-500', badge: 'bg-red-900/40 text-red-400', label: 'Critical' },
  error: { dot: 'bg-orange-500', badge: 'bg-orange-900/40 text-orange-400', label: 'Error' },
  warning: { dot: 'bg-yellow-500', badge: 'bg-yellow-900/40 text-yellow-400', label: 'Warning' },
  info: { dot: 'bg-blue-500', badge: 'bg-blue-900/40 text-blue-400', label: 'Info' },
};

const STATUS = {
  healthy: { color: 'text-accent-green', label: 'Healthy' },
  degraded: { color: 'text-accent-yellow', label: 'Degraded' },
  critical: { color: 'text-accent-red', label: 'Critical' },
  unknown: { color: 'text-gray-400', label: 'Unknown' },
};

function HealthRing({ score, status }) {
  const st = STATUS[status] || STATUS.unknown;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;
  const stroke = score >= 80 ? '#22c55e' : score >= 50 ? '#eab308' : '#ef4444';

  return (
    <div className="flex flex-col items-center">
      <svg width="100" height="100" className="-rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#374151" strokeWidth="8" />
        <circle
          cx="50" cy="50" r="40" fill="none" stroke={stroke} strokeWidth="8"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
        />
      </svg>
      <div className="text-center -mt-16">
        <div className="text-2xl font-bold">{Math.round(score)}</div>
        <div className={`text-xs ${st.color}`}>{st.label}</div>
      </div>
    </div>
  );
}

export default function Issues() {
  const [data, setData] = useState(null);
  const [validating, setValidating] = useState(false);

  const load = () => fetchAPI('/issues').then(setData).catch(console.error);

  useEffect(() => {
    load();
    const interval = setInterval(load, 20000);
    return () => clearInterval(interval);
  }, []);

  const runValidation = async () => {
    setValidating(true);
    try {
      await postAPI('/issues/validate');
      await load();
    } finally {
      setValidating(false);
    }
  };

  const resolveIssue = async (id) => {
    await postAPI(`/issues/${id}/resolve`);
    load();
  };

  if (!data) {
    return <div className="p-8 text-gray-500">Loading validation status...</div>;
  }

  return (
    <div className="p-4 max-w-[1200px] mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Issues & Validation</h1>
          <p className="text-sm text-gray-500 mt-1">
            Validation Agent runs every 15 min — health, accuracy, and system checks
          </p>
        </div>
        <button
          onClick={runValidation}
          disabled={validating}
          className="px-4 py-2 bg-accent-blue hover:bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50"
        >
          {validating ? 'Running checks...' : 'Run Validation Now'}
        </button>
      </div>

      {/* Health overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card flex flex-col items-center justify-center">
          <HealthRing score={data.health_score ?? 0} status={data.overall_status} />
          <p className="text-xs text-gray-500 mt-2">System Health</p>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-accent-blue">{data.accuracy_score ?? 0}%</div>
          <p className="text-xs text-gray-500 mt-1">Trade Accuracy</p>
          <p className="text-[10px] text-gray-600 mt-2">Recent closed trades win rate</p>
        </div>
        <div className="card text-center">
          <div className={`text-3xl font-bold ${data.open_count > 0 ? 'text-accent-yellow' : 'text-accent-green'}`}>
            {data.open_count}
          </div>
          <p className="text-xs text-gray-500 mt-1">Open Issues</p>
          <p className="text-[10px] text-gray-600 mt-2">
            {data.critical_count} critical · {data.warning_count} warnings
          </p>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">Last validation</div>
          <div className="text-sm font-medium mt-1">
            {data.last_validation_at
              ? new Date(data.last_validation_at).toLocaleString()
              : 'Never'}
          </div>
          <Link to="/insights" className="text-xs text-accent-blue hover:underline mt-3 inline-block">
            View performance →
          </Link>
        </div>
      </div>

      {/* Latest checks */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Latest Validation Checks</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {(data.latest_checks || []).map((c, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 p-2 rounded-lg text-xs ${
                c.status === 'pass' ? 'bg-green-900/10' : 'bg-red-900/10'
              }`}
            >
              <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${
                c.status === 'pass' ? 'bg-accent-green' : 'bg-accent-red'
              }`} />
              <div>
                <div className="font-medium">{c.name}</div>
                <div className="text-gray-500">{c.message}</div>
                <div className="text-gray-600 capitalize">{c.category}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Open issues */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          Open Issues ({data.open_count})
        </h3>
        {data.open_count === 0 ? (
          <div className="text-center py-8 text-accent-green">
            <p className="text-lg font-medium">All clear</p>
            <p className="text-xs text-gray-500 mt-1">No open issues — validation agent found no problems</p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.open_issues.map((issue) => {
              const sev = SEVERITY[issue.severity] || SEVERITY.info;
              return (
                <div key={issue.id} className="border border-dark-600 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span className={`w-2.5 h-2.5 rounded-full mt-1 ${sev.dot}`} />
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm">{issue.title}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded ${sev.badge}`}>{sev.label}</span>
                          <span className="text-[10px] text-gray-600 capitalize">{issue.category}</span>
                        </div>
                        <p className="text-sm text-gray-400 mt-1">{issue.message}</p>
                        <p className="text-[10px] text-gray-600 mt-1">
                          {issue.created_at ? new Date(issue.created_at).toLocaleString() : ''} · {issue.source}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => resolveIssue(issue.id)}
                      className="text-xs px-2 py-1 rounded bg-dark-700 hover:bg-dark-600 shrink-0"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Autopilot issues */}
      {(data.autopilot_issues?.length ?? 0) > 0 && (
        <div className="card border border-accent-yellow/30">
          <h3 className="text-sm font-semibold text-accent-yellow mb-2">Autopilot Notes</h3>
          <ul className="text-sm text-gray-400 space-y-1">
            {data.autopilot_issues.map((msg, i) => (
              <li key={i}>• {msg}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Validation history */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Recent Validation Runs</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-dark-600 text-gray-400">
                <th className="py-2 text-left">Time</th>
                <th className="py-2 text-left">Status</th>
                <th className="py-2 text-right">Health</th>
                <th className="py-2 text-right">Accuracy</th>
                <th className="py-2 text-right">Passed</th>
                <th className="py-2 text-right">Failed</th>
              </tr>
            </thead>
            <tbody>
              {(data.recent_validations || []).map((r) => (
                <tr key={r.id} className="border-b border-dark-700/50">
                  <td className="py-2 text-gray-500">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                  <td className={`py-2 capitalize ${STATUS[r.overall_status]?.color || ''}`}>
                    {r.overall_status}
                  </td>
                  <td className="py-2 text-right">{r.health_score}%</td>
                  <td className="py-2 text-right">{r.accuracy_score ?? 0}%</td>
                  <td className="py-2 text-right text-accent-green">{r.checks_passed}</td>
                  <td className="py-2 text-right text-accent-red">{r.checks_failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
