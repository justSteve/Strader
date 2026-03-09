import { useStore } from '../../store';
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ReferenceLine,
} from 'recharts';

function fmt(n: number): string {
  return n.toFixed(2);
}

function pnlClass(n: number): string {
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}

export default function PnLChart() {
  const todayPnl = useStore(s => s.todayPnl);
  const pnlHistory = useStore(s => s.pnlHistory);

  const chartData = pnlHistory.map(d => ({
    date: d.date.slice(5), // MM-DD
    pnl: d.total_pnl,
    cumulative: 0, // calculated below
    trades: d.trade_count,
  }));

  // Calculate cumulative P&L
  let cum = 0;
  for (const d of chartData) {
    cum += d.pnl;
    d.cumulative = parseFloat(cum.toFixed(2));
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span>P&L</span>
        {todayPnl && (
          <div style={{ display: 'flex', gap: '16px', fontSize: 'var(--font-size-xs)' }}>
            <span>
              Today: <span className={pnlClass(todayPnl.total_pnl)}>${fmt(todayPnl.total_pnl)}</span>
            </span>
            <span>
              Realized: <span className={pnlClass(todayPnl.realized_pnl)}>${fmt(todayPnl.realized_pnl)}</span>
            </span>
            <span>
              Trades: <span>{todayPnl.trade_count}</span>
            </span>
            {todayPnl.win_rate != null && (
              <span>
                Win%: <span className={todayPnl.win_rate >= 50 ? 'positive' : 'negative'}>
                  {todayPnl.win_rate}%
                </span>
              </span>
            )}
            <span>
              DD: <span className="negative">${fmt(todayPnl.max_drawdown)}</span>
            </span>
          </div>
        )}
      </div>

      <div style={{ height: '100%', minHeight: '200px', padding: '8px 0' }}>
        {chartData.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
            No P&L history
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
              <XAxis dataKey="date" tick={{ fill: '#555', fontSize: 10 }} />
              <YAxis yAxisId="pnl" tick={{ fill: '#555', fontSize: 10 }} tickFormatter={v => `$${v}`} />
              <YAxis yAxisId="cum" orientation="right" tick={{ fill: '#555', fontSize: 10 }} tickFormatter={v => `$${v}`} />
              <Tooltip
                contentStyle={{
                  background: '#1a1a25', border: '1px solid #2a2a3a',
                  fontSize: '11px', fontFamily: 'monospace',
                }}
                formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name]}
              />
              <ReferenceLine yAxisId="pnl" y={0} stroke="#2a2a3a" />
              <Bar
                yAxisId="pnl"
                dataKey="pnl"
                fill="#2196f3"
                opacity={0.6}
                barSize={8}
              />
              <Line
                yAxisId="cum"
                type="monotone"
                dataKey="cumulative"
                stroke="#b388ff"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
