import { useStore } from '../../store';

function fmt(n: number | null, d = 2): string {
  return n != null ? n.toFixed(d) : '-';
}

function pnlClass(n: number | null): string {
  if (n == null) return 'neutral';
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}

export default function PositionDashboard() {
  const positions = useStore(s => s.positions);
  const greeks = useStore(s => s.greeks);

  const totalPnlDay = positions.reduce((sum, p) => sum + (p.pnl_day || 0), 0);
  const totalPnlTotal = positions.reduce((sum, p) => sum + (p.pnl_total || 0), 0);
  const totalValue = positions.reduce((sum, p) => sum + (p.market_value || 0), 0);

  return (
    <div className="panel" style={{ overflow: 'auto' }}>
      <div className="panel-header">
        <span>Positions ({positions.length})</span>
        <div style={{ display: 'flex', gap: '16px', fontSize: 'var(--font-size-xs)' }}>
          <span>
            Day: <span className={pnlClass(totalPnlDay)}>${fmt(totalPnlDay)}</span>
          </span>
          <span>
            Total: <span className={pnlClass(totalPnlTotal)}>${fmt(totalPnlTotal)}</span>
          </span>
          <span>
            Value: <span>${fmt(totalValue)}</span>
          </span>
        </div>
      </div>

      {/* Greeks rollup */}
      {greeks && (
        <div style={{
          display: 'flex', gap: '16px', padding: '6px 12px',
          background: 'var(--bg-primary)', borderBottom: '1px solid var(--border)',
          fontSize: 'var(--font-size-xs)',
        }}>
          <span>
            <span style={{ color: 'var(--text-muted)' }}>Delta:</span>{' '}
            <span className={pnlClass(greeks.total_delta)}>{fmt(greeks.total_delta, 4)}</span>
          </span>
          <span>
            <span style={{ color: 'var(--text-muted)' }}>Gamma:</span>{' '}
            <span>{fmt(greeks.total_gamma, 6)}</span>
          </span>
          <span>
            <span style={{ color: 'var(--text-muted)' }}>Theta:</span>{' '}
            <span className={pnlClass(greeks.total_theta)}>{fmt(greeks.total_theta, 4)}</span>
          </span>
          <span>
            <span style={{ color: 'var(--text-muted)' }}>Vega:</span>{' '}
            <span>{fmt(greeks.total_vega, 4)}</span>
          </span>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th className="text-left">Symbol</th>
            <th>Qty</th>
            <th>Avg</th>
            <th>Last</th>
            <th>MktVal</th>
            <th>Day P&L</th>
            <th>Total P&L</th>
            <th>Delta</th>
            <th>Gamma</th>
            <th>Theta</th>
            <th>Vega</th>
          </tr>
        </thead>
        <tbody>
          {positions.length === 0 ? (
            <tr>
              <td colSpan={11} className="text-center" style={{ padding: '20px', color: 'var(--text-muted)' }}>
                No open positions
              </td>
            </tr>
          ) : (
            positions.map((pos, i) => (
              <tr key={i}>
                <td className="text-left" style={{ color: 'var(--blue)' }}>
                  {pos.option_symbol || pos.symbol}
                </td>
                <td className={pos.quantity > 0 ? 'positive' : 'negative'}>
                  {pos.quantity > 0 ? '+' : ''}{pos.quantity}
                </td>
                <td>{fmt(pos.avg_price)}</td>
                <td>{fmt(pos.current_price)}</td>
                <td>{fmt(pos.market_value)}</td>
                <td className={pnlClass(pos.pnl_day)}>{fmt(pos.pnl_day)}</td>
                <td className={pnlClass(pos.pnl_total)}>{fmt(pos.pnl_total)}</td>
                <td>{fmt(pos.delta, 4)}</td>
                <td>{fmt(pos.gamma, 4)}</td>
                <td>{fmt(pos.theta, 4)}</td>
                <td>{fmt(pos.vega, 4)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
