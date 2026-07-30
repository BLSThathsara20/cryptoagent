import { useState } from 'react';
import { fetchAPI, postAPI } from '../api';
import { usePolling } from '../hooks/useLive';

const STATUS_STYLE = {
  connected: { dot: 'bg-accent-green', label: 'Connected', text: 'text-accent-green' },
  error: { dot: 'bg-accent-red', label: 'Error', text: 'text-accent-red' },
  not_configured: { dot: 'bg-accent-yellow', label: 'Not configured', text: 'text-accent-yellow' },
  unknown: { dot: 'bg-gray-500', label: 'Unknown', text: 'text-gray-400' },
};

export default function LLMUsagePanel() {
  const [usage, setUsage] = useState(null);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setUsage(await fetchAPI('/llm/usage'));
  };

  usePolling(load, 15000);

  const testApi = async () => {
    setTesting(true);
    try {
      await postAPI('/llm/test');
      await load();
    } finally {
      setTesting(false);
    }
  };

  if (!usage) {
    return <div className="card text-gray-500 text-sm">Loading AI usage...</div>;
  }

  const st = STATUS_STYLE[usage.api_status] || STATUS_STYLE.unknown;
  const maxHistory = Math.max(...(usage.monthly_history?.map((h) => h.spent_usd) || [1]), usage.budget_usd, 0.01);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-300">OpenAI / AI Usage</h3>
          <p className="text-xs text-gray-500 mt-0.5">{usage.model} · {usage.current_month}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 text-xs ${st.text}`}>
            <span className={`w-2 h-2 rounded-full ${st.dot}`} />
            {st.label}
          </span>
          <button
            onClick={testApi}
            disabled={testing}
            className="text-xs px-2 py-1 rounded bg-dark-700 hover:bg-dark-600 disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test API'}
          </button>
        </div>
      </div>

      {usage.api_message && usage.api_status === 'error' && (
        <p className="text-xs text-accent-red mb-3">{usage.api_message}</p>
      )}

      {/* Budget bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-gray-400">This month</span>
          <span>
            <span className={usage.budget_exceeded ? 'text-accent-red font-medium' : 'text-white'}>
              ${usage.spent_usd?.toFixed(4)}
            </span>
            <span className="text-gray-500"> / ${usage.budget_usd} budget</span>
          </span>
        </div>
        <div className="h-3 bg-dark-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              usage.budget_used_percent >= 100 ? 'bg-accent-red' :
              usage.budget_used_percent >= 80 ? 'bg-accent-yellow' : 'bg-accent-blue'
            }`}
            style={{ width: `${Math.min(usage.budget_used_percent, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-gray-600 mt-1">
          <span>{usage.budget_used_percent}% used</span>
          <span>${usage.budget_remaining_usd?.toFixed(4)} remaining</span>
        </div>
        {usage.budget_exceeded && (
          <p className="text-xs text-accent-yellow mt-2">
            Monthly budget reached — agent uses rule-based signals until next month
          </p>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-4 text-center">
        <div className="bg-dark-700/50 rounded-lg p-2">
          <div className="text-xs text-gray-500">API Calls</div>
          <div className="font-medium">{usage.calls_this_month}</div>
        </div>
        <div className="bg-dark-700/50 rounded-lg p-2">
          <div className="text-xs text-gray-500">Tokens</div>
          <div className="font-medium">{usage.tokens_this_month?.toLocaleString()}</div>
        </div>
        <div className="bg-dark-700/50 rounded-lg p-2">
          <div className="text-xs text-gray-500">Est. Spend</div>
          <div className="font-medium text-accent-blue">${usage.spent_usd?.toFixed(4)}</div>
        </div>
      </div>

      {/* 4-month history */}
      <div>
        <h4 className="text-xs text-gray-500 mb-2">Spend history (last 4 months)</h4>
        <div className="flex items-end gap-2 h-20">
          {usage.monthly_history?.map((h) => (
            <div key={h.month} className="flex-1 flex flex-col items-center gap-1">
              <div className="w-full flex items-end justify-center h-14">
                <div
                  className="w-full max-w-[40px] bg-accent-blue/80 rounded-t"
                  style={{ height: `${(h.spent_usd / maxHistory) * 100}%`, minHeight: h.spent_usd > 0 ? '4px' : '2px' }}
                  title={`$${h.spent_usd}`}
                />
              </div>
              <span className="text-[10px] text-gray-600">{h.month.slice(5)}</span>
              <span className="text-[10px] text-gray-400">${h.spent_usd?.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
