import { useState, useEffect } from 'react';
import { fetchAPI, putAPI, postAPI, formatPrice } from '../api';

const STATUS_COLORS = {
  idle: 'bg-gray-500',
  running: 'bg-accent-green animate-pulse',
  analysing: 'bg-accent-yellow animate-pulse',
};

export default function AgentPanel() {
  const [status, setStatus] = useState(null);
  const [decision, setDecision] = useState(null);
  const [account, setAccount] = useState(null);
  const [settings, setSettings] = useState({ loop_interval: 300, max_risk_percent: 2, watch_coins: '' });
  const [showConfirm, setShowConfirm] = useState(false);
  const [running, setRunning] = useState(false);

  const load = async () => {
    try {
      const [s, d, a] = await Promise.all([
        fetchAPI('/agent/status'),
        fetchAPI('/agent/last-decision'),
        fetchAPI('/agent/paper-account'),
      ]);
      setStatus(s);
      setDecision(d);
      setAccount(a);
      setSettings({
        loop_interval: s.loop_interval,
        max_risk_percent: s.max_risk_percent,
        watch_coins: s.watch_coins,
      });
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

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

  const runCycleNow = async () => {
    setRunning(true);
    try {
      await postAPI('/agent/run-cycle');
      await load();
    } catch (e) {
      console.error(e);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Paper trading banner */}
      {!status?.live_mode && (
        <div className="card border border-accent-green/30 bg-green-900/10">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-accent-green">Mock Trading Active (Paper Mode)</p>
              <p className="text-xs text-gray-400 mt-0.5">
                Virtual $10,000 · Binance keys read your real balances but NO real trades execute
              </p>
            </div>
            <button
              onClick={runCycleNow}
              disabled={running}
              className="px-4 py-2 bg-accent-green hover:bg-green-600 text-white text-xs font-medium rounded-lg disabled:opacity-50 shrink-0"
            >
              {running ? 'Running...' : 'Run Agent Now'}
            </button>
          </div>
        </div>
      )}
      {/* Status */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-300">Agent Status</h3>
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${STATUS_COLORS[status?.status] || 'bg-gray-500'}`} />
            <span className="text-sm capitalize">{status?.status || 'unknown'}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-500">Mode</span>
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={toggleLiveMode}
                className={`px-3 py-1 rounded text-xs font-medium ${
                  status?.live_mode ? 'bg-accent-red text-white' : 'bg-accent-green/20 text-accent-green'
                }`}
              >
                {status?.live_mode ? 'LIVE' : 'PAPER'}
              </button>
            </div>
          </div>
          <div>
            <span className="text-gray-500">Last Run</span>
            <p className="text-white mt-1">
              {status?.last_run_at ? new Date(status.last_run_at).toLocaleString() : 'Never'}
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

      {/* Last Decision */}
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

      {/* Settings */}
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

      {/* Live Mode Confirmation */}
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
