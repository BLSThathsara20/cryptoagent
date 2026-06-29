import { useState, useEffect } from 'react';
import { fetchAPI, formatPrice } from '../api';

function StatusDot({ status }) {
  const colors = {
    active: 'bg-accent-green',
    connected: 'bg-accent-green',
    healthy: 'bg-accent-green',
    running: 'bg-accent-green',
    waiting: 'bg-accent-yellow',
    disconnected: 'bg-accent-red',
    needs_api_key: 'bg-accent-yellow',
    degraded: 'bg-accent-red',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-gray-500'}`} />;
}

function timeAgo(iso) {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

export default function Settings() {
  const [system, setSystem] = useState(null);
  const [memories, setMemories] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [s, m] = await Promise.all([
          fetchAPI('/system/status'),
          fetchAPI('/system/memories?limit=10'),
        ]);
        setSystem(s);
        setMemories(m);
        setError(null);
      } catch (e) {
        setError(e.message);
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <div className="card text-accent-red">Failed to load system status: {error}</div>
      </div>
    );
  }

  if (!system) {
    return <div className="p-6 text-gray-500 text-center">Loading system status...</div>;
  }

  const auto = system.automation_level;
  const cfg = system.configuration;

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System & Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Health, data pipeline, agent capabilities, and automation status</p>
      </div>

      {/* Automation Level */}
      <div className="card">
        <div className="flex justify-between items-start mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-300">Automation Level</h2>
            <p className="text-xs text-gray-500 mt-1">{auto.description}</p>
          </div>
          <span className="text-lg font-bold text-accent-blue">{auto.level}</span>
        </div>
        <div className="h-3 bg-dark-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-accent-blue to-accent-green transition-all duration-500"
            style={{ width: `${auto.percent}%` }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-2">{auto.percent}% toward fully autonomous live trading</p>
      </div>

      {/* Autopilot — runs without you */}
      {system.autopilot && (
        <div className="card border border-accent-green/30 bg-green-900/5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-accent-green">Autopilot — Zero Touch</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Trading mode: <span className="text-white uppercase">{system.autopilot.trading_mode}</span>
                {' · '}You do not need to click anything — agents handle everything
              </p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-accent-green/20 text-accent-green font-medium">
              FULL AUTO
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {system.autopilot.automated_tasks?.map((t) => (
              <div key={t.name} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded bg-dark-800/50">
                <StatusDot status={t.active ? 'active' : 'waiting'} />
                <span className="flex-1 text-gray-300">{t.name}</span>
                <span className="text-gray-600">{t.interval}</span>
              </div>
            ))}
          </div>
          {system.autopilot.issues?.length > 0 && (
            <p className="text-xs text-accent-yellow mt-3">
              Auto-fixing: {system.autopilot.issues.join(' · ')}
            </p>
          )}
          {system.backup && (
            <p className="text-xs text-gray-600 mt-2">
              Backups: {system.backup.backup_count} saved · last {system.backup.last_run_at ? timeAgo(system.backup.last_run_at) : 'on startup'}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Health */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">System Health</h2>
          <div className="space-y-2 text-sm">
            {[
              ['Backend API', system.health.backend, 'running'],
              ['Database', system.health.database, system.health.database === 'connected' ? 'connected' : 'disconnected'],
              ['Overall', system.health.status, system.health.status],
              ['Ingestion Scheduler', system.ingestion_scheduler.running ? 'running' : 'stopped', system.ingestion_scheduler.running ? 'running' : 'disconnected'],
            ].map(([label, value, status]) => (
              <div key={label} className="flex justify-between items-center py-1 border-b border-dark-700/50">
                <span className="text-gray-400">{label}</span>
                <span className="flex items-center gap-2">
                  <StatusDot status={status} />
                  <span className="capitalize">{value}</span>
                </span>
              </div>
            ))}
          </div>

          <h3 className="text-xs font-semibold text-gray-500 mt-4 mb-2">Quick Links</h3>
          <div className="flex flex-wrap gap-2">
            <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
              className="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 rounded text-xs text-accent-blue">
              API Documentation ↗
            </a>
            <a href="http://localhost:8000/health" target="_blank" rel="noreferrer"
              className="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 rounded text-xs">
              Health Check ↗
            </a>
            <a href="http://localhost:8000/openapi.json" target="_blank" rel="noreferrer"
              className="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 rounded text-xs">
              OpenAPI JSON ↗
            </a>
          </div>
        </div>

        {/* Configuration */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Configuration</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500 text-xs">Mode</span><p>{cfg.live_mode ? 'LIVE' : 'PAPER'}</p></div>
            <div><span className="text-gray-500 text-xs">Paper Balance</span><p>{formatPrice(cfg.paper_balance)}</p></div>
            <div><span className="text-gray-500 text-xs">Agent Interval</span><p>{cfg.agent_interval_sec}s</p></div>
            <div><span className="text-gray-500 text-xs">Max Risk</span><p>{cfg.max_risk_percent}%</p></div>
            <div><span className="text-gray-500 text-xs">AI Brain</span><p className={cfg.llm_configured ? 'text-accent-green' : 'text-accent-yellow'}>{cfg.llm_model || 'Not set'}</p></div>
            <div><span className="text-gray-500 text-xs">Binance API</span><p className={cfg.binance_configured ? 'text-accent-green' : 'text-gray-500'}>{cfg.binance_configured ? 'Configured' : 'Not set'}</p></div>
            <div><span className="text-gray-500 text-xs">Coinglass</span><p className={cfg.coinglass_configured ? 'text-accent-green' : 'text-accent-yellow'}>{cfg.coinglass_configured ? 'Connected' : 'Not set'}</p></div>
            <div><span className="text-gray-500 text-xs">Lessons Learned</span><p>{system.agent.memories_learned}</p></div>
          </div>
          <p className="text-xs text-gray-600 mt-3">Edit .env file and restart: <code className="text-gray-400">docker compose restart backend</code></p>
        </div>
      </div>

      {/* Data Pipeline */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Data Pipeline — Saving & Processing</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-dark-600 text-gray-400">
                <th className="text-left py-2 px-2">Source</th>
                <th className="text-left py-2 px-2">Status</th>
                <th className="text-left py-2 px-2">Last Update</th>
                <th className="text-right py-2 px-2">Records (24h)</th>
                <th className="text-left py-2 px-2">Interval</th>
              </tr>
            </thead>
            <tbody>
              {system.data_pipeline.map((row) => (
                <tr key={row.name} className="border-b border-dark-700/50">
                  <td className="py-2 px-2 font-medium">{row.name}</td>
                  <td className="py-2 px-2">
                    <span className="flex items-center gap-1.5">
                      <StatusDot status={row.status} />
                      {row.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-gray-400">{timeAgo(row.last_update)}</td>
                  <td className="py-2 px-2 text-right">{row.records_24h?.toLocaleString()}</td>
                  <td className="py-2 px-2 text-gray-500">{row.interval}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          Ingestion cycles: {system.ingestion_scheduler.total_cycles} · WS messages: {system.ingestion_scheduler.last_run_at ? timeAgo(system.ingestion_scheduler.last_run_at) : '—'}
        </p>
      </div>

      {/* Agent Capabilities */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-1">What The Agent Does Right Now</h2>
        <p className="text-xs text-gray-500 mb-4">
          Agent status: <span className="text-white capitalize">{system.agent.status}</span>
          {' · '}Last run: {timeAgo(system.agent.last_run_at)}
          {' · '}Decisions: {system.agent.decisions_total} total ({system.agent.decisions_24h} today)
        </p>

        <h3 className="text-xs font-semibold text-accent-green mb-2">✓ Active (working now)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
          {system.capabilities.active.map((c) => (
            <div key={c.id} className="bg-dark-700/50 rounded-lg p-3">
              <div className="text-sm font-medium">{c.label}</div>
              <div className="text-xs text-gray-500 mt-0.5">{c.detail}</div>
            </div>
          ))}
        </div>

        <h3 className="text-xs font-semibold text-accent-yellow mb-2">⚡ Conditional (needs setup)</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
          {system.capabilities.conditional.map((c) => (
            <div key={c.id} className={`rounded-lg p-3 border ${c.enabled ? 'border-accent-green/30 bg-green-900/10' : 'border-dark-600 bg-dark-700/30'}`}>
              <div className="flex justify-between">
                <span className="text-sm font-medium">{c.label}</span>
                <StatusDot status={c.enabled ? 'active' : 'needs_api_key'} />
              </div>
              <div className="text-xs text-gray-500 mt-1">{c.detail}</div>
            </div>
          ))}
        </div>

        <h3 className="text-xs font-semibold text-accent-blue mb-2">→ Roadmap (your full-auto vision)</h3>
        <div className="space-y-2">
          {system.capabilities.roadmap.map((c) => (
            <div key={c.id} className="flex gap-3 text-xs border-l-2 border-accent-blue/40 pl-3 py-1">
              <span className="text-gray-500 w-16 shrink-0">{c.status}</span>
              <div>
                <span className="font-medium">{c.label}</span>
                <span className="text-gray-500"> — {c.detail}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Database health (long-run) */}
      {system.database && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Database Health (Long-Run)</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
            <div>
              <span className="text-gray-500 text-xs">DB Size</span>
              <p className="font-medium">{system.database.database_size_mb} MB</p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Coin Prices</span>
              <p>{system.database.table_counts?.coin_prices?.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Order Book Rows</span>
              <p>{system.database.table_counts?.order_book?.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-gray-500 text-xs">Live Trades</span>
              <p>{system.database.table_counts?.live_trades?.toLocaleString()}</p>
            </div>
          </div>
          {system.maintenance && (
            <p className="text-xs text-gray-500">
              Auto cleanup: order book {system.maintenance.retention_policy?.order_book_days}d ·
              prices {system.maintenance.retention_policy?.coin_prices_days}d ·
              last run {system.maintenance.last_run_at ? timeAgo(system.maintenance.last_run_at) : 'scheduled daily'}
            </p>
          )}
        </div>
      )}

      {/* Learning Memory */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Agent Learning Memory</h2>
        <p className="text-xs text-gray-500 mb-3">
          Every win/loss is saved and fed into the next agent decision. This is the start of self-improvement.
        </p>
        {memories.length === 0 ? (
          <p className="text-gray-600 text-sm text-center py-6">No lessons yet — agent will learn after first trades close</p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {memories.map((m) => (
              <div key={m.id} className={`text-xs p-3 rounded-lg border ${m.outcome === 'win' ? 'border-green-900/40 bg-green-900/10' : 'border-red-900/40 bg-red-900/10'}`}>
                <div className="flex justify-between mb-1">
                  <span className="font-medium">{m.coin} · {m.outcome.toUpperCase()}</span>
                  <span className={m.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>{formatPrice(m.pnl)}</span>
                </div>
                <p className="text-gray-400">{m.lesson}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
