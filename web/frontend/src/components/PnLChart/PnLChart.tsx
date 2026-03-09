import { useState, useCallback } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import type { DailyPnL, IntradayPoint } from '../../types'

function fmt(n: number): string {
  return n.toFixed(2)
}

export function PnLChart() {
  const [view, setView] = useState<'intraday' | 'daily'>('intraday')

  const intradayFetcher = useCallback(() => api.getIntradayPnL() as Promise<IntradayPoint[]>, [])
  const dailyFetcher = useCallback(() => api.getDailyPnL(30) as Promise<DailyPnL[]>, [])

  const { data: intraday } = usePolling(intradayFetcher, 10000)
  const { data: daily } = usePolling(dailyFetcher, 30000)

  const currentPnl = intraday?.[intraday.length - 1]?.pnl ?? 0
  const totalDaily = daily?.reduce((s, d) => s + d.total_pnl, 0) ?? 0
  const totalWins = daily?.reduce((s, d) => s + d.win_count, 0) ?? 0
  const totalLosses = daily?.reduce((s, d) => s + d.loss_count, 0) ?? 0
  const winRate = totalWins + totalLosses > 0 ? (totalWins / (totalWins + totalLosses) * 100) : 0

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8, padding: 8 }}>
      {/* Stats row */}
      <div style={{ display: 'flex', gap: 8 }}>
        <Stat label="Intraday P&L" value={`$${fmt(currentPnl)}`} className={currentPnl >= 0 ? 'positive' : 'negative'} />
        <Stat label="30d Total" value={`$${fmt(totalDaily)}`} className={totalDaily >= 0 ? 'positive' : 'negative'} />
        <Stat label="Win Rate" value={`${winRate.toFixed(0)}%`} className={winRate >= 50 ? 'positive' : 'negative'} />
        <Stat label="W/L" value={`${totalWins}/${totalLosses}`} className="neutral" />
      </div>

      {/* Chart toggle */}
      <div className="panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div className="panel-header">
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              className={view === 'intraday' ? 'primary' : ''}
              onClick={() => setView('intraday')}
              style={{ fontSize: 11 }}
            >
              Intraday
            </button>
            <button
              className={view === 'daily' ? 'primary' : ''}
              onClick={() => setView('daily')}
              style={{ fontSize: 11 }}
            >
              Daily
            </button>
          </div>
        </div>
        <div style={{ flex: 1, padding: 8 }}>
          {view === 'intraday' ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={intraday ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="time"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10 }}
                  interval={29}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                  }}
                  formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
                />
                <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="pnl"
                  stroke={currentPnl >= 0 ? 'var(--green)' : 'var(--red)'}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="trade_date"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                  }}
                  formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name]}
                />
                <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="3 3" />
                <Bar dataKey="total_pnl" name="P&L">
                  {(daily ?? []).map((entry, i) => (
                    <Cell key={i} fill={entry.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, className }: { label: string; value: string; className: string }) {
  return (
    <div className="panel" style={{ flex: 1 }}>
      <div className="panel-body" style={{ textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
        <div className="muted" style={{ fontSize: 10, marginBottom: 2 }}>{label}</div>
        <div className={className} style={{ fontSize: 18, fontWeight: 700 }}>{value}</div>
      </div>
    </div>
  )
}
