import { useState, useCallback, useEffect } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import type { OptionsChainRow, OptionQuote } from '../../types'

function fmt(n: number | undefined, d = 2): string {
  if (n === undefined || n === null) return '-'
  return n.toFixed(d)
}

function fmtInt(n: number | undefined): string {
  if (n === undefined || n === null) return '-'
  return n.toLocaleString()
}

function QuoteCell({ q, field }: { q: OptionQuote | null; field: keyof OptionQuote }) {
  if (!q) return <td className="muted">-</td>
  const val = q[field]
  if (typeof val === 'number') {
    if (field === 'volume' || field === 'open_interest') return <td>{fmtInt(val)}</td>
    if (field === 'iv') return <td>{(val * 100).toFixed(1)}%</td>
    if (field === 'delta' || field === 'gamma' || field === 'vega') return <td>{fmt(val, 4)}</td>
    return <td>{fmt(val)}</td>
  }
  return <td>{String(val)}</td>
}

export function OptionsChain() {
  const [expiration, setExpiration] = useState<string>('')
  const [expirations, setExpirations] = useState<string[]>([])
  const [strikeCount, setStrikeCount] = useState(25)

  useEffect(() => {
    api.getExpirations().then((exps: string[]) => {
      setExpirations(exps)
      if (exps.length > 0 && !expiration) setExpiration(exps[0])
    })
  }, [])

  const fetcher = useCallback(
    () => api.getOptionsChain('$SPX', expiration || undefined, strikeCount) as Promise<OptionsChainRow[]>,
    [expiration, strikeCount],
  )
  const { data: chain, loading } = usePolling(fetcher, 5000)

  const CALL_COLS: { key: keyof OptionQuote; label: string }[] = [
    { key: 'volume', label: 'Vol' },
    { key: 'open_interest', label: 'OI' },
    { key: 'delta', label: 'Delta' },
    { key: 'gamma', label: 'Gamma' },
    { key: 'theta', label: 'Theta' },
    { key: 'iv', label: 'IV' },
    { key: 'bid', label: 'Bid' },
    { key: 'ask', label: 'Ask' },
    { key: 'last', label: 'Last' },
  ]

  const PUT_COLS: { key: keyof OptionQuote; label: string }[] = [
    { key: 'bid', label: 'Bid' },
    { key: 'ask', label: 'Ask' },
    { key: 'last', label: 'Last' },
    { key: 'iv', label: 'IV' },
    { key: 'delta', label: 'Delta' },
    { key: 'gamma', label: 'Gamma' },
    { key: 'theta', label: 'Theta' },
    { key: 'volume', label: 'Vol' },
    { key: 'open_interest', label: 'OI' },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={styles.toolbar}>
        <label>
          <span className="muted" style={{ marginRight: 6, fontSize: 11 }}>EXP</span>
          <select value={expiration} onChange={e => setExpiration(e.target.value)}>
            {expirations.map(exp => (
              <option key={exp} value={exp}>{exp}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="muted" style={{ marginRight: 6, fontSize: 11 }}>STRIKES</span>
          <select value={strikeCount} onChange={e => setStrikeCount(Number(e.target.value))}>
            {[10, 15, 20, 25, 30, 40, 50].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <span className="muted" style={{ fontSize: 11 }}>
          {chain?.length ?? 0} strikes
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading && !chain ? (
          <div className="p-3 muted text-center">Loading chain...</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th colSpan={CALL_COLS.length} style={{ textAlign: 'center', color: 'var(--green)', borderRight: '2px solid var(--border)' }}>
                  CALLS
                </th>
                <th style={{ textAlign: 'center', background: 'var(--bg-primary)' }}>STRIKE</th>
                <th colSpan={PUT_COLS.length} style={{ textAlign: 'center', color: 'var(--red)', borderLeft: '2px solid var(--border)' }}>
                  PUTS
                </th>
              </tr>
              <tr>
                {CALL_COLS.map(c => <th key={`c-${c.key}`}>{c.label}</th>)}
                <th style={{ textAlign: 'center', background: 'var(--bg-primary)' }}></th>
                {PUT_COLS.map(c => <th key={`p-${c.key}`}>{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {(chain ?? []).map(row => (
                <tr
                  key={row.strike}
                  style={{
                    background: row.call?.in_the_money || row.put?.in_the_money
                      ? 'rgba(59,130,246,0.05)'
                      : undefined,
                  }}
                >
                  {CALL_COLS.map(c => (
                    <QuoteCell key={`c-${c.key}`} q={row.call} field={c.key} />
                  ))}
                  <td style={{
                    textAlign: 'center',
                    fontWeight: 700,
                    background: 'var(--bg-primary)',
                    color: 'var(--cyan)',
                    borderLeft: '2px solid var(--border)',
                    borderRight: '2px solid var(--border)',
                  }}>
                    {row.strike.toFixed(0)}
                  </td>
                  {PUT_COLS.map(c => (
                    <QuoteCell key={`p-${c.key}`} q={row.put} field={c.key} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '6px 12px',
    background: 'var(--bg-secondary)',
    borderBottom: '1px solid var(--border)',
  },
}
