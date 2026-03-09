import { useState, type ReactNode } from 'react';

const S: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column' as const, height: '100vh', background: '#0a0a0f', color: '#e0e0e0' },
  nav: { display: 'flex', gap: 2, padding: '0 12px', background: '#0d0d14', borderBottom: '1px solid #1e1e2e' },
  tab: { padding: '10px 16px', cursor: 'pointer', fontSize: 12, color: '#666', borderBottom: '2px solid transparent', transition: 'all 0.2s' },
  tabActive: { padding: '10px 16px', cursor: 'pointer', fontSize: 12, color: '#e0e0e0', borderBottom: '2px solid #7c4dff', fontWeight: 600 },
  content: { flex: 1, overflow: 'auto' },
};

interface Tab {
  id: string;
  label: string;
  shortcut: string;
  component: ReactNode;
}

interface LayoutProps {
  tabs: Tab[];
  topBar: ReactNode;
}

export function Layout({ tabs, topBar }: LayoutProps) {
  const [activeTab, setActiveTab] = useState(tabs[0]?.id ?? '');

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    const idx = tabs.findIndex((t) => t.id === activeTab);
    if (e.key === 'ArrowRight' || e.key === 'l') {
      setActiveTab(tabs[(idx + 1) % tabs.length].id);
    } else if (e.key === 'ArrowLeft' || e.key === 'h') {
      setActiveTab(tabs[(idx - 1 + tabs.length) % tabs.length].id);
    } else {
      const tab = tabs.find((t) => t.shortcut === e.key);
      if (tab) setActiveTab(tab.id);
    }
  };

  const active = tabs.find((t) => t.id === activeTab);

  return (
    <div style={S.container} tabIndex={0} onKeyDown={handleKeyDown}>
      {topBar}
      <div style={S.nav}>
        {tabs.map((tab) => (
          <div
            key={tab.id}
            style={tab.id === activeTab ? S.tabActive : S.tab}
            onClick={() => setActiveTab(tab.id)}
          >
            <span style={{ color: '#555', marginRight: 4, fontSize: 10 }}>{tab.shortcut}</span>
            {tab.label}
          </div>
        ))}
      </div>
      <div style={S.content}>{active?.component}</div>
    </div>
  );
}
