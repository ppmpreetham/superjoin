import { useEffect, useState } from 'react'
import './App.css'
import GraphView from './GraphView.jsx'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const KIND_COLORS = {
  corroborates: '#4A9E5C',
  contradicts: '#D71921',
  reconciles: '#D4A843',
}

function FactCard({ fact }) {
  if (!fact) return null
  return (
    <div className="fact-card">
      <div className="fact-meta mono-caps">
        <span>{fact.doc_id?.slice(0, 32)}</span>
        <span>P.{fact.page}</span>
        <span>{fact.type?.toUpperCase()}</span>
        <span className="fact-conf">{Math.round((fact.confidence ?? 0) * 100)}%</span>
      </div>
      <p className="claim">{fact.claim}</p>
      <div className="fact-value-row">
        {fact.value && (
          <span className="fact-value">
            {fact.value} <i className="mono-caps unit">{fact.unit}</i>
          </span>
        )}
      </div>
      <blockquote>“{fact.quote}”</blockquote>
    </div>
  )
}

function RelCard({ rel }) {
  const color = KIND_COLORS[rel.kind]
  return (
    <div className="rel-card">
      <div className="rel-head">
        <span className="rel-kind mono-caps" style={{ color }}>
          [{rel.kind.toUpperCase()}]
        </span>
        <span className="mono-caps rel-src">{rel.source}</span>
      </div>
      <div className="rel-facts">
        <FactCard fact={rel.fact_a} />
        <FactCard fact={rel.fact_b} />
      </div>
      <p className="explanation">{rel.explanation}</p>
    </div>
  )
}

