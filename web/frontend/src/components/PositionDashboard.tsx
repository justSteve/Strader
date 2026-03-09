import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Position, PortfolioSummary } from '../types';

const S: Record<string, React.CSSProperties> = {
  wrap: { padding: 12 },
  summary: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8, marginBottom: 12 },
  card: { background: '#111118', border: '1px solid #1e1e2e', borderRadius: 6, padding: '8px 12px' },
  cardLabel: { fontSize: 9, color: '#666', textTransform: 'uppercase' as const, letterSpacing: 1 },
  cardVal: { fontSize: 18, fontWeight: 700, marginTop: 2 },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 11 },
  th: { padding: '6px 8px', borderBottom: '1px solid #2a2a3a', color: '#888', textTransform: 'uppercase' as const, fontSize: 9, textAlign: 'left' as const },
  td: { padding: '5px 8px', borderBottom: '1px solid #1a1a2a', fontVariantNumeric: 'tabular-nums' },
  pos: { color: '#00e676' },
  neg: { color: '#ff1744' },
};

function pnlColor(v: number): React.CSSProperties {
  return v >= 0 ? S.pos : S.neg;
}

function fmt(v: number, prefix = '$'): string {
  return `${prefix}${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function PositionDashboard() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);

  useEffect(() => {
    const load = () => {
      api.positions.list().then((d) => setPositions(d as Position[]));
      api.positions.summary().then((d) => setSummary(d as PortfolioSummary));
    };
    load();
    const iv = setInterval(load, 3000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div style={S.wrap}>
      {summary && (
        <div style={S.summary}>
          <div style={S.card}>
            <div style={S.cardLabel}>Positions</div>
            <div style={S.cardVal}>{summary.position_count}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Market Value</div>
            <div style={S.cardVal}>{fmt(summary.total_market_value)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Day P&L</div>
            <div style={{ ...S.cardVal, ...pnlColor(summary.day_pnl) }}>{fmt(summary.day_pnl)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Unrealized</div>
            <div style={{ ...S.cardVal, ...pnlColor(summary.unrealized_pnl) }}>{fmt(summary.unrealized_pnl)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Delta</div>
            <div style={S.cardVal}>{summary.greeks.delta.toFixed(2)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Gamma</div>
            <div style={S.cardVal}>{summary.greeks.gamma.toFixed(4)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Theta</div>
            <div style={{ ...S.cardVal, color: '#ff9800' }}>{summary.greeks.theta.toFixed(2)}</div>
          </div>
          <div style={S.card}>
            <div style={S.cardLabel}>Vega</div>
            <div style={S.cardVal}>{summary.greeks.vega.toFixed(3)}</div>
          </div>
        </div>
      )}
      <table style={S.table}>
        <thead>
          <tr>
            {['Symbol', 'Strategy', 'Qty', 'Avg Price', 'Mkt Value', 'Day P&L', 'Unreal P&L', 'Delta', 'Gamma', 'Theta', 'Vega'].map((h) => (
              <th key={h} style={S.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.id}>
              <td style={S.td}>{p.symbol}</td>
              <td style={S.td}>{p.strategy}</td>
              <td style={S.td}>{p.quantity}</td>
              <td style={S.td}>{fmt(p.average_price)}</td>
              <td style={S.td}>{fmt(p.market_value)}</td>
              <td style={{ ...S.td, ...pnlColor(p.day_pnl) }}>{fmt(p.day_pnl)}</td>
              <td style={{ ...S.td, ...pnlColor(p.unrealized_pnl) }}>{fmt(p.unrealized_pnl)}</td>
              <td style={S.td}>{p.delta.toFixed(3)}</td>
              <td style={S.td}>{p.gamma.toFixed(4)}</td>
              <td style={S.td}>{p.theta.toFixed(3)}</td>
              <td style={S.td}>{p.vega.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
