import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, AreaChart, Area } from 'recharts';
import { api } from '../api/client';
import type { PnLPoint } from '../types';

const S: Record<string, React.CSSProperties> = {
  wrap: { padding: 12 },
  tabs: { display: 'flex', gap: 4, marginBottom: 12 },
  tab: { padding: '4px 12px', background: '#111118', border: '1px solid #1e1e2e', borderRadius: 4, cursor: 'pointer', fontSize: 11, color: '#888' },
  tabActive: { padding: '4px 12px', background: '#7c4dff', border: '1px solid #7c4dff', borderRadius: 4, cursor: 'pointer', fontSize: 11, color: '#fff' },
};

export function PnLChart() {
  const [view, setView] = useState<'intraday' | 'history'>('intraday');
  const [intraday, setIntraday] = useState<PnLPoint[]>([]);
  const [history, setHistory] = useState<PnLPoint[]>([]);

  useEffect(() => {
    api.positions.intradayPnl().then((d) => setIntraday(d as PnLPoint[]));
    api.positions.pnlHistory(30).then((d) => setHistory(d as PnLPoint[]));
  }, []);

  const data = view === 'intraday' ? intraday : history;
  const xKey = view === 'intraday' ? 'time' : 'date';
  const yKey = view === 'intraday' ? 'pnl' : 'cumulative_pnl';

  return (
    <div style={S.wrap}>
      <div style={S.tabs}>
        <button style={view === 'intraday' ? S.tabActive : S.tab} onClick={() => setView('intraday')}>Intraday</button>
        <button style={view === 'history' ? S.tabActive : S.tab} onClick={() => setView('history')}>30-Day</button>
      </div>
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#7c4dff" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#7c4dff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
            <XAxis dataKey={xKey} stroke="#555" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis stroke="#555" tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v}`} />
            <Tooltip
              contentStyle={{ background: '#111118', border: '1px solid #333', fontSize: 11 }}
              formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
            />
            <ReferenceLine y={0} stroke="#444" strokeDasharray="3 3" />
            <Area type="monotone" dataKey={yKey} stroke="#7c4dff" fill="url(#pnlGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
