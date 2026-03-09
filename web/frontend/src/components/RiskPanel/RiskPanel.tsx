import { useStore } from '../../store';

export default function RiskPanel() {
  const alerts = useStore(s => s.alerts);
  const greeks = useStore(s => s.greeks);
  const positions = useStore(s => s.positions);

  const totalValue = positions.reduce((sum, p) => sum + Math.abs(p.market_value || 0), 0);

  return (
    <div className="panel" style={{ overflow: 'auto' }}>
      <div className="panel-header">
        <span>Risk Monitor</span>
        {alerts.some(a => a.breached) && (
          <span className="badge badge-red">BREACH</span>
        )}
      </div>

      {/* Portfolio Greeks Summary */}
      {greeks && (
        <div style={{ padding: '8px 12px' }}>
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginBottom: '4px' }}>
            PORTFOLIO GREEKS
          </div>
          <table>
            <tbody>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Net Delta</td>
                <td className={Math.abs(greeks.total_delta) > 30 ? 'negative' : ''}>
                  {greeks.total_delta.toFixed(4)}
                </td>
              </tr>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Net Gamma</td>
                <td>{greeks.total_gamma.toFixed(6)}</td>
              </tr>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Net Theta</td>
                <td className={greeks.total_theta > 0 ? 'positive' : 'negative'}>
                  ${greeks.total_theta.toFixed(2)}/day
                </td>
              </tr>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Net Vega</td>
                <td>{greeks.total_vega.toFixed(4)}</td>
              </tr>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Net Premium</td>
                <td>${greeks.net_premium.toFixed(2)}</td>
              </tr>
              <tr>
                <td className="text-left" style={{ color: 'var(--text-muted)' }}>Exposure</td>
                <td>${totalValue.toFixed(2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Alerts */}
      <div style={{ padding: '8px 12px' }}>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginBottom: '4px' }}>
          RISK ALERTS
        </div>
        {alerts.length === 0 ? (
          <div style={{ color: 'var(--green)', fontSize: 'var(--font-size-xs)', padding: '8px 0' }}>
            All limits within bounds
          </div>
        ) : (
          alerts.map((alert, i) => (
            <div
              key={i}
              className={`alert-bar`}
              style={{
                marginBottom: '4px',
                borderLeftColor: alert.severity === 'critical' ? 'var(--red)' : 'var(--yellow)',
                background: alert.severity === 'critical' ? 'var(--red-dim)' : '#4d4000',
                color: alert.severity === 'critical' ? 'var(--red)' : 'var(--yellow)',
              }}
            >
              <div>{alert.message}</div>
              <div style={{ fontSize: '10px', marginTop: '2px', opacity: 0.7 }}>
                Current: {alert.current_value.toFixed(2)} / Limit: {alert.limit_value.toFixed(2)}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Max Loss Scenarios */}
      <div style={{ padding: '8px 12px' }}>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginBottom: '4px' }}>
          MAX LOSS SCENARIOS
        </div>
        <table>
          <thead>
            <tr>
              <th className="text-left">Scenario</th>
              <th>Impact</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="text-left" style={{ color: 'var(--text-muted)' }}>SPX -1%</td>
              <td className="negative">
                ${((greeks?.total_delta || 0) * -58.5 + (greeks?.total_gamma || 0) * 58.5 * 58.5 * 0.5).toFixed(2)}
              </td>
            </tr>
            <tr>
              <td className="text-left" style={{ color: 'var(--text-muted)' }}>SPX +1%</td>
              <td className={((greeks?.total_delta || 0) * 58.5) > 0 ? 'positive' : 'negative'}>
                ${((greeks?.total_delta || 0) * 58.5 + (greeks?.total_gamma || 0) * 58.5 * 58.5 * 0.5).toFixed(2)}
              </td>
            </tr>
            <tr>
              <td className="text-left" style={{ color: 'var(--text-muted)' }}>VIX +5pts</td>
              <td className={((greeks?.total_vega || 0) * 5) > 0 ? 'positive' : 'negative'}>
                ${((greeks?.total_vega || 0) * 5 * 100).toFixed(2)}
              </td>
            </tr>
            <tr>
              <td className="text-left" style={{ color: 'var(--text-muted)' }}>1 Day Decay</td>
              <td className={(greeks?.total_theta || 0) > 0 ? 'positive' : 'negative'}>
                ${((greeks?.total_theta || 0) * 100).toFixed(2)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
