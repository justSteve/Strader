import { useCallback } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import type { RiskStatus } from '../../types'

function fmt(n: number, d = 2): string {
  return n.toFixed(d)
}

function ProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, Math.abs(value / max) * 100)
  const isWarning = pct > 70
  const isBreach = pct > 100

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={styles.barTrack}>
        <div
          style={{
            ...styles.barFill,
            width: `${Math.min(pct, 100)}%`,
            background: isBreach ? 'var(--red)' : isWarning ? 'var(--yellow)' : color,
          }}
        />
      </div>
      <span className="mono" style={{ fontSize: 11, minWidth: 40, textAlign: 'right' }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

export function RiskPanel() {
  const fetcher = useCallback(() => api.getRiskStatus() as Promise<RiskStatus>, [])
  const { data: risk } = usePolling(fetcher, 5000)

  if (!risk) {
    return <div className="p-3 muted">Loading risk status...</div>
  }

  const hasBreaches = risk.breaches.length > 0

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8, padding: 8 }}>
      {/* Alert banner */}
      {hasBreaches && (
        <div style={styles.alertBanner}>
          [ALERT] RISK LIMIT BREACH
          {risk.breaches.map((b, i) => (
            <div key={i} style={{ fontSize: 12, marginTop: 2 }}>{b}</div>
          ))}
        </div>
      )}

      {/* Limits grid */}
      <div style={{ display: 'flex', gap: 8 }}>
        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">Daily P&L vs Limit</div>
          <div className="panel-body">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span className={risk.daily_pnl >= 0 ? 'positive' : 'negative'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 18 }}>
                ${fmt(risk.daily_pnl)}
              </span>
              <span className="muted mono">/ -${fmt(risk.daily_limit)}</span>
            </div>
            <ProgressBar value={risk.daily_pnl} max={risk.daily_limit} color="var(--blue)" />
          </div>
        </div>

        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">Position Count</div>
          <div className="panel-body">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span className="mono" style={{ fontWeight: 700, fontSize: 18 }}>
                {risk.position_count}
              </span>
              <span className="muted mono">/ {risk.max_positions}</span>
            </div>
            <ProgressBar value={risk.position_count} max={risk.max_positions} color="var(--cyan)" />
          </div>
        </div>

        <div className="panel" style={{ flex: 1 }}>
          <div className="panel-header">Portfolio Delta</div>
          <div className="panel-body">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span className="mono" style={{ fontWeight: 700, fontSize: 18 }}>
                {fmt(risk.portfolio_delta)}
              </span>
              <span className="muted mono">/ {fmt(risk.max_delta)}</span>
            </div>
            <ProgressBar value={risk.portfolio_delta} max={risk.max_delta} color="var(--purple)" />
          </div>
        </div>
      </div>

      {/* Greeks detail */}
      <div className="panel" style={{ flex: 0 }}>
        <div className="panel-header">Portfolio Greeks</div>
        <div className="panel-body">
          <table>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Greek</th>
                <th>Value</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <GreekRow label="Delta" value={risk.portfolio_greeks.total_delta} limit={risk.max_delta} />
              <GreekRow label="Gamma" value={risk.portfolio_greeks.total_gamma} />
              <GreekRow label="Theta" value={risk.portfolio_greeks.total_theta} />
              <GreekRow label="Vega" value={risk.portfolio_greeks.total_vega} />
              <tr>
                <td style={{ textAlign: 'left' }}>Net Premium</td>
                <td className="mono">${fmt(risk.portfolio_greeks.net_premium)}</td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Warnings */}
      {risk.warnings.length > 0 && (
        <div className="panel">
          <div className="panel-header">Warnings</div>
          <div className="panel-body">
            {risk.warnings.map((w, i) => (
              <div key={i} style={{ padding: '4px 0', fontSize: 12, color: w.includes('[ESCALATE]') ? 'var(--orange)' : 'var(--yellow)' }}>
                {w}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Max loss scenarios */}
      <div className="panel" style={{ flex: 1 }}>
        <div className="panel-header">Scenario Analysis</div>
        <div className="panel-body">
          <table>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Scenario</th>
                <th>SPX Move</th>
                <th>Est. P&L</th>
                <th>Delta Impact</th>
              </tr>
            </thead>
            <tbody>
              <ScenarioRow label="SPX +1%" move="+1%" pnl={risk.portfolio_greeks.total_delta * 58.5} delta={risk.portfolio_greeks.total_gamma * 58.5 * 100} />
              <ScenarioRow label="SPX -1%" move="-1%" pnl={-risk.portfolio_greeks.total_delta * 58.5} delta={-risk.portfolio_greeks.total_gamma * 58.5 * 100} />
              <ScenarioRow label="SPX +2%" move="+2%" pnl={risk.portfolio_greeks.total_delta * 117} delta={risk.portfolio_greeks.total_gamma * 117 * 100} />
              <ScenarioRow label="SPX -2%" move="-2%" pnl={-risk.portfolio_greeks.total_delta * 117} delta={-risk.portfolio_greeks.total_gamma * 117 * 100} />
              <ScenarioRow label="VIX +5pts" move="VIX+5" pnl={risk.portfolio_greeks.total_vega * 5} delta={0} />
              <ScenarioRow label="1 Day Decay" move="Theta" pnl={risk.portfolio_greeks.total_theta} delta={0} />
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function GreekRow({ label, value, limit }: { label: string; value: number; limit?: number }) {
  const status = limit
    ? Math.abs(value) > limit ? 'BREACH' : Math.abs(value) > limit * 0.7 ? 'WARN' : 'OK'
    : undefined

  return (
    <tr>
      <td style={{ textAlign: 'left' }}>{label}</td>
      <td className="mono">{fmt(value, 4)}</td>
      <td>
        {status && (
          <span className={`badge badge-${status === 'BREACH' ? 'breach' : status === 'WARN' ? 'warning' : 'ok'}`}>
            {status}
          </span>
        )}
      </td>
    </tr>
  )
}

function ScenarioRow({ label, move, pnl, delta }: { label: string; move: string; pnl: number; delta: number }) {
  return (
    <tr>
      <td style={{ textAlign: 'left' }}>{label}</td>
      <td className="mono">{move}</td>
      <td className={`mono ${pnl >= 0 ? 'positive' : 'negative'}`}>
        {pnl >= 0 ? '+' : ''}${fmt(pnl)}
      </td>
      <td className="mono">{delta !== 0 ? `${delta >= 0 ? '+' : ''}${fmt(delta)}` : '-'}</td>
    </tr>
  )
}

const styles: Record<string, React.CSSProperties> = {
  alertBanner: {
    background: 'var(--red-dim)',
    border: '1px solid var(--red)',
    borderRadius: 4,
    padding: '8px 12px',
    color: 'var(--red)',
    fontWeight: 700,
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
  },
  barTrack: {
    flex: 1,
    height: 6,
    background: 'var(--bg-primary)',
    borderRadius: 3,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 3,
    transition: 'width 0.3s',
  },
}
