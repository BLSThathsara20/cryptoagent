import { useLivePulse } from '../LivePulseContext';

const BUSY = new Set(['preparing', 'analysing', 'deciding', 'executing', 'running']);

const STAGE_COPY = {
  preparing: { title: 'Preparing to decide', sub: 'Gathering context before the next call' },
  analysing: { title: 'Reading market', sub: 'Scanning prices, signals, and portfolio' },
  deciding: { title: 'Getting decision', sub: 'AI is choosing the best setup' },
  executing: { title: 'Placing trade', sub: 'Recording entry, TP, and stop loss' },
  running: { title: 'Placing trade', sub: 'Recording entry, TP, and stop loss' },
};

/**
 * Full-width glow strip on Dashboard while the agent is in an active cycle.
 */
export default function DecisionGlowBanner() {
  const { pulse } = useLivePulse();
  const agent = pulse?.agent;

  const stage = agent?.stage || '';
  const active = Boolean(agent?.loop_running) && BUSY.has(stage);
  if (!active) return null;

  const copy = STAGE_COPY[stage] || { title: 'Agent working', sub: stage };

  return (
    <div className="decision-glow-banner px-4 py-3 border-b border-accent-blue/40">
      <div className="max-w-[1600px] mx-auto flex items-center gap-3">
        <span className="decision-glow-orb" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white tracking-wide">{copy.title}</p>
          <p className="text-xs text-blue-200/80 truncate">{copy.sub}</p>
        </div>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-blue-200/70 hidden sm:inline">
          Live cycle
        </span>
      </div>
    </div>
  );
}
