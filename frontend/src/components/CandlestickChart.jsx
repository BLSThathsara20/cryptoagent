import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import { fetchAPI } from '../api';

export default function CandlestickChart({ symbol = 'BTC' }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 350,
      layout: { background: { color: '#111827' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      crosshair: { mode: 0 },
      timeScale: { borderColor: '#374151' },
      rightPriceScale: { borderColor: '#374151' },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    chartRef.current = chart;

    const load = async () => {
      try {
        const data = await fetchAPI(`/market/candles/${symbol}?limit=200`);
        candleSeries.setData(data);
        chart.timeScale().fitContent();
      } catch (e) {
        console.error(e);
      }
    };

    load();
    const interval = setInterval(load, 30000);

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      clearInterval(interval);
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [symbol]);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">{symbol}/USDT Chart</h3>
      <div ref={containerRef} />
    </div>
  );
}
