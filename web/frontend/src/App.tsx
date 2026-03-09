import { useStore } from './store';
import { useWebSocket } from './hooks/useWebSocket';
import { usePolling } from './hooks/usePolling';
import { useKeyboard } from './hooks/useKeyboard';
import MarketContextBar from './components/MarketContext/MarketContextBar';
import OptionsChainGrid from './components/OptionsChain/OptionsChainGrid';
import PositionDashboard from './components/PositionDashboard/PositionDashboard';
import TradeBuilder from './components/TradeBuilder/TradeBuilder';
import PnLChart from './components/PnLChart/PnLChart';
import RiskPanel from './components/RiskPanel/RiskPanel';

export default function App() {
  useWebSocket();
  usePolling(5000);
  useKeyboard();

  const activePanel = useStore(s => s.activePanel);
  const setActivePanel = useStore(s => s.setActivePanel);

  const renderMainPanel = () => {
    switch (activePanel) {
      case 'chain':
        return <OptionsChainGrid />;
      case 'positions':
        return <PositionDashboard />;
      case 'builder':
        return <TradeBuilder />;
      default:
        return <OptionsChainGrid />;
    }
  };

  return (
    <div className="app">
      <MarketContextBar />

      <div className="main-content">
        <div className="center-panels">
          {/* Main panel with tabs */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{
              display: 'flex', gap: '2px', padding: '2px 4px',
              background: 'var(--bg-primary)', borderBottom: '1px solid var(--border)',
            }}>
              <button
                className={`panel-tab ${activePanel === 'chain' ? 'active' : ''}`}
                onClick={() => setActivePanel('chain')}
              >
                Chain <span className="kbd">Alt+1</span>
              </button>
              <button
                className={`panel-tab ${activePanel === 'positions' ? 'active' : ''}`}
                onClick={() => setActivePanel('positions')}
              >
                Positions <span className="kbd">Alt+2</span>
              </button>
              <button
                className={`panel-tab ${activePanel === 'builder' ? 'active' : ''}`}
                onClick={() => setActivePanel('builder')}
              >
                Builder <span className="kbd">Alt+3</span>
              </button>
            </div>
            <div style={{ flex: 1, overflow: 'auto' }}>
              {renderMainPanel()}
            </div>
          </div>

          {/* Bottom panel: P&L Chart */}
          <PnLChart />
        </div>

        {/* Right sidebar: Risk Panel */}
        <div className="sidebar">
          <RiskPanel />
        </div>
      </div>
    </div>
  );
}
