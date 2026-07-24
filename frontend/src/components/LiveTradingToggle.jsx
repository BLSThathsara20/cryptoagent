import { useState, useEffect } from 'react';
import { fetchAPI, putAPI } from '../api';

export default function LiveTradingToggle({ compact = false, onChange }) {
  const [liveMode, setLiveMode] = useState(false);
  const [canEnable, setCanEnable] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const [trading, system] = await Promise.all([
        fetchAPI('/analytics/trading'),
        fetchAPI('/system/status'),
      ]);
      setLiveMode(trading.live_mode);
      setCanEnable(trading.can_enable_live ?? system?.configuration?.binance_configured);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const setMode = async (live) => {
    setLoading(true);
    try {
      await putAPI('/agent/settings', { live_mode: live });
      setLiveMode(live);
      setShowConfirm(false);
      onChange?.(live);
      await load();
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = () => {
    if (liveMode) {
      setMode(false);
    } else {
      setShowConfirm(true);
    }
  };

  return (
    <>
      <div className={`flex items-center gap-3 ${compact ? '' : 'flex-wrap'}`}>
        <div className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
          liveMode
            ? 'bg-accent-red/20 text-accent-red border border-accent-red/40'
            : 'bg-accent-green/20 text-accent-green border border-accent-green/40'
        }`}>
          {liveMode ? 'LIVE TRADING' : 'MOCK TRADING (PAPER)'}
        </div>
        <button
          onClick={handleToggle}
          disabled={loading || (!liveMode && !canEnable)}
          title={!canEnable && !liveMode ? 'Configure Binance + OpenAI keys first' : ''}
          className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-40 ${
            liveMode
              ? 'bg-dark-700 hover:bg-dark-600 text-gray-200'
              : 'bg-accent-blue hover:bg-blue-600 text-white'
          }`}
        >
          {loading ? 'Updating...' : liveMode ? 'Switch to Mock' : 'Switch to Live'}
        </button>
        {!compact && (
          <p className="text-[11px] text-gray-500">
            {liveMode
              ? 'Real Binance orders — use with caution'
              : 'Virtual balance only — no real money at risk'}
          </p>
        )}
      </div>

      {showConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="card max-w-md w-full border border-accent-red/50">
            <h3 className="text-lg font-bold text-accent-red mb-2">Enable Live Trading?</h3>
            <p className="text-sm text-gray-400 mb-4">
              This will place real orders on Binance with your connected API keys.
              Make sure mock performance meets your expectations first.
            </p>
            <ul className="text-xs text-gray-500 space-y-1 mb-4">
              <li>• Real money will be used</li>
              <li>• Losses are permanent</li>
              <li>• You can switch back to mock anytime from this toggle</li>
            </ul>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowConfirm(false)} className="px-4 py-2 text-sm rounded-lg bg-dark-700 hover:bg-dark-600">
                Cancel
              </button>
              <button
                onClick={() => setMode(true)}
                disabled={loading}
                className="px-4 py-2 text-sm rounded-lg bg-accent-red hover:bg-red-600 text-white disabled:opacity-50"
              >
                Enable Live Trading
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
