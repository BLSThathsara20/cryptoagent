import { useState, useEffect, useRef } from 'react';
import { fetchAPI, postAPI } from '../api';
import { usePolling } from '../hooks/useLive';

const LEVEL_STYLES = {
  info: 'border-l-accent-blue bg-blue-900/10',
  success: 'border-l-accent-green bg-green-900/10',
  warning: 'border-l-accent-yellow bg-yellow-900/10',
  error: 'border-l-accent-red bg-red-900/10',
};

const LEVEL_DOT = {
  info: 'bg-accent-blue',
  success: 'bg-accent-green',
  warning: 'bg-accent-yellow',
  error: 'bg-accent-red',
};

export default function AlertBell() {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef(null);

  const load = async () => {
    const data = await fetchAPI('/alerts?limit=30');
    setAlerts(data.alerts || []);
    setUnread(data.unread_count || 0);
  };

  usePolling(load, 5000);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  const markRead = async (id) => {
    await postAPI(`/alerts/${id}/read`);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    setUnread((n) => Math.max(0, n - 1));
  };

  const markAllRead = async () => {
    await postAPI('/alerts/read-all');
    setAlerts([]);
    setUnread(0);
  };

  const testBinance = async () => {
    const result = await postAPI('/alerts/test-binance');
    alert(result.message);
    load();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-dark-700 text-gray-300 hover:text-white border border-dark-600"
        title="System alerts"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        <span className="text-xs hidden sm:inline">Alerts</span>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-accent-red text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 max-h-[480px] bg-dark-800 border border-dark-600 rounded-xl shadow-2xl z-50 flex flex-col">
          <div className="flex items-center justify-between p-3 border-b border-dark-600">
            <span className="text-sm font-semibold">System Alerts</span>
            <div className="flex gap-2">
              <button onClick={testBinance} className="text-[10px] text-accent-blue hover:underline">
                Test Binance
              </button>
              {unread > 0 && (
                <button onClick={markAllRead} className="text-[10px] text-gray-400 hover:text-white">
                  Clear all
                </button>
              )}
            </div>
          </div>
          <div className="overflow-y-auto flex-1">
            {alerts.length === 0 ? (
              <p className="text-gray-500 text-xs text-center py-8">No alerts yet</p>
            ) : (
              alerts.map((a) => (
                <div
                  key={a.id}
                  onClick={() => markRead(a.id)}
                  className={`p-3 border-b border-dark-700/50 border-l-4 cursor-pointer hover:bg-dark-700/30 ${LEVEL_STYLES[a.level] || LEVEL_STYLES.info}`}
                >
                  <div className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${LEVEL_DOT[a.level]}`} />
                    <div className="min-w-0">
                      <div className="flex justify-between gap-2">
                        <span className="text-xs font-medium truncate">{a.title}</span>
                        <span className="text-[10px] text-gray-600 shrink-0">{a.category}</span>
                      </div>
                      <p className="text-[11px] text-gray-400 mt-0.5 leading-relaxed">{a.message}</p>
                      <p className="text-[10px] text-gray-600 mt-1">
                        {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
