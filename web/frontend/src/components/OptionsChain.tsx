import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { OptionsChain as OC, Expiration } from '../types';

const S: Record<string, React.CSSProperties> = {
  wrap: { padding: 12, overflow: 'auto', maxHeight: 'calc(100vh - 200px)' },
  header: { display: 'flex', gap: 12, marginBottom: 8, alignItems: 'center' },
  select: { background: '#1a1a2e', color: '#e0e0e0', border: '1px solid #333', padding: '4px 8px', borderRadius: 4, fontSize: 12 },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 11 },
  th: { padding: '4px 6px', borderBottom: '1px solid #2a2a3a', color: '#888', textTransform: 'uppercase' as const, fontSize: 9, letterSpacing: 0.5, position: 'sticky' as const, top: 0, background: '#0f0f18' },
  td: { padding: '3px 6px', borderBottom: '1px solid #1a1a2a', textAlign: 'right' as const, fontVariantNumeric: 'tabular-nums' },
  strikeCell: { padding: '3px 6px', borderBottom: '1px solid #1a1a2a', textAlign: 'center' as const, fontWeight: 700, background: '#151520', color: '#7c4dff' },
  callSide: { background: 'rgba(0, 230, 118, 0.03)' },
  putSide: { background: 'rgba(255, 23, 68, 0.03)' },
  itm: { background: 'rgba(124, 77, 255, 0.08)' },
  spot: { fontSize: 12, color: '#888' },
};

export function OptionsChainGrid() {
  const [chain, setChain] = useState<OC | null>(null);
  const [expirations, setExpirations] = useState<Expiration[]>([]);
  const [selectedExp, setSelectedExp] = useState<string>('');

  useEffect(() => {
    api.options.expirations().then((d) => {
      const exps = d as Expiration[];
      setExpirations(exps);
      if (exps.length > 0) setSelectedExp(exps[0].date);
    });
  }, []);

  useEffect(() => {
    if (!selectedExp) return;
    const load = () => api.options.chain({ expiration: selectedExp }).then((d) => setChain(d as OC));
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [selectedExp]);

  if (!chain) return <div style={S.wrap}>Loading chain...</div>;

  const cols = ['Bid', 'Ask', 'Last', 'Vol', 'OI', 'IV', 'Delta', 'Gamma', 'Theta', 'Vega'];

  return (
    <div style={S.wrap}>
      <div style={S.header}>
        <select style={S.select} value={selectedExp} onChange={(e) => setSelectedExp(e.target.value)}>
          {expirations.map((exp) => (
            <option key={exp.date} value={exp.date}>{exp.label} ({exp.date})</option>
          ))}
        </select>
        <span style={S.spot}>Spot: {chain.spot.toFixed(2)} | DTE: {chain.dte}</span>
      </div>
      <table style={S.table}>
        <thead>
          <tr>
            {cols.map((c) => <th key={'c' + c} style={{ ...S.th, ...S.callSide }}>{c}</th>)}
            <th style={S.th}>Strike</th>
            {cols.map((c) => <th key={'p' + c} style={{ ...S.th, ...S.putSide }}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {chain.chain.map((row) => {
            const isITMCall = row.strike < chain.spot;
            const isITMPut = row.strike > chain.spot;
            return (
              <tr key={row.strike}>
                {renderOptionCells(row.call, isITMCall, S.callSide)}
                <td style={S.strikeCell}>{row.strike}</td>
                {renderOptionCells(row.put, isITMPut, S.putSide)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function renderOptionCells(opt: OC extends never ? never : any, isITM: boolean, sideStyle: React.CSSProperties) {
  const base = { ...S.td, ...sideStyle, ...(isITM ? S.itm : {}) };
  return (
    <>
      <td style={base}>{opt.bid.toFixed(2)}</td>
      <td style={base}>{opt.ask.toFixed(2)}</td>
      <td style={base}>{opt.last.toFixed(2)}</td>
      <td style={base}>{opt.volume}</td>
      <td style={base}>{opt.open_interest}</td>
      <td style={base}>{(opt.iv * 100).toFixed(1)}%</td>
      <td style={base}>{opt.delta.toFixed(3)}</td>
      <td style={base}>{opt.gamma.toFixed(4)}</td>
      <td style={base}>{opt.theta.toFixed(3)}</td>
      <td style={base}>{opt.vega.toFixed(3)}</td>
    </>
  );
}
