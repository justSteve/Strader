import { useCallback } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import type { Position, PortfolioGreeks } from '../../types'

function fmt(n: number, d = 2): string {
  return n.toFixed(d)
}

function pnlClass(n: number): string {
  if (n > 0) return 'positive'
  if (n < 0) return 'negative'
  return 'neutral'
}

export function PositionDashboard() {
  const posFetcher = useCallback(() => api.getPositions() as Promise<Position[]>, [])
  const greeksFetcher = useCallback(() => api.getPortfolioGreeks() as Promise<PortfolioGreeks>, [])
  const balFetcher = useCallback(() => api.getAccountBalance() as Promise<Record<string, number>>, [])

  const { data: positions } = usePolling(posFetcher, 5000)
  const { data: greeks } = usePolling(greeksFetcher, 5000)
  const { data: balance } = usePolling(balFetcher, 10000)

  const totalDayPnl = positions?.reduce((s, p) => s + p.day_pnl, 0) ?? 0
  const totalPnl = positions?.reduce((s, p) => s + p.total_pnl, 0) ?? 0

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8, padding: 8 }}>
      {/* Summary row */}
      <div style={{ display: 'flex', gap: 8 }}>
        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">Account</div>
          <div className="panel-body" style={{ display: 'flex', gap: 24, fontFamily: 'var(--font-mono)' }}>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>NAV</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>${balance?.liquidation_value?.toLocaleString() ?? '-'}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>BUYING POWER</div>
              <div>${balance?.buying_power?.toLocaleString() ?? '-'}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>DAY P&L</div>
              <div className={pnlClass(totalDayPnl)} style={{ fontSize: 16, fontWeight: 700 }}>
                {totalDayPnl >= 0 ? '+' : ''}${fmt(totalDayPnl)}
              </div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>TOTAL P&L</div>
              <div className={pnlClass(totalPnl)}>
                {totalPnl >= 0 ? '+' : ''}${fmt(totalPnl)}
              </div>
            </div>
          </div>
        </div>

        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">Portfolio Greeks</div>
          <div className="panel-body" style={{ display: 'flex', gap: 24, fontFamily: 'var(--font-mono)' }}>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>DELTA</div>
              <div style={{ fontWeight: 600 }}>{greeks ? fmt(greeks.total_delta) : '-'}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>GAMMA</div>
              <div>{greeks ? fmt(greeks.total_gamma, 4) : '-'}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>THETA</div>
              <div className={pnlClass(greeks?.total_theta ?? 0)}>
                {greeks ? fmt(greeks.total_theta) : '-'}
              </div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>VEGA</div>
              <div>{greeks ? fmt(greeks.total_vega, 4) : '-'}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 10 }}>NET PREM</div>
              <div>${greeks ? fmt(greeks.net_premium) : '-'}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Positions table */}
      <div className="panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div className="panel-header">
          <span>Open Positions</span>
          <span className="muted">{positions?.length ?? 0} positions</span>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Symbol</th>
                <th style={{ textAlign: 'left' }}>Description</th>
                <th>Qty</th>
                <th>Avg Price</th>
                <th>Mkt Value</th>
                <th>Day P&L</th>
                <th>Total P&L</th>
                <th>P&L %</th>
                <th>Delta</th>
                <th>Gamma</th>
                <th>Theta</th>
                <th>Vega</th>
              </tr>
            </thead>
            <tbody>
              {(positions ?? []).map((p, i) => (
                <tr key={i}>
                  <td style={{ textAlign: 'left', color: 'var(--cyan)' }}>{p.symbol}</td>
                  <td style={{ textAlign: 'left', fontSize: 11 }}>{p.description}</td>
                  <td style={{ color: p.quantity > 0 ? 'var(--green)' : 'var(--red)' }}>
                    {p.quantity > 0 ? '+' : ''}{p.quantity}
                  </td>
                  <td>${fmt(p.average_price)}</td>
                  <td>${fmt(p.market_value)}</td>
                  <td className={pnlClass(p.day_pnl)}>
                    {p.day_pnl >= 0 ? '+' : ''}${fmt(p.day_pnl)}
                  </td>
                  <td className={pnlClass(p.total_pnl)}>
                    {p.total_pnl >= 0 ? '+' : ''}${fmt(p.total_pnl)}
                  </td>
                  <td className={pnlClass(p.pnl_pct)}>
                    {p.pnl_pct >= 0 ? '+' : ''}{fmt(p.pnl_pct)}%
                  </td>
                  <td>{fmt(p.delta, 4)}</td>
                  <td>{fmt(p.gamma, 4)}</td>
                  <td>{fmt(p.theta)}</td>
                  <td>{fmt(p.vega, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