function App() {
  const [tab, setTab] = useState('showcase')
  const [health, setHealth] = useState(null)
  const [docs, setDocs] = useState([])
  const [facts, setFacts] = useState([])
  const [rels, setRels] = useState([])
  const [showcase, setShowcase] = useState(null)
  const [relFilter, setRelFilter] = useState('all')
  const [docFilter, setDocFilter] = useState('all')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)

  const loadAll = async () => {
    const [h, d, f, r, s] = await Promise.all([
      fetch(`${API}/api/health`).then((r) => r.json()),
      fetch(`${API}/api/documents`).then((r) => r.json()),
      fetch(`${API}/api/facts`).then((r) => r.json()),
      fetch(`${API}/api/relationships`).then((r) => r.json()),
      fetch(`${API}/api/showcase`).then((r) => r.json()),
    ])
    setHealth(h)
    setDocs(d)
    setFacts(f)
    setRels(r)
    setShowcase(s)
  }

  useEffect(() => {
    loadAll().catch((e) => setUploadMsg({ err: String(e) }))
  }, [])

  const onUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg({ info: '[PROCESSING] EXTRACTION + CROSS-DOC COMPARISON' })
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(`${API}/api/upload`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error(await res.text())
      const out = await res.json()
      setUploadMsg({
        ok: `[OK] ${out.num_pages}P → ${out.facts_extracted} FACTS (${out.extraction_mode.toUpperCase()}) → ${out.relationships_found} RELS`,
      })
      await loadAll()
      setTab('facts')
    } catch (err) {
      setUploadMsg({ err: `[ERROR] ${err.message}` })
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const filteredRels = rels.filter(
    (r) =>
      (relFilter === 'all' || r.kind === relFilter) &&
      (docFilter === 'all' ||
        r.fact_a?.doc_id === docFilter ||
        r.fact_b?.doc_id === docFilter),
  )
  const filteredFacts =
    docFilter === 'all' ? facts : facts.filter((f) => f.doc_id === docFilter)

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>FACT KNOWLEDGE LAYER</h1>
          <span className="mono-caps sub">GROUND · LINK · RECONCILE</span>
        </div>
        <div className="status mono-caps">
          <span className="stat">
            LLM <b className={health?.llm_provider !== 'none' ? 'ok' : 'dim'}>{health?.llm_provider?.toUpperCase() ?? '…'}</b>
          </span>
          <span className="stat">DOCS <b>{docs.length}</b></span>
          <span className="stat">FACTS <b>{facts.length}</b></span>
          <span className="stat">RELS <b>{rels.length}</b></span>
        </div>
      </header>

      <div className="upload-bar">
        <label className={`btn-primary mono-caps ${uploading ? 'disabled' : ''}`}>
          <input type="file" accept="application/pdf" onChange={onUpload} disabled={uploading} />
          {uploading ? '[PROCESSING…]' : 'UPLOAD PDF'}
        </label>
        <select
          className="select mono-caps"
          value={docFilter}
          onChange={(e) => setDocFilter(e.target.value)}
        >
          <option value="all">ALL DOCUMENTS</option>
          {docs.map((d) => (
            <option key={d.doc_id} value={d.doc_id}>
              {d.name} ({d.fact_count})
            </option>
          ))}
        </select>
        {uploadMsg && (
          <span className={`msg mono-caps ${uploadMsg.err ? 'err' : uploadMsg.ok ? 'ok' : 'dim'}`}>
            {uploadMsg.err || uploadMsg.ok || uploadMsg.info}
          </span>
        )}
      </div>

      <nav className="mono-caps">
        {[
          ['showcase', 'SHOWCASE'],
          ['facts', 'FACTS'],
          ['relationships', 'RELS'],
          ['graph', 'GRAPH'],
          ['docs', 'DOCS'],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`tab ${tab === id ? 'active' : ''}`}
            onClick={() => setTab(id)}
          >
            {tab === id ? `[ ${label} ]` : label}
          </button>
        ))}
      </nav>

      {tab === 'showcase' && showcase && (
        <main>
          <p className="intro">
            THE FOUR REQUIRED CASES, RESOLVED LIVE AGAINST THE KNOWLEDGE BASE. EVERY
            CLAIM CARRIES ITS VERBATIM SOURCE QUOTE AND PAGE.
          </p>
          {showcase.cases.map((c) => (
            <section key={c.case} className="case">
              <h2>
                <span className="case-num">C{c.case}</span>
                {c.title}
              </h2>
              <p className="narrative">{c.narrative}</p>
              {c.relationship && <RelCard rel={c.relationship} />}
            </section>
          ))}
          {showcase.failures?.length > 0 && (
            <section className="case">
              <h2>
                <span className="case-num case-num-red">!</span>FAILURE LOG
              </h2>
              {showcase.failures.map((f, i) => (
                <div key={i} className="failure">
                  <span className="mono-caps dim">{f.stage.toUpperCase()}</span>
                  <p>{f.detail}</p>
                </div>
              ))}
            </section>
          )}
        </main>
      )}

      {tab === 'facts' && (
        <main>
          <div className="grid">
            {filteredFacts.map((f) => (
              <FactCard key={f.fact_id} fact={f} />
            ))}
          </div>
          {filteredFacts.length === 0 && (
            <div className="empty-state">
              <p className="empty-head">NO FACTS</p>
              <p className="empty-sub">Upload a PDF to extract grounded facts.</p>
            </div>
          )}
        </main>
      )}

      {tab === 'relationships' && (
        <main>
          <div className="filter-bar">
            {['all', 'corroborates', 'contradicts', 'reconciles'].map((k) => (
              <button
                key={k}
                className={`chip mono-caps ${relFilter === k ? 'on' : ''}`}
                onClick={() => setRelFilter(k)}
              >
                {k.toUpperCase()}{' '}
                <span className="chip-count">
                  {k === 'all' ? rels.length : rels.filter((r) => r.kind === k).length}
                </span>
              </button>
            ))}
          </div>
          {filteredRels.map((r) => (
            <RelCard key={r.rel_id} rel={r} />
          ))}
        </main>
      )}

      {tab === 'graph' && <GraphView facts={facts} rels={rels} />}

      {tab === 'docs' && (
        <main>
          <table className="docs-table">
            <thead>
              <tr>
                <th className="mono-caps">DOCUMENT</th>
                <th className="mono-caps">PAGES</th>
                <th className="mono-caps">FACTS</th>
                <th className="mono-caps">ADDED</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.doc_id}>
                  <td>{d.name}</td>
                  <td className="mono">{d.num_pages ?? '—'}</td>
                  <td className="mono">{d.fact_count}</td>
                  <td className="mono">{d.uploaded_at?.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </main>
      )}

      <footer className="mono-caps dim">
        FACT KNOWLEDGE LAYER · SQLITE · PYMUPDF · SENTENCE-TRANSFORMERS · LLM-OPTIONAL
      </footer>
    </div>
  )
}

export default App
