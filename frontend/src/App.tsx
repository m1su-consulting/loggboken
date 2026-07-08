import { useState } from 'react'
import './App.css'
import { EnvironmentDiff } from './components/EnvironmentDiff'
import { InstallationsTable } from './components/InstallationsTable'
import { Logo } from './components/Logo'

type Tab = 'installations' | 'diff'

function App() {
  const [tab, setTab] = useState<Tab>('installations')

  return (
    <>
      <div className="watermark" aria-hidden="true" />
      <header className="site-header">
        <div className="site-header-inner">
          <Logo size={44} />
          <div className="site-header-text">
            <h1>Loggboken</h1>
            <p className="subtitle">Vet var varje artefakt är installerad.</p>
          </div>
          <div className="site-header-spacer" aria-hidden="true" />
        </div>
        <svg
          className="header-wave"
          viewBox="0 0 1440 60"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d="M0,32 C240,60 480,0 720,20 C960,40 1200,10 1440,28 L1440,60 L0,60 Z" />
        </svg>
      </header>
      <div className="page">
        <nav className="tabs">
          <button
            type="button"
            className={tab === 'installations' ? 'tab active' : 'tab'}
            onClick={() => setTab('installations')}
          >
            Installationer
          </button>
          <button
            type="button"
            className={tab === 'diff' ? 'tab active' : 'tab'}
            onClick={() => setTab('diff')}
          >
            Jämför miljöer
          </button>
        </nav>
        <main>{tab === 'installations' ? <InstallationsTable /> : <EnvironmentDiff />}</main>
      </div>
    </>
  )
}

export default App
