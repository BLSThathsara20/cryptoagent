import { useEffect } from 'react';
import { formatPrice } from '../api';

function formatHold(sec) {
  if (sec == null) return '—';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

function closeLabel(reason) {
  const map = {
    take_profit: 'Take profit hit',
    stop_loss: 'Stop loss hit',
    time_exit: 'Time exit (max hold)',
    trim_excess_open: 'Closed to trim excess open trades',
    take_profit_or_time: 'Closed (TP or time)',
    stop_loss_or_time: 'Closed (SL or time)',
  };
  if (!reason) return 'Still open — waiting for TP, SL, or time exit';
  return map[reason] || reason;
}

function SignalCard({ signal }) {
  if (!signal) return null;
  const macd = signal.macd || {};
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
      <div className="bg-dark-700/50 rounded-lg p-2">
        <div className="text-gray-500">RSI</div>
        <div className="font-medium">{signal.rsi != null ? Number(signal.rsi).toFixed(1) : '—'}</div>
      </div>
      <div className="bg-dark-700/50 rounded-lg p-2">
        <div className="text-gray-500">MACD</div>
        <div className="font-medium capitalize">{macd.trend || '—'}</div>
      </div>
      <div className="bg-dark-700/50 rounded-lg p-2">
        <div className="text-gray-500">Signal score</div>
        <div className="font-medium">{signal.signal_score ?? '—'}</div>
      </div>
      <div className="bg-dark-700/50 rounded-lg p-2">
        <div className="text-gray-500">Volume spike</div>
        <div className="font-medium">{String(signal.volume?.spike ?? '—')}</div>
      </div>
    </div>
  );
}

export default function TradeDetailModal({ trade, onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!trade) return null;

  const isOpen = trade.status === 'pending';
  const pnl = isOpen ? trade.unrealized_pnl : trade.outcome_pnl;
  const pnlLabel = isOpen ? 'Unrealized P&L' : 'Realized P&L';
  const meta = trade.meta || {};

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="bg-dark-800 border border-dark-600 rounded-xl max-w-xl w-full max-h-[90vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-dark-800 border-b border-dark-600 px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-lg font-bold">{trade.coin}</span>
            <span className={trade.direction === 'long' ? 'badge-green' : 'badge-red'}>
              {(trade.direction || '').toUpperCase()}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${
              trade.status === 'win' ? 'bg-green-900/30 text-accent-green' :
              trade.status === 'loss' ? 'bg-red-900/30 text-accent-red' :
              'bg-yellow-900/30 text-accent-yellow'
            }`}>
              {trade.status}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-white text-sm px-2"
          >
            Close
          </button>
        </div>

        <div className="p-4 space-y-4 text-sm">
          {/* Strategy */}
          <div className="rounded-lg border border-accent-blue/30 bg-blue-950/20 p-3">
            <div className="text-xs text-gray-500 mb-1">Strategy used</div>
            <div className="font-medium text-gray-100">{trade.strategy || '—'}</div>
            <div className="text-[11px] text-gray-500 mt-1">
              Source: {trade.decision_source || meta.decision_source || 'legacy / not tagged'}
              {meta.local_model_score != null && ` · Local score ${meta.local_model_score}`}
            </div>
            <div className="text-[11px] text-gray-500 mt-0.5">
              Style: {meta.style || 'scalp_short_hold'} · SL {meta.sl_percent_cfg ?? '—'}% · TP {meta.tp_percent_cfg ?? '—'}% · max hold {meta.max_hold_minutes ?? '—'}m
            </div>
          </div>

          {/* Timeline */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">Entry time</div>
              <div className="text-xs text-gray-200">
                {trade.created_at ? new Date(trade.created_at).toLocaleString() : '—'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Exit time · hold</div>
              <div className="text-xs text-gray-200">
                {trade.closed_at ? new Date(trade.closed_at).toLocaleString() : (isOpen ? 'Still open' : '—')}
                {' · '}{formatHold(trade.hold_seconds)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Entry price</div>
              <div className="font-medium">{formatPrice(trade.entry_price)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Mark / confidence</div>
              <div className="font-medium">
                {trade.mark_price != null ? formatPrice(trade.mark_price) : '—'}
                <span className="text-gray-500 text-xs"> · {trade.confidence}/100</span>
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Take profit</div>
              <div className="text-accent-green">
                {formatPrice(trade.take_profit)}
                {trade.tp_percent != null && <span className="text-gray-500 text-xs"> (+{trade.tp_percent}%)</span>}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Stop loss</div>
              <div className="text-accent-red">
                {formatPrice(trade.stop_loss)}
                {trade.sl_percent != null && <span className="text-gray-500 text-xs"> (−{trade.sl_percent}%)</span>}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">{pnlLabel}</div>
              <div className={(pnl || 0) >= 0 ? 'text-accent-green font-semibold' : 'text-accent-red font-semibold'}>
                {pnl != null ? formatPrice(pnl) : (isOpen ? 'Waiting for price…' : '—')}
              </div>
              {isOpen && (
                <div className="text-[10px] text-accent-yellow mt-0.5">No result yet — trade still open</div>
              )}
            </div>
            <div>
              <div className="text-xs text-gray-500">Risk / reward</div>
              <div className="font-medium">{trade.risk_reward != null ? `${trade.risk_reward}:1` : '—'}</div>
            </div>
          </div>

          {/* Closing strategy */}
          <div>
            <div className="text-xs text-gray-500 mb-1">Closing strategy</div>
            <div className="bg-dark-700/50 rounded-lg p-3 text-xs text-gray-300 space-y-1">
              <p>{closeLabel(trade.close_reason || trade.exit_plan?.close_reason)}</p>
              <p className="text-gray-500">
                Exit rules: hit TP {formatPrice(trade.take_profit)}, hit SL {formatPrice(trade.stop_loss)},
                or time-exit after {trade.exit_plan?.time_exit_minutes ?? meta.max_hold_minutes ?? '—'} minutes
                (whichever comes first). Excess opens may be trimmed to max concurrent limit.
              </p>
            </div>
          </div>

          {/* Why entry */}
          {(trade.entry_reason || trade.reasoning) && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Why this entry</div>
              <p className="text-xs text-gray-300 leading-relaxed bg-dark-700/50 rounded-lg p-3 whitespace-pre-wrap">
                {trade.entry_reason || trade.reasoning}
              </p>
            </div>
          )}

          {/* Coin signal */}
          {trade.coin_signal && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Technical snapshot ({trade.coin})</div>
              <SignalCard signal={trade.coin_signal} />
            </div>
          )}

          {/* Learning */}
          {trade.learning_snapshot?.special && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 p-3 text-xs text-amber-200">
              ★ Special lesson: {trade.learning_snapshot.special_reason}
            </div>
          )}

          {trade.lesson && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Saved lesson</div>
              <p className="text-xs text-gray-300 bg-dark-700/50 rounded-lg p-3">{trade.lesson}</p>
            </div>
          )}

          {trade.learning_snapshot?.features && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Training features</div>
              <pre className="text-[10px] text-gray-500 bg-dark-900/60 rounded-lg p-2 overflow-x-auto">
                {JSON.stringify(trade.learning_snapshot.features, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
