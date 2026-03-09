import { useState, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { api } from '../../services/api'
import type { ButterflyPreview, VerticalPreview, RiskGraphPoint } from '../../types'

type BuilderMode = 'butterfly' | 'vertical'

function fmt(n: number, d = 2): string {
  return n.toFixed(d)
}

export function TradeBuilder() {
  const [mode, setMode] = useState<BuilderMode>('butterfly')

  // Butterfly params
  const [bfCenter, setBfCenter] = useState(5850)
  const [bfWidth, setBfWidth] = useState(10)
  const [bfType, setBfType] = useState<'CALL' | 'PUT'>('CALL')
  const [bfQty, setBfQty] = useState(1)
  const [bfExp, setBfExp] = useState(new Date().toISOString().slice(0, 10))

  // Vertical params
  const [vsLong, setVsLong] = useState(5840)
  const [vsShort, setVsShort] = useState(5850)
  const [vsType, setVsType] = useState<'CALL' | 'PUT'>('CALL')
  const [vsQty, setVsQty] = useState(1)
  const [vsExp, setVsExp] = useState(new Date().toISOString().slice(0, 10))

  const [preview, setPreview] = useState<ButterflyPreview | VerticalPreview | null>(null)
  const [loading, setLoading] = useState(false)

  const handlePreview = useCallback(async () => {
    setLoading(true)
    try {
      if (mode === 'butterfly') {
        const result = await api.previewButterfly({
          center_strike: bfCenter,
          wing_width: bfWidth,
          expiration: bfExp,
          option_type: bfType,
          quantity: bfQty,
        })
        setPreview(result as ButterflyPreview)
      } else {
        const result = await api.previewVertical({
          long_strike: vsLong,
          short_strike: vsShort,
          expiration: vsExp,
          option_type: vsType,
          quantity: vsQty,
        })
        setPreview(result as VerticalPreview)
      }
    } catch (e) {
      console.error('Preview failed:', e)
    } finally {
      setLoading(false)
    }
  }, [mode, bfCenter, bfWidth, bfType, bfQty, bfExp, vsLong, vsShort, vsType, vsQty, vsExp])

  return (
    <div style={{ height: '100%', display: 'flex', gap: 8, padding: 8 }}>
      {/* Builder panel */}
      <div className="panel" style={{ width: 320, flexShrink: 0 }}>
        <div className="panel-header">
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              className={mode === 'butterfly' ? 'primary' : ''}
              onClick={() => { setMode('butterfly'); setPreview(null) }}
              style={{ fontSize: 11 }}
            >
              Butterfly
            </button>
            <button
              className={mode === 'vertical' ? 'primary' : ''}
              onClick={() => { setMode('vertical'); setPreview(null) }}
              style={{ fontSize: 11 }}
            >
              Vertical
            </button>
          </div>
        </div>
        <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mode === 'butterfly' ? (
            <>
              <Field label="Center Strike">
                <input type="number" value={bfCenter} onChange={e => setBfCenter(+e.target.value)} step={5} style={{ width: '100%' }} />
              </Field>
              <Field label="Wing Width">
                <input type="number" value={bfWidth} onChange={e => setBfWidth(+e.target.value)} step={5} min={5} style={{ width: '100%' }} />
              </Field>
              <Field label="Type">
                <select value={bfType} onChange={e => setBfType(e.target.value as 'CALL' | 'PUT')} style={{ width: '100%' }}>
                  <option value="CALL">Call</option>
                  <option value="PUT">Put</option>
                </select>
              </Field>
              <Field label="Quantity">
                <input type="number" value={bfQty} onChange={e => setBfQty(+e.target.value)} min={1} max={50} style={{ width: '100%' }} />
              </Field>
              <Field label="Expiration">
                <input type="date" value={bfExp} onChange={e => setBfExp(e.target.value)} style={{ width: '100%' }} />
              </Field>
            </>
          ) : (
            <>
              <Field label="Long Strike">
                <input type="number" value={vsLong} onChange={e => setVsLong(+e.target.value)} step={5} style={{ width: '100%' }} />
              </Field>
              <Field label="Short Strike">
                <input type="number" value={vsShort} onChange={e => setVsShort(+e.target.value)} step={5} style={{ width: '100%' }} />
              </Field>
              <Field label="Type">
                <select value={vsType} onChange={e => setVsType(e.target.value as 'CALL' | 'PUT')} style={{ width: '100%' }}>
                  <option value="CALL">Call</option>
                  <option value="PUT">Put</option>
                </select>
              </Field>
              <Field label="Quantity">
                <input type="number" value={vsQty} onChange={e => setVsQty(+e.target.value)} min={1} max={50} style={{ width: '100%' }} />
              </Field>
              <Field label="Expiration">
                <input type="date" value={vsExp} onChange={e => setVsExp(e.target.value)} style={{ width: '100%' }} />
              </Field>
            </>
          )}

          <button className="primary" onClick={handlePreview} disabled={loading} style={{ marginTop: 8 }}>
            {loading ? 'Computing...' : 'Preview'}
          </button>

          {/* Risk check results */}
          {preview?.risk_check && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
                RISK CHECK:{' '}
                <span className={preview.risk_check.approved ? 'positive' : 'negative'}>
                  {preview.risk_check.approved ? 'APPROVED' : 'BLOCKED'}
                </span>
              </div>
              {preview.risk_check.issues.map((issue, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--red)', marginBottom: 2 }}>
                  {issue}
                </div>
              ))}
              <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                Risk: {preview.risk_check.risk_pct}% | Delta after: {preview.risk_check.delta_after}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Risk graph */}
      <div className="panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div className="panel-header">
          <span>P&L at Expiration</span>
          {preview && (
            <span className="mono" style={{ fontSize: 11 }}>
              {'max_profit' in preview && `Max Profit: $${fmt(preview.max_profit)}`}
              {' | '}
              {'max_loss_estimate' in preview
                ? `Max Loss: $${fmt((preview as ButterflyPreview).max_loss_estimate)}`
                : `Max Loss: $${fmt((preview as VerticalPreview).max_loss)}`
              }
            </span>
          )}
        </div>
        <div style={{ flex: 1, padding: 8 }}>
          {preview ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={preview.risk_graph}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="price"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: number) => v.toFixed(0)}
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
                  labelFormatter={(l: number) => `SPX: ${l.toFixed(0)}`}
                />
                <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="pnl"
                  stroke="var(--blue)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="muted text-center" style={{ paddingTop: 60 }}>
              Configure a trade and click Preview to see the risk graph
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', display: 'block', marginBottom: 3 }}>
        {label}
      </label>
      {children}
    </div>
  )
}
