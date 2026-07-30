import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { formatPrice, postAPI } from '../api';
import { useLivePulse } from '../LivePulseContext';
import { formatCountdown, isAgentBusy } from '../hooks/useLive';

function formatRows(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n ?? 0);
}

function formatAgo(iso, nowMs) {
  if (!iso) return '';
  const sec = Math.max(0, Math.floor((nowMs - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

/**
 * Always-on pulse + daily target / learning — updates live via LivePulseProvider.
 */
export default function SystemStatusBar() {
  const { pulse, now, nextIn } = useLivePulse();
  const [browserOnline, setBrowserOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    const on = () => setBrowserOnline(true);
    const off = () => setBrowserOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  const online = browserOnline && (pulse?.online ?? false);
  const agent = pulse?.agent;
  const data = pulse?.data;
  const binance = pulse?.binance;
  const prog = pulse?.progress;

  const netLabel = !browserOnline ? 'OFFLINE' : online ? 'LIVE' : 'OFFLINE';
  const netDot = online && browserOnline ? 'bg-accent-green animate-pulse' : 'bg-accent-red';

  const stageLabel = !browserOnline
    ? 'Preparing to decide (offline)'
    : agent?.label || 'Checking…';

  const stageBusy = isAgentBusy(agent?.stage);

  let bnLabel = 'Binance…';
  if (binance?.account === 'ok') bnLabel = 'Binance account OK';
  else if (binance?.market === 'ok' && binance?.account === 'error') bnLabel = 'Market OK · account IP/key';
  else if (binance?.market === 'ok') bnLabel = 'Binance market OK';
  else if (binance) bnLabel = 'Binance down';

  const progressPct = Math.min(100, Math.max(0, prog?.progress_percent || 0));
  const targetHit = prog?.target_status === 'hit';
  const pnl = prog?.today_pnl ?? 0;
  const barColor = targetHit ? 'bg-accent-green' : pnl < 0 ? 'bg-accent-red' : 'bg-accent-blue';

  const nextLabel = !agent?.loop_running
    ? 'Agent stopped'
    : stageBusy
      ? 'Cycle running…'
      : `Next check ${formatCountdown(nextIn)}`;

  const showRestart = !agent?.loop_running || !online;

  const restartAgent = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setRestarting(true);
    try {
      await postAPI('/agent/restart', {}, 15000);
    } catch {
      /* ignore — user can retry */
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div className={`bg-dark-800/90 border-b border-dark-600 ${stageBusy ? 'status-bar-deciding' : ''}`}>
      {prog && (
        <div className="px-4 pt-1.5 pb-1 flex items-center gap-3 flex-wrap text-[11px]">
          <Link to="/agent" className="flex items-center gap-2 min-w-[180px] flex-1 max-w-md group">
            <span className="text-gray-400 shrink-0">Daily target</span>
            <div className="flex-1 h-1.5 bg-dark-700 rounded-full overflow-hidden">
              <div className={`h-full transition-all duration-500 ${barColor}`} style={{ width: `${progressPct}%` }} />
            </div>
            <span className={`font-medium tabular-nums ${pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
              {formatPrice(pnl)}
            </span>
            <span className="text-gray-500 tabular-nums">/ {formatPrice(prog.target_usd)}</span>
            {targetHit && <span className="text-accent-green font-semibold">HIT</span>}
          </Link>

          <Link
            to="/agent"
            className={`font-medium tabular-nums ${stageBusy ? 'text-accent-blue' : 'text-gray-200 hover:text-white'}`}
            title={agent?.next_run_at ? `Next cycle ~ ${new Date(agent.next_run_at).toLocaleTimeString()}` : 'Next agent trading cycle'}
          >
            {nextLabel}
          </Link>

          {showRestart && (
            <button
              type="button"
              onClick={restartAgent}
              disabled={restarting}
              className="px-2 py-0.5 rounded bg-accent-yellow/90 text-dark-900 font-medium hover:bg-yellow-400 disabled:opacity-50"
              title="Restart agent loop now"
            >
              {restarting ? 'Restarting…' : 'Restart agent'}
            </button>
          )}

          <Link to="/learning" className="text-gray-400 hover:text-white transition-colors">
            Today{' '}
            <span className={`font-medium tabular-nums ${pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
              {formatPrice(pnl)}
            </span>
            <span className="text-gray-600 mx-1">·</span>
            Acc <span className="text-gray-200 font-medium">{prog.accuracy_percent ?? 0}%</span>
            <span className="text-gray-600 mx-1">·</span>
            Learn <span className="text-gray-200">{prog.memories ?? 0}</span>
          </Link>

          <span className="text-gray-500 hidden sm:inline" title={`Max hold ${prog.max_hold_minutes}m`}>
            Open <span className="text-gray-300">{prog.open_trades ?? 0}/{prog.max_open ?? 2}</span>
            <span className="text-gray-600 mx-1">·</span>
            ≤{prog.max_hold_minutes}m
          </span>

          <span
            className="text-gray-500 hidden md:inline"
            title={`LLM mode: ${prog.llm_mode} · last skip: ${prog.llm_skip || '—'}`}
          >
            AI ${Number(prog.llm_spent_usd || 0).toFixed(2)}
            <span className="text-gray-600">/{prog.llm_budget_usd}</span>
            <span className="text-gray-600 ml-1">({prog.llm_mode})</span>
          </span>
        </div>
      )}

      <div className="px-4 py-1.5 flex items-center justify-between gap-3 text-xs text-gray-500">
        <div className="flex items-center gap-3 sm:gap-4 flex-wrap min-w-0">
          <span className="flex items-center gap-1.5 font-medium text-gray-200">
            <span className={`w-1.5 h-1.5 rounded-full ${netDot}`} />
            {netLabel}
            {pulse?.using_cached_data && browserOnline && (
              <span className="text-gray-500 font-normal">· cached</span>
            )}
          </span>

          <span className={`flex items-center gap-1.5 truncate max-w-[220px] sm:max-w-none ${stageBusy ? 'text-blue-200 font-medium' : 'text-gray-300'}`}>
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                !agent?.loop_running
                  ? 'bg-accent-red'
                  : stageBusy
                    ? 'bg-accent-blue animate-pulse'
                    : 'bg-accent-green animate-pulse'
              }`}
            />
            {stageLabel}
            {agent?.last_run_at && (
              <span className="text-gray-500 hidden sm:inline">· {formatAgo(agent.last_run_at, now)}</span>
            )}
          </span>

          {data && (
            <span className="hidden lg:inline text-gray-400" title="Data saved in PostgreSQL">
              Saved{' '}
              <span className="text-gray-300">
                {data.size_mb} MB · {formatRows(data.rows)} rows
              </span>
            </span>
          )}

          <span
            className="hidden xl:inline text-gray-400 truncate max-w-[240px]"
            title={binance?.hint || binance?.message || ''}
          >
            {bnLabel}
          </span>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-gray-500 tabular-nums" title="Live React clock — updates every second">
            {new Date(now).toLocaleTimeString()}
          </span>
          <span className="text-gray-500 hidden sm:inline">
            {agent?.live_mode ? 'LIVE trade' : 'PAPER'}
          </span>
          <Link to="/learning" className="text-accent-blue hover:underline">
            Learning
          </Link>
          <Link to="/settings" className="text-gray-400 hover:text-white">
            Settings
          </Link>
        </div>
      </div>
    </div>
  );
}
