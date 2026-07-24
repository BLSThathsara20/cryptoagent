import React from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Agent from './pages/Agent';
import Insights from './pages/Insights';
import Issues from './pages/Issues';
import Settings from './pages/Settings';
import SystemStatusBar from './components/SystemStatusBar';
import AlertBell from './components/AlertBell';
import IssuesNavLink from './components/IssuesNavLink';

function NavBar() {
  const linkClass = ({ isActive }) =>
    `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive ? 'bg-accent-blue text-white' : 'text-gray-400 hover:text-white hover:bg-dark-700'
    }`;

  return (
    <nav className="bg-dark-800 border-b border-dark-600 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-xl font-bold bg-gradient-to-r from-accent-blue to-accent-green bg-clip-text text-transparent">
          CryptoAgent
        </span>
        <span className="text-xs text-gray-500 hidden sm:inline">AI Trading System</span>
      </div>
      <div className="flex gap-2 items-center">
        <NavLink to="/" className={linkClass} end>Dashboard</NavLink>
        <NavLink to="/agent" className={linkClass}>Agent</NavLink>
        <NavLink to="/insights" className={linkClass}>Insights</NavLink>
        <IssuesNavLink linkClass={linkClass} />
        <NavLink to="/settings" className={linkClass}>Settings</NavLink>
        <AlertBell />
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-dark-900">
        <NavBar />
        <SystemStatusBar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/issues" element={<Issues />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
