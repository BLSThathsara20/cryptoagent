import { useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { fetchAPI, formatPrice } from '../api';
import LiveTradingToggle from '../components/LiveTradingToggle';
import { usePolling, useNow, formatCountdown, secondsUntil, isAgentBusy } from '../hooks/useLive';
import { useLivePulse } from '../LivePulseContext';

const LEARNING_STATUS = {
  active: { color: 'text-accent-green', bg: 'bg-accent-green/20', label: 'Learning Today' },
  stable: { color: 'text-accent-blue', bg: 'bg-accent-blue/20', label: 'Stable' },
  idle: { color: 'text-gray-400', bg: 'bg-dark-700', label: 'Idle' },
};

function StatCard({ label, value, sub, color }) {
  return (
    <div className="card text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color || 'text-white'}`}>{value}</div>
      {sub && <div className="text-[10px] text-gray-600 mt-1">{sub}</div>}
    </div>
  );
}

function ChartTooltip({ active, payload, label, prefix = '$' }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {prefix}{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  );
}

export default function Insights() {
  const [data, setData] = useState(null);
  const [expandedDate, setExpandedDate] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const now = useNow(1000);
  const { pulse, nextIn: pulseNextIn } = useLivePulse();

  usePolling(async () => {
    const d = await fetchAPI('/analytics/overview');
    setData(d);
    setFetchedAt(Date.now());
  }, 8000);

  if (!data) {
    return <div className="p-8 text-gray-500">Loading insights...</div>;
  }

  const { trading, daily_pnl, wealth, predictions, learnings, next_action: na, regime } = data;
  const ls = LEARNING_STATUS[learnings?.status] || LEARNING_STATUS.idle;
  const todayPnl = daily_pnl?.today?.pnl ?? 0;
  const pnlSeries = (daily_pnl?.series || []).map((d) => ({
    ...d,
    label: d.date.slice(5),
  }));

  // Live countdown — prefer pulse, else next_run_at from overview, else static seconds
  const stageBusy = isAgentBusy(pulse?.agent?.stage);
  let liveNext = pulseNextIn;
  if (liveNext == null && na?.next_run_at) {
    liveNext = secondsUntil(na.next_run_at, now);
  }
  if (liveNext == null && na?.seconds_until_next_cycle != null) {
    // Decay the API snapshot second-by-second until the next poll
    const elapsed = Math.floor((now - fetchedAt) / 1000);
    liveNext = Math.max(0, na.seconds_until_next_cycle - elapsed);
  }
  const nextDisplay = stageBusy ? 'running…' : formatCountdown(liveNext);
  const wealthSeries = (wealth?.series || []).map((w, i) => ({
    label: w.timestamp ? new Date(w.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : `#${i}`,
    value: w.value,
  }));

  return (
    <div className="p-4 max-w-[1400px] mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Insights & Performance</h1>
          <p className="text-sm text-gray-500 mt-1">
            P&L, wealth growth, agent learning, and projections — all in one place
          </p>
        </div>
        <LiveTradingToggle />
      </div>

      {regime?.regime && (
        <div className={`card border ${
          regime.allow_new_trades === false
            ? 'border-accent-red/40 bg-red-900/10'
            : regime.regime_shifted
              ? 'border-accent-yellow/40 bg-yellow-900/10'
              : 'border-dark-600'
        }`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-300">Market Regime</h3>
              <p className="text-lg font-bold mt-1">{regime.regime_label || regime.regime}</p>
              {regime.previous_regime && regime.regime_shifted && (
                <p className="text-xs text-accent-yellow mt-1">
                  Shifted from {regime.previous_regime.replace('_', ' ')}
                </p>
              )}
            </div>
            <div className="flex gap-4 text-center text-xs">
              <div>
                <div className="text-gray-500">Size</div>
                <div className="font-bold">×{(regime.size_multiplier ?? 1).toFixed(2)}</div>
              </div>
              <div>
                <div className="text-gray-500">BTC 24h</div>
                <div className={regime.btc_change_24h >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                  {regime.btc_change_24h >= 0 ? '+' : ''}{regime.btc_change_24h}%
                </div>
              </div>
              <div>
                <div className="text-gray-500">Learning Δ</div>
                <div>{regime.learning_rate ?? regime.learning_drift?.learning_rate_today ?? 0}%</div>
              </div>
            </div>
          </div>
          {(regime.policy_notes?.length > 0) && (
            <ul className="text-xs text-gray-400 mt-3 space-y-1">
              {regime.policy_notes.map((n, i) => (
                <li key={i}>• {n}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Agent next action */}
      {na && (
        <div className="card border border-accent-blue/30 bg-blue-900/10">
          <div className="flex flex-col lg:flex-row lg:items-start gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2.5 h-2.5 rounded-full ${
                  na.agent_status === 'running' || na.agent_status === 'analysing'
                    ? 'bg-accent-yellow animate-pulse' : 'bg-accent-green'
                }`} />
                <h3 className="text-sm font-semibold text-gray-300">Agent Next Action</h3>
                <span className="text-xs text-gray-500 capitalize">({na.agent_status})</span>
              </div>
              <div className="text-2xl font-bold mb-2">
                <span className={
                  na.next_action === 'buy' ? 'text-accent-green' :
                  na.next_action === 'sell' ? 'text-accent-red' :
                  na.next_action === 'monitor' ? 'text-accent-yellow' : 'text-accent-blue'
                }>
                  {na.next_action_label}
                </span>
                {na.confidence > 0 && (
                  <span className="text-sm font-normal text-gray-500 ml-2">
                    {na.confidence}% confidence
                  </span>
                )}
              </div>
              <ul className="text-xs text-gray-400 space-y-1 mb-3">
                {(na.reasoning || []).map((r, i) => (
                  <li key={i}>• {r}</li>
                ))}
              </ul>
              <p className="text-sm text-gray-300 bg-dark-700/40 rounded-lg p-3">
                <span className="text-gray-500 text-xs block mb-1">Prediction analysis</span>
                {na.prediction_analysis}
              </p>
            </div>
            <div className="lg:w-72 shrink-0 space-y-3">
              {(na.next_run_at != null || na.seconds_until_next_cycle != null || pulseNextIn != null) && (
                <div className="bg-dark-700/50 rounded-lg p-3 text-center">
                  <div className="text-xs text-gray-500">Next cycle in</div>
                  <div className="text-lg font-bold tabular-nums text-white">
                    {nextDisplay}
                  </div>
                </div>
              )}
              {na.top_signals?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-500 mb-2">Top signal scan</div>
                  <div className="space-y-1">
                    {na.top_signals.slice(0, 4).map((s) => (
                      <div key={s.symbol} className="flex justify-between text-xs bg-dark-700/30 rounded px-2 py-1">
                        <span>{s.symbol}</span>
                        <span className={s.signal_score >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                          {s.signal_score > 0 ? '+' : ''}{s.signal_score} → {s.suggested}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          label="Today P&L"
          value={formatPrice(todayPnl)}
          color={todayPnl >= 0 ? 'text-accent-green' : 'text-accent-red'}
          sub={`${daily_pnl?.today?.trades ?? 0} trades · ${daily_pnl?.today?.wins ?? 0}W/${daily_pnl?.today?.losses ?? 0}L`}
        />
        <StatCard
          label="Total P&L"
          value={formatPrice(trading?.total_pnl ?? 0)}
          color={(trading?.total_pnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}
        />
        <StatCard label="Balance" value={formatPrice(trading?.paper_balance ?? 0)} />
        <StatCard
          label="Wealth Growth"
          value={`${wealth?.growth_percent >= 0 ? '+' : ''}${wealth?.growth_percent ?? 0}%`}
          color={(wealth?.growth_percent ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}
          sub={`from ${formatPrice(wealth?.initial_balance ?? 0)}`}
        />
        <StatCard label="Win Rate" value={`${trading?.win_rate ?? 0}%`} sub={`${trading?.closed_trades ?? 0} closed`} />
        <StatCard label="Pending" value={trading?.pending_trades ?? 0} sub="open positions" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-1">Daily Profit & Loss</h3>
          <p className="text-xs text-gray-500 mb-4">Last 30 days — green = profit, red = loss</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={pnlSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
              <ReferenceLine y={0} stroke="#6b7280" />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="pnl" name="P&L" radius={[2, 2, 0, 0]}>
                {pnlSeries.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-1">Wealth Growth</h3>
          <p className="text-xs text-gray-500 mb-4">Portfolio value over time</p>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={wealthSeries}>
              <defs>
                <linearGradient id="wealthGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 10 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} domain={['auto', 'auto']} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="value" name="Balance" stroke="#3b82f6" fill="url(#wealthGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cumulative P&L + Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-1">Cumulative P&L Trend</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={pnlSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
              <ReferenceLine y={0} stroke="#6b7280" />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="cumulative_pnl" name="Cumulative" stroke="#22c55e" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-1">Wealth Projections</h3>
          <p className="text-xs text-gray-500 mb-3">
            Based on avg daily P&L ${predictions?.avg_daily_pnl?.toFixed(2)} · Target ${formatPrice(predictions?.target_daily_profit)} / day
          </p>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {(predictions?.projections || []).map((p) => (
              <div key={p.horizon} className="bg-dark-700/50 rounded-lg p-3 text-center">
                <div className="text-xs text-gray-500">{p.horizon}</div>
                <div className={`text-lg font-bold ${p.projected_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                  {p.projected_pnl >= 0 ? '+' : ''}{formatPrice(p.projected_pnl)}
                </div>
                <div className="text-[10px] text-gray-500">→ {formatPrice(p.projected_balance)}</div>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-600 italic">{predictions?.disclaimer}</p>
        </div>
      </div>

      {/* Agent Learning */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-300">Agent Learning</h3>
            <p className="text-xs text-gray-500 mt-0.5">Lessons from closed trades — fed back into AI decisions</p>
          </div>
          <div className={`px-3 py-1 rounded-full text-xs font-medium ${ls.bg} ${ls.color}`}>
            {learnings?.status_label || ls.label}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <StatCard
            label="Today P&L"
            value={`${todayPnl >= 0 ? '+' : ''}${formatPrice(todayPnl)}`}
            sub={`${daily_pnl?.today?.wins ?? 0}W / ${daily_pnl?.today?.losses ?? 0}L`}
            color={todayPnl >= 0 ? 'text-accent-green' : 'text-accent-red'}
          />
          <StatCard label="Total Lessons" value={learnings?.total_lessons ?? 0} />
          <StatCard label="From Wins" value={learnings?.win_lessons ?? 0} color="text-accent-green" />
          <StatCard label="From Losses" value={learnings?.loss_lessons ?? 0} color="text-accent-red" />
        </div>

        {/* Today's learnings */}
        <div className="mb-4">
          <h4 className="text-xs font-medium text-gray-400 mb-2">
            Today ({learnings?.today?.date}) — {learnings?.today?.count ?? 0} lesson(s)
            {learnings?.today?.pnl != null && (
              <span className={`ml-2 ${learnings.today.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                · P&L {formatPrice(learnings.today.pnl)}
              </span>
            )}
          </h4>
          {(learnings?.today?.lessons?.length ?? 0) === 0 ? (
            <p className="text-xs text-gray-600 bg-dark-700/30 rounded-lg p-3">
              No new lessons today. The agent will learn when trades close (win or loss).
            </p>
          ) : (
            <div className="space-y-2">
              {learnings.today.lessons.map((l) => (
                <div key={l.id} className="bg-dark-700/40 rounded-lg p-3 border-l-2 border-accent-blue">
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <span className="font-medium">{l.coin}</span>
                    <span className={l.outcome === 'win' ? 'text-accent-green' : 'text-accent-red'}>{l.outcome}</span>
                    {l.pnl != null && <span className="text-gray-500">{formatPrice(l.pnl)}</span>}
                  </div>
                  <p className="text-sm text-gray-300">{l.lesson}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Past learnings by date */}
        <h4 className="text-xs font-medium text-gray-400 mb-2">Learning history by date</h4>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {(learnings?.daily_digest || []).map((day) => (
            <div key={day.date} className="border border-dark-600 rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedDate(expandedDate === day.date ? null : day.date)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-dark-700/50"
              >
                <span className="font-medium">{day.date}</span>
                <span className="text-gray-500">
                  {day.lessons_count} lessons · {day.wins}W/{day.losses}L
                </span>
              </button>
              {expandedDate === day.date && (
                <div className="px-3 pb-2 space-y-2 border-t border-dark-600">
                  {day.lessons.map((l) => (
                    <div key={l.id} className="text-xs pt-2">
                      <span className={`${l.outcome === 'win' ? 'text-accent-green' : 'text-accent-red'} font-medium`}>
                        {l.coin} {l.outcome}
                      </span>
                      <span className="text-gray-500 ml-2">{l.lesson}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Non-technical summary */}
      <div className="card bg-dark-800/80 border-accent-blue/20">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Plain English Summary</h3>
        <p className="text-sm text-gray-400 leading-relaxed">
          You are in <strong className="text-white">{trading?.trading_mode_label}</strong>.
          {todayPnl >= 0
            ? ` Today you are up ${formatPrice(todayPnl)}.`
            : todayPnl < 0
              ? ` Today you are down ${formatPrice(Math.abs(todayPnl))}.`
              : ' No closed trades today yet.'}
          {' '}Your balance is {formatPrice(trading?.paper_balance)} ({wealth?.growth_percent >= 0 ? 'up' : 'down'} {Math.abs(wealth?.growth_percent ?? 0)}% from start).
          The agent has stored {learnings?.total_lessons ?? 0} lessons from past trades
          {learnings?.today?.count ? ` and learned ${learnings.today.count} new thing(s) today` : ''}.
          {trading?.live_mode
            ? ' Live trading is ON — real money is at risk.'
            : ' Mock mode is safe — switch to live only when performance looks good.'}
        </p>
      </div>
    </div>
  );
}
