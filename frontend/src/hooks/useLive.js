import { useEffect, useRef, useState } from 'react';

/** Wall-clock that updates every `ms` (default 1s) for live countdowns. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/**
 * Call `fn` immediately and on an interval. Survives tab focus.
 * Never stays stuck: overlapping runs are skipped, but a hung run
 * is force-cleared after `intervalMs * 2` so polling continues.
 */
export function usePolling(fn, intervalMs = 5000, deps = []) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const busy = useRef(false);
  const startedAt = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let id = null;

    const run = async () => {
      if (cancelled) return;
      const now = Date.now();
      // Unstick if a previous request hung longer than 2 intervals
      if (busy.current && now - startedAt.current > intervalMs * 2) {
        busy.current = false;
      }
      if (busy.current) return;
      busy.current = true;
      startedAt.current = now;
      try {
        await fnRef.current();
      } catch (e) {
        // Timeouts / network blips are expected — keep polling
        if (e?.name !== 'AbortError') console.error(e);
      } finally {
        busy.current = false;
      }
    };

    run();
    id = setInterval(run, intervalMs);

    const onFocus = () => run();
    const onVis = () => {
      if (document.visibilityState === 'visible') run();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVis);

    return () => {
      cancelled = true;
      clearInterval(id);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}

export function formatCountdown(sec) {
  if (sec == null || Number.isNaN(sec)) return '—';
  const s = Math.max(0, Math.floor(sec));
  if (s <= 0) return 'now';
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m <= 0) return `${r}s`;
  return `${m}m ${String(r).padStart(2, '0')}s`;
}

/** Seconds until ISO timestamp (or null). */
export function secondsUntil(iso, nowMs = Date.now()) {
  if (!iso) return null;
  return Math.max(0, Math.floor((new Date(iso).getTime() - nowMs) / 1000));
}

/** Stages that mean a cycle is actively running (not idle/monitoring). */
export const BUSY_STAGES = ['analysing', 'deciding', 'executing', 'running'];

export function isAgentBusy(stage) {
  return BUSY_STAGES.includes(stage);
}
