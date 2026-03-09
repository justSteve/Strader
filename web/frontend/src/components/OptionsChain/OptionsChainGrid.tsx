import { useMemo } from 'react';
import { useStore } from '../../store';
import type { OptionQuote } from '../../types';

function fmt(n: number | null, d = 2): string {
  return n != null ? n.toFixed(d) : '-';
}

function greekFmt(n: number | null): string {
  return n != null ? n.toFixed(4) : '-';
}

export default function OptionsChainGrid() {
  const chain = useStore(s => s.chain);
  const selectedExpiration = useStore(s => s.selectedExpiration);
  const setSelectedExpiration = useStore(s => s.setSelectedExpiration);

  const filteredData = useMemo(() => {
    if (!chain) return { calls: [], puts: [], strikes: [] };

    const exp = selectedExpiration || chain.expirations[0];
    const calls = chain.calls.filter(c => c.expiration === exp);
    const puts = chain.puts.filter(p => p.expiration === exp);
    const strikes = [...new Set([...calls.map(c => c.strike), ...puts.map(p => p.strike)])].sort((a, b) => a - b);

    return { calls, puts, strikes };
  }, [chain, selectedExpiration]);

  if (!chain) {
    return <div style={{ padding: '20px', color: 'var(--text-muted)' }}>Loading options chain...</div>;
  }

  const callMap = new Map<number, OptionQuote>();
  const putMap = new Map<number, OptionQuote>();
  filteredData.calls.forEach(c => callMap.set(c.strike, c));
  filteredData.puts.forEach(p => putMap.set(p.strike, p));

  return (
    <div className="panel" style={{ overflow: 'auto' }}>
      <div className="panel-header">
        <span>Options Chain</span>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>EXP:</span>
          <select
            value={selectedExpiration || chain.expirations[0] || ''}
            onChange={e => setSelectedExpiration(e.target.value)}
            style={{ width: '120px' }}
          >
            {chain.expirations.map(exp => (
              <option key={exp} value={exp}>{exp}</option>
            ))}
          </select>
          <span style={{ marginLeft: '12px', color: 'var(--text-muted)' }}>
            UND: <span style={{ color: 'var(--text-primary)' }}>{fmt(chain.underlying_price)}</span>
          </span>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th className="text-center" colSpan={7} style={{ color: 'var(--green)', borderRight: '2px solid var(--border)' }}>CALLS</th>
            <th className="text-center" style={{ color: 'var(--yellow)' }}>STRIKE</th>
            <th className="text-center" colSpan={7} style={{ color: 'var(--red)', borderLeft: '2px solid var(--border)' }}>PUTS</th>
          </tr>
          <tr>
            {/* Calls */}
            <th>IV</th>
            <th>Delta</th>
            <th>Vol</th>
            <th>OI</th>
            <th>Bid</th>
            <th>Ask</th>
            <th style={{ borderRight: '2px solid var(--border)' }}>Last</th>
            {/* Strike */}
            <th className="text-center" style={{ fontWeight: 'bold' }}>Strike</th>
            {/* Puts */}
            <th style={{ borderLeft: '2px solid var(--border)' }}>Last</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>OI</th>
            <th>Vol</th>
            <th>Delta</th>
            <th>IV</th>
          </tr>
        </thead>
        <tbody>
          {filteredData.strikes.map(strike => {
            const call = callMap.get(strike);
            const put = putMap.get(strike);
            const isATM = Math.abs(strike - chain.underlying_price) < 2.5;
            const callITM = call?.in_the_money;
            const putITM = put?.in_the_money;

            return (
              <tr key={strike} style={isATM ? { background: 'var(--bg-hover)', borderTop: '1px solid var(--blue)', borderBottom: '1px solid var(--blue)' } : undefined}>
                <td className={callITM ? 'itm' : ''}>{call ? fmt(call.iv, 1) : '-'}</td>
                <td className={callITM ? 'itm' : ''}>{call ? greekFmt(call.delta) : '-'}</td>
                <td className={callITM ? 'itm' : ''}>{call?.volume?.toLocaleString() || '-'}</td>
                <td className={callITM ? 'itm' : ''}>{call?.open_interest?.toLocaleString() || '-'}</td>
                <td className={callITM ? 'itm' : ''} style={{ color: 'var(--green)' }}>{call ? fmt(call.bid) : '-'}</td>
                <td className={callITM ? 'itm' : ''} style={{ color: 'var(--red)' }}>{call ? fmt(call.ask) : '-'}</td>
                <td className={callITM ? 'itm' : ''} style={{ borderRight: '2px solid var(--border)' }}>{call ? fmt(call.last) : '-'}</td>
                <td className="text-center" style={{ fontWeight: isATM ? 'bold' : 'normal', color: isATM ? 'var(--blue)' : 'var(--yellow)' }}>
                  {strike.toFixed(0)}
                </td>
                <td className={putITM ? 'itm' : ''} style={{ borderLeft: '2px solid var(--border)' }}>{put ? fmt(put.last) : '-'}</td>
                <td className={putITM ? 'itm' : ''} style={{ color: 'var(--green)' }}>{put ? fmt(put.bid) : '-'}</td>
                <td className={putITM ? 'itm' : ''} style={{ color: 'var(--red)' }}>{put ? fmt(put.ask) : '-'}</td>
                <td className={putITM ? 'itm' : ''}>{put?.open_interest?.toLocaleString() || '-'}</td>
                <td className={putITM ? 'itm' : ''}>{put?.volume?.toLocaleString() || '-'}</td>
                <td className={putITM ? 'itm' : ''}>{put ? greekFmt(put.delta) : '-'}</td>
                <td className={putITM ? 'itm' : ''}>{put ? fmt(put.iv, 1) : '-'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
