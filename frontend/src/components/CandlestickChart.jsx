import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import { fetchAPI } from '../api';

export default function CandlestickChart({ symbol = 'BTC' }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let disposed = false;
    let chart;
    let candleSeries;

    try {
      chart = createChart(el, {
        width: el.clientWidth || 600,
        height: 350,
        layout: { background: { color: '#111827' }, textColor: '#9ca3af' },
        grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
        crosshair: { mode: 0 },
        timeScale: { borderColor: '#374151' },
        rightPriceScale: { borderColor: '#374151' },
      });

      candleSeries = chart.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
      });
    } catch (e) {
      console.error('Chart init failed:', e);
      return;
    }

    const load = async () => {
      try {
        const data = await fetchAPI(`/market/candles/${symbol}?limit=200`);
        if (disposed || !candleSeries || !chart) return;
        if (!Array.isArray(data) || data.length === 0) return;
        candleSeries.setData(data);
        chart.timeScale().fitContent();
      } catch (e) {
        if (!disposed) console.error(e);
      }
    };

    load();
    const interval = setInterval(load, 10000);

    const handleResize = () => {
      if (disposed || !chart || !containerRef.current) return;
      try {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      } catch {
        /* chart already disposed */
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      disposed = true;
      clearInterval(interval);
      window.removeEventListener('resize', handleResize);
      try {
        chart?.remove();
      } catch {
        /* already disposed */
      }
      chart = null;
      candleSeries = null;
    };
  }, [symbol]);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">{symbol}/USDT Chart</h3>
      <div ref={containerRef} />
    </div>
  );
}
