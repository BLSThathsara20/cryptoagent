import { useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { fetchAPI, formatPrice } from '../api';
import { usePolling } from '../hooks/useLive';
import PaginationBar from '../components/PaginationBar';

const PAGE_SIZE = 25;

function StatCard({ label, value, sub, color }) {
  return (
    <div className="card text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color || 'text-white'}`}>{value}</div>
      {sub && <div className="text-[10px] text-gray-600 mt-1">{sub}</div>}
    </div>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : p.value}
        </p>
      ))}
    </div>
  );
}

function statusColor(status) {
  if (status === 'win') return 'text-accent-green';
  if (status === 'loss') return 'text-accent-red';
  if (status === 'pending') return 'text-accent-yellow';
  return 'text-gray-400';
}

function isSameDay(iso, dayKey) {
  if (!iso || !dayKey) return false;
  try {
    return new Date(iso).toISOString().slice(0, 10) === String(dayKey).slice(0, 10);
  } catch {
    return String(iso).slice(0, 10) === String(dayKey).slice(0, 10);
  }
}

export default function Learning() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('footprints');
  const [page, setPage] = useState(1);
  const [listItems, setListItems] = useState([]);
  const [listMeta, setListMeta] = useState({ page: 1, pages: 1, total: 0, page_size: PAGE_SIZE });

  usePolling(async () => {
    setData(await fetchAPI('/learning/overview?days=30&preview=12'));
  }, 8000);

  usePolling(async () => {
    let path = null;
    if (tab === 'footprints') path = `/learning/footprints?page=${page}&page_size=${PAGE_SIZE}`;
    else if (tab === 'specials') path = `/learning/footprints?page=${page}&page_size=${PAGE_SIZE}&special_only=true`;
    else if (tab === 'learnings') path = `/learning/lessons?page=${page}&page_size=${PAGE_SIZE}`;
    else if (tab === 'news') path = `/learning/news?page=${page}&page_size=${PAGE_SIZE}`;
    if (!path) return;
    const res = await fetchAPI(path);
    if (Array.isArray(res)) {
      setListItems(res);
      setListMeta({ page: 1, pages: 1, total: res.length, page_size: PAGE_SIZE });
    } else {
      setListItems(res.items || []);
      setListMeta({
        page: res.page || page,
        pages: res.pages || 1,
        total: res.total || 0,
        page_size: res.page_size || PAGE_SIZE,
      });
    }
  }, 8000, [tab, page]);

  const changeTab = (id) => {
    setTab(id);
    setPage(1);
  };

  if (!data) {
    return <div className="p-8 text-gray-500">Loading learning hub...</div>;
  }

  const { summary: s, today: t, daily, learnings: previewLessons, local_model: lm, training } = data;
  const footprints = tab === 'footprints' ? listItems : [];
  const specials = tab === 'specials' ? listItems : [];
  const learnings = tab === 'learnings' ? listItems : (previewLessons || []);
  const news = tab === 'news' ? listItems : [];
  const dailySeries = [...(daily || [])].reverse().map((d) => ({
    ...d,
    label: d.day?.slice(5),
  }));
  const lrColor = (t?.learning_rate || 0) >= 0 ? 'text-accent-green' : 'text-accent-red';
  const todayPnl = t?.pnl ?? 0;
  const pnlColor = todayPnl >= 0 ? 'text-accent-green' : 'text-accent-red';
  const progressPct = Math.min(100, Math.max(0, t?.progress_percent || 0));
  const todayLessons = (previewLessons || []).filter((m) => isSameDay(m.created_at, t?.day));

  return (
    <div className="p-4 max-w-[1400px] mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Learning Hub</h1>
        <p className="text-sm text-gray-500 mt-1">
          Today P&amp;L, lessons, decision footprints, and the local model
        </p>
      </div>

      <div className="card border border-accent-blue/30 bg-blue-950/20">
        <div className="flex flex-col lg:flex-row lg:items-stretch gap-4">
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-400 mb-1">Today profit &amp; loss</div>
            <div className={`text-3xl font-bold tabular-nums ${pnlColor}`}>
              {todayPnl >= 0 ? '+' : ''}{formatPrice(todayPnl)}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {t?.wins ?? 0}W / {t?.losses ?? 0}L · {t?.trades_closed ?? 0} closed
              {t?.target_usd != null && (
                <span>
                  {' '}· target {formatPrice(t.target_usd)}
                  {t.target_status === 'hit' ? ' · HIT' : ''}
                </span>
              )}
            </div>
            {t?.target_usd > 0 && (
              <div className="mt-3">
                <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      t.target_status === 'hit' ? 'bg-accent-green' : todayPnl < 0 ? 'bg-accent-red' : 'bg-accent-blue'
                    }`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <div className="text-[10px] text-gray-500 mt-1">{progressPct}% of daily target</div>
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0 border-t lg:border-t-0 lg:border-l border-dark-600 pt-3 lg:pt-0 lg:pl-4">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="text-xs text-gray-400">Today learnings</div>
              <span className="text-xs text-gray-500">{todayLessons.length} lesson(s)</span>
            </div>
            {todayLessons.length === 0 ? (
              <p className="text-xs text-gray-600 bg-dark-800/60 rounded-lg p-3">
                No new lessons yet today. Lessons appear when trades close (win or loss).
              </p>
            ) : (
              <div className="space-y-2 max-h-36 overflow-y-auto">
                {todayLessons.slice(0, 6).map((m) => (
                  <div key={m.id} className="bg-dark-800/70 rounded-lg px-3 py-2 border-l-2 border-accent-blue">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-500 mb-0.5">
                      <span className="font-medium text-gray-300">{m.coin}</span>
                      <span className={statusColor(m.outcome)}>{m.outcome}</span>
                      {m.pnl != null && (
                        <span className={m.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                          {formatPrice(m.pnl)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-300 line-clamp-2">{m.lesson}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <StatCard
          label="Today P&L"
          value={`${todayPnl >= 0 ? '+' : ''}${formatPrice(todayPnl)}`}
          sub={`${t?.wins ?? 0}W / ${t?.losses ?? 0}L`}
          color={pnlColor}
        />
        <StatCard label="Accuracy" value={`${s.accuracy_percent ?? 0}%`} sub={`${s.closed_trades} closed`} color="text-accent-blue" />
        <StatCard label="Learning rate" value={`${(t?.learning_rate ?? 0) >= 0 ? '+' : ''}${t?.learning_rate ?? 0}`} sub="vs prior day" color={lrColor} />
        <StatCard label="Today closed" value={t?.trades_closed ?? 0} sub={`${t?.special_events ?? 0} special`} />
        <StatCard label="Memories" value={s.memories ?? 0} sub={`+${t?.memories_added ?? 0} today`} />
        <StatCard label="Snapshots" value={s.snapshots_labeled ?? 0} sub={`${s.snapshots_total ?? 0} total`} color="text-accent-yellow" />
        <StatCard label="Specials" value={s.special_count ?? 0} sub="highlighted" color="text-accent-red" />
        <StatCard
          label="Training"
          value={training?.ready ? 'Ready' : 'Warming'}
          sub={`${training?.labeled ?? 0} labeled`}
          color={training?.ready ? 'text-accent-green' : 'text-gray-400'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Daily P&L</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailySeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine y={0} stroke="#6b7280" />
                <Bar dataKey="pnl" name="P&L $" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Accuracy by day</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dailySeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="accuracy_percent" name="Accuracy %" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card border border-accent-green/20 bg-emerald-950/20">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Local model — {lm?.name}</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Online weight updates on every closed trade · version {lm?.version} · {lm?.samples} samples
            </p>
          </div>
          <div className="text-xs text-gray-500">
            Updated {lm?.updated_at ? new Date(lm.updated_at).toLocaleString() : '—'}
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          {Object.entries(lm?.weights || {}).map(([k, v]) => (
            <div key={k} className="bg-dark-800/80 rounded-lg px-3 py-2">
              <div className="text-[10px] text-gray-500 truncate">{k}</div>
              <div className="text-sm font-mono text-accent-green">{Number(v).toFixed(3)}</div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-gray-600 mt-3">{training?.note}</p>
      </div>

      <div className="flex gap-2 border-b border-dark-600 pb-2">
        {[
          ['footprints', 'Decision footprints'],
          ['specials', 'Special highlights'],
          ['learnings', 'Lessons'],
          ['news', 'Market news'],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => changeTab(id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === id ? 'bg-accent-blue text-white' : 'text-gray-400 hover:bg-dark-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'footprints' && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-dark-600">
                <th className="pb-2 pr-3">When</th>
                <th className="pb-2 pr-3">Coin</th>
                <th className="pb-2 pr-3">Dir</th>
                <th className="pb-2 pr-3">Conf</th>
                <th className="pb-2 pr-3">Local</th>
                <th className="pb-2 pr-3">Status</th>
                <th className="pb-2 pr-3">PnL</th>
                <th className="pb-2">Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {footprints.map((f) => (
                <tr
                  key={f.id}
                  className={`border-b border-dark-700/60 ${
                    f.special ? 'bg-amber-900/20 ring-1 ring-inset ring-amber-500/30' : ''
                  }`}
                >
                  <td className="py-2 pr-3 text-xs text-gray-500 whitespace-nowrap">
                    {f.created_at ? new Date(f.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-2 pr-3 font-medium">{f.coin}</td>
                  <td className="py-2 pr-3 uppercase text-xs">{f.direction}</td>
                  <td className="py-2 pr-3">{f.confidence ?? '—'}</td>
                  <td className="py-2 pr-3 text-accent-blue">{f.local_score != null ? Number(f.local_score).toFixed(0) : '—'}</td>
                  <td className={`py-2 pr-3 font-medium ${statusColor(f.status)}`}>
                    {f.status}
                    {f.special && (
                      <span className="ml-2 text-[10px] text-amber-400" title={f.special_reason || ''}>
                        ★ SPECIAL
                      </span>
                    )}
                  </td>
                  <td className={`py-2 pr-3 ${f.outcome_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    {f.outcome_pnl != null ? `$${Number(f.outcome_pnl).toFixed(2)}` : '—'}
                  </td>
                  <td className="py-2 text-xs text-gray-400 max-w-md truncate" title={f.reasoning || ''}>
                    {f.reasoning || '—'}
                  </td>
                </tr>
              ))}
              {!footprints.length && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-gray-500">
                    No decision footprints yet — they appear as the agent trades
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <PaginationBar
            page={listMeta.page}
            pages={listMeta.pages}
            total={listMeta.total}
            pageSize={listMeta.page_size}
            onPageChange={setPage}
            label="footprints"
          />
        </div>
      )}

      {tab === 'specials' && (
        <div className="space-y-2">
          {specials.map((sp) => (
            <div key={`${sp.id}-${sp.created_at}`} className="card border border-amber-500/40 bg-amber-950/20">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-amber-400 text-xs font-bold">★ SPECIAL</span>
                <span className="font-semibold">{sp.coin}</span>
                <span className="text-xs uppercase text-gray-400">{sp.direction}</span>
                <span className={`text-xs font-medium ${statusColor(sp.status || sp.outcome)}`}>{sp.status || sp.outcome}</span>
                <span className="text-xs text-gray-500">conf {sp.confidence}</span>
                {(sp.outcome_pnl ?? sp.pnl) != null && (
                  <span className={`text-xs ${(sp.outcome_pnl ?? sp.pnl) >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    ${Number(sp.outcome_pnl ?? sp.pnl).toFixed(2)}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-300">{sp.special_reason || sp.reasoning || '—'}</p>
            </div>
          ))}
          {!specials.length && (
            <div className="card text-center text-gray-500 py-8">
              Special highlights appear on high-confidence losses, low-confidence wins, and large P&L moves
            </div>
          )}
          <PaginationBar
            page={listMeta.page}
            pages={listMeta.pages}
            total={listMeta.total}
            pageSize={listMeta.page_size}
            onPageChange={setPage}
            label="specials"
          />
        </div>
      )}

      {tab === 'learnings' && (
        <div className="space-y-2">
          {learnings.map((m) => (
            <div key={m.id} className="card">
              <div className="flex flex-wrap items-center gap-2 mb-1 text-xs text-gray-500">
                <span className="font-semibold text-gray-300">{m.coin}</span>
                <span className="uppercase">{m.direction}</span>
                <span className={statusColor(m.outcome)}>{m.outcome}</span>
                {m.pnl != null && (
                  <span className={m.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                    {formatPrice(m.pnl)}
                  </span>
                )}
                <span>{m.created_at ? new Date(m.created_at).toLocaleString() : ''}</span>
              </div>
              <p className="text-sm text-gray-300">{m.lesson}</p>
            </div>
          ))}
          {!learnings.length && (
            <div className="card text-center text-gray-500 py-8">Lessons appear when trades close</div>
          )}
          <PaginationBar
            page={listMeta.page}
            pages={listMeta.pages}
            total={listMeta.total}
            pageSize={listMeta.page_size}
            onPageChange={setPage}
            label="lessons"
          />
        </div>
      )}

      {tab === 'news' && (
        <div className="space-y-2">
          {news.map((n) => (
            <a
              key={n.id}
              href={n.url || '#'}
              target="_blank"
              rel="noreferrer"
              className="card block hover:border-accent-blue/40 transition-colors"
            >
              <div className="text-sm text-gray-200">{n.title}</div>
              <div className="text-[11px] text-gray-500 mt-1 flex flex-wrap gap-2">
                <span>{n.source}</span>
                {n.currencies && <span>{n.currencies}</span>}
                <span>{n.published_at ? new Date(n.published_at).toLocaleString() : ''}</span>
              </div>
            </a>
          ))}
          {!news.length && (
            <div className="card text-center text-gray-500 py-8">
              News will appear after the next data ingestion cycle
            </div>
          )}
          <PaginationBar
            page={listMeta.page}
            pages={listMeta.pages}
            total={listMeta.total}
            pageSize={listMeta.page_size}
            onPageChange={setPage}
            label="headlines"
          />
        </div>
      )}

      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Daily footprint</h3>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={dailySeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="trades_closed" name="Trades" stroke="#eab308" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="memories_added" name="Memories" stroke="#a78bfa" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="special_events" name="Specials" stroke="#f59e0b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
