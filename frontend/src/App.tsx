import React from 'react';
import { BrowserRouter as Router, Route, Routes, Link, useLocation } from 'react-router-dom';
import Chat from './pages/Chat';
import RunsIndex from './pages/RunsIndex';
import RunDetail from './pages/RunDetail';
import Incidents from './pages/Incidents';
import CostView from './pages/CostView';

function NavLink({ to, children }: { to: string, children: React.ReactNode }) {
  const location = useLocation();
  const isActive = location.pathname === to || (to !== '/' && to !== '/chat' && location.pathname.startsWith(to));
  
  return (
    <Link 
      to={to} 
      className={`px-3 py-1.5 text-[13px] font-medium transition-colors rounded-[2px] ${
        isActive 
          ? 'bg-[var(--color-ink)] text-[var(--color-paper)]' 
          : 'text-[var(--color-muted)] hover:text-[var(--color-ink)]'
      }`}
    >
      {children}
    </Link>
  );
}

function Layout() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="flex items-center justify-between border-b border-[var(--color-hairline)] bg-[var(--color-paper)] px-4 py-2 shrink-0">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2">
            <span className="font-serif text-[18px] text-[var(--color-ink)] leading-none tracking-tight">Glass Box</span>
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/chat">Active Chat</NavLink>
            <NavLink to="/">Runs Index</NavLink>
            <NavLink to="/incidents">Incidents</NavLink>
            <NavLink to="/cost">Cost</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4 text-[13px] text-[var(--color-muted)] font-mono">
          <span>{new Date().toISOString().split('T')[0]}</span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[var(--color-ink)]"></span>
            RECORDING
          </span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden bg-[var(--color-surface)] relative">
        <Routes>
          <Route path="/chat" element={<Chat />} />
          <Route path="/" element={<RunsIndex />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/cost" element={<CostView />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <Layout />
    </Router>
  );
}
