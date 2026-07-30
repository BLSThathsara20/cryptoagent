import { useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchAPI, putAPI, postAPI, formatPrice } from '../api';
import { useLivePulse } from '../LivePulseContext';
import { usePolling, formatCountdown, isAgentBusy } from '../hooks/useLive';

const STAGE_LABELS = {
  preparing: 'Preparing to decide',
  analysing: 'Reading market',
  deciding: 'Making decision',
  executing: 'Placing trade',
  running: 'Placing trade',
  monitoring: 'Watching market',
  idle: 'Watching market',
  stopped: 'Agent stopped',
};

function formatAgo(iso, nowMs = Date.now()) {
  if (!iso) return 'never';
  const sec = Math.max(0, Math.floor((nowMs - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

export default function AgentPanel() {
  const { pulse, now, nextIn } = useLivePulse();
  const [status, setStatus] = useState(null);
  const [decision, setDecision] = useState(null);
  const [account, setAccount] = useState(null);
  const [validation, setValidation] = useState(null);
  const [settings, setSettings] = useState({ loop_interval: 300, max_risk_percent: 2, watch_coins: '' });
  const [showConfirm, setShowConfirm] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [restartMsg, setRestartMsg] = useState('');

  const load = async () => {
    const [s, d, a, v] = await Promise.all([
      fetchAPI('/agent/status'),
      fetchAPI('/agent/last-decision'),
      fetchAPI('/agent/paper-account'),
      fetchAPI('/issues'),
    ]);
    setStatus(s);
    setDecision(d);
    setAccount(a);
    setValidation(v);
    if (s) {
      setSettings({
        loop_interval: s.loop_interval,
        max_risk_percent: s.max_risk_percent,
        watch_coins: s.watch_coins,
      });
    }
  };

  usePolling(load, 5000);

  const restartAgent = async () => {
    setRestarting(true);
    setRestartMsg('');
    try {
      const r = await postAPI('/agent/restart', {}, 15000);
      setRestartMsg(r.message || 'Agent loop restarted');
      await load();
    } catch (e) {
      setRestartMsg(e?.message || 'Restart failed — try again when backend is up');
    } finally {
      setRestarting(false);
    }
  };

  const toggleLiveMode = async () => {
    if (!status?.live_mode) {
      setShowConfirm(true);
      return;
    }
    await putAPI('/agent/settings', { live_mode: false });
    load();
  };

  const confirmLiveMode = async () => {
    await putAPI('/agent/settings', { live_mode: true });
    setShowConfirm(false);
    load();
  };

  const saveSettings = async () => {
    await putAPI('/agent/settings', settings);
    load();
  };

  const loopOn = Boolean(pulse?.agent?.loop_running ?? status?.loop_running);
  const online = pulse?.online ?? true;
  const stage = pulse?.agent?.stage || status?.status || 'unknown';
  const stageLabel = pulse?.agent?.label || STAGE_LABELS[stage] || stage;
  const busy = isAgentBusy(stage);
  const lastRun = pulse?.agent?.last_run_at || status?.last_run_at;
  const liveMode = pulse?.agent?.live_mode ?? status?.live_mode;
  const intervalSec = pulse?.agent?.interval_sec || status?.loop_interval || 300;
  const needsRestart = !loopOn || !online;

  const health = validation?.overall_status;
  const healthScore = validation?.health_score;
  const openIssues = validation?.open_count ?? 0;
  const lastValidation = validation?.last_validation_at;

  return (
    <div className="space-y-4">
      <div className={`card border ${loopOn ? 'border-accent-green/40 bg-green-900/10' : 'border-accent-red/40 bg-red-900/10'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${
                  !loopOn
                    ? 'bg-accent-red'
                    : busy
                      ? 'bg-accent-blue animate-pulse'
                      : 'bg-accent-green animate-pulse'
                }`}
              />
              <p className="text-sm font-medium text-white truncate">
                {loopOn ? 'Agent running' : 'Agent stopped'}
                {!online && <span className="text-accent-yellow ml-2 text-xs">· offline</span>}
              </p>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {stageLabel}
              {lastRun ? ` · last cycle ${formatAgo(lastRun, now)}` : ''}
              {` · every ${intervalSec}s`}
            </p>
            <p className={`text-sm mt-2 font-medium tabular-nums ${busy ? 'text-accent-blue' : 'text-white'}`}>
              {busy ? 'Trading cycle in progress…' : `Next trading check: ${formatCountdown(nextIn)}`}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Auto-restarts when the network comes back. Use Restart if it still looks stuck.
            </p>
            {restartMsg && (
              <p className="text-xs text-accent-green mt-1">{restartMsg}</p>
            )}
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <span className={`text-xs px-2 py-1 rounded ${liveMode ? 'bg-accent-red/20 text-accent-red' : 'bg-accent-green/20 text-accent-green'}`}>
              {liveMode ? 'LIVE trades' : 'PAPER trades'}
            </span>
            <button
              type="button"
              onClick={restartAgent}
              disabled={restarting}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                needsRestart
                  ? 'bg-accent-yellow text-dark-900 hover:bg-yellow-400'
                  : 'bg-dark-700 text-gray-200 hover:bg-dark-600'
              }`}
              title="Force-restart the agent trading loop"
            >
              {restarting ? 'Restarting…' : 'Restart agent'}
            </button>
          </div>
        </div>
      </div>

      {/* Live validation snapshot (real data) */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">Validation</h3>
          <Link to="/issues" className="text-xs text-accent-blue hover:underline">
            Issues →
          </Link>
        </div>
        {validation ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <span className="text-gray-500 text-xs">Health</span>
              <p className="font-medium capitalize">
                {typeof healthScore === 'number' ? Math.round(healthScore) : '—'}
                {health ? ` · ${health}` : ''}
              </p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Open issues</span>
              <p className={openIssues > 0 ? 'text-accent-yellow font-medium' : 'text-accent-green font-medium'}>
                {openIssues}
              </p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Last check</span>
              <p className="text-white text-xs mt-1">{lastValidation ? formatAgo(lastValidation) : 'pending'}</p>
            </div>
          </div>
        ) : (
          <p className="text-xs text-gray-500">Loading validation…</p>
        )}
        <p className="text-[11px] text-gray-600 mt-2">Runs automatically every few minutes.</p>
      </div>

      {/* Status */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-300">Agent Status</h3>
          <div className="flex items-center gap-2">
            <div
              className={`w-2.5 h-2.5 rounded-full ${
                !loopOn
                  ? 'bg-accent-red'
                  : busy
                    ? 'bg-accent-blue animate-pulse'
                    : 'bg-accent-green animate-pulse'
              }`}
            />
            <span className="text-sm">{stageLabel}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-500">Mode</span>
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={toggleLiveMode}
                className={`px-3 py-1 rounded text-xs font-medium ${
                  liveMode ? 'bg-accent-red text-white' : 'bg-accent-green/20 text-accent-green'
                }`}
              >
                {liveMode ? 'LIVE' : 'PAPER'}
              </button>
            </div>
          </div>
          <div>
            <span className="text-gray-500">Last cycle</span>
            <p className="text-white mt-1 text-xs">
              {lastRun ? new Date(lastRun).toLocaleString() : 'Waiting for first cycle'}
            </p>
          </div>
        </div>

        {account && (
          <div className="grid grid-cols-4 gap-3 mt-4 pt-4 border-t border-dark-600 text-sm">
            <div>
              <span className="text-gray-500 text-xs">Balance</span>
              <p className="font-medium">{formatPrice(account.balance)}</p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">P&L</span>
              <p className={account.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                {formatPrice(account.total_pnl)}
              </p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Win Rate</span>
              <p>{account.win_rate}%</p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Drawdown</span>
              <p className="text-accent-red">{account.max_drawdown?.toFixed(1)}%</p>
            </div>
          </div>
        )}
      </div>

      {decision && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Last Decision</h3>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-lg font-bold">{decision.coin}</span>
            <span className={decision.direction === 'long' ? 'badge-green' : 'badge-red'}>
              {decision.direction.toUpperCase()}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${
              decision.status === 'win' ? 'bg-green-900/30 text-accent-green' :
              decision.status === 'loss' ? 'bg-red-900/30 text-accent-red' :
              'bg-yellow-900/30 text-accent-yellow'
            }`}>
              {decision.status}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm mb-3">
            <div><span className="text-gray-500">Entry:</span> {formatPrice(decision.entry_price)}</div>
            <div><span className="text-gray-500">TP:</span> <span className="text-accent-green">{formatPrice(decision.take_profit)}</span></div>
            <div><span className="text-gray-500">SL:</span> <span className="text-accent-red">{formatPrice(decision.stop_loss)}</span></div>
            <div><span className="text-gray-500">Confidence:</span> {decision.confidence}/100</div>
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{decision.reasoning}</p>
        </div>
      )}

      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Agent Settings</h3>
        <div className="space-y-3 text-sm">
          <div>
            <label className="text-gray-500 text-xs">Loop Interval (seconds)</label>
            <input
              type="number"
              value={settings.loop_interval}
              onChange={(e) => setSettings({ ...settings, loop_interval: parseInt(e.target.value) })}
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded px-3 py-1.5 text-white"
            />
          </div>
          <div>
            <label className="text-gray-500 text-xs">Max Risk %</label>
            <input
              type="number"
              step="0.1"
              value={settings.max_risk_percent}
              onChange={(e) => setSettings({ ...settings, max_risk_percent: parseFloat(e.target.value) })}
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded px-3 py-1.5 text-white"
            />
          </div>
          <div>
            <label className="text-gray-500 text-xs">Watch Coins (comma-separated)</label>
            <input
              type="text"
              value={settings.watch_coins}
              onChange={(e) => setSettings({ ...settings, watch_coins: e.target.value })}
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded px-3 py-1.5 text-white"
            />
          </div>
          <button
            onClick={saveSettings}
            className="w-full bg-accent-blue hover:bg-blue-600 text-white py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Save Settings
          </button>
        </div>
      </div>

      {showConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-6 max-w-md mx-4">
            <h3 className="text-lg font-bold text-accent-red mb-2">Enable Live Trading?</h3>
            <p className="text-sm text-gray-400 mb-4">
              This will execute real trades with your Binance account. Real money is at risk.
              Make sure your API keys are configured and you understand the risks.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 bg-dark-600 hover:bg-dark-700 py-2 rounded-lg text-sm"
              >
                Cancel
              </button>
              <button
                onClick={confirmLiveMode}
                className="flex-1 bg-accent-red hover:bg-red-600 py-2 rounded-lg text-sm font-medium"
              >
                Enable Live Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
