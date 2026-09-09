import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const KIND_COLORS = {
  corroborates: '#4A9E5C',
  contradicts: '#D71921',
  reconciles: '#D4A843',
}

function GraphView({ facts, rels }) {
  const fgRef = useRef(null)
  const wrapRef = useRef(null)
  const [width, setWidth] = useState(900)
  const [height, setHeight] = useState(560)
  const [kindFilter, setKindFilter] = useState('all')
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      setWidth(el.clientWidth)
      setHeight(Math.max(480, Math.min(640, window.innerHeight - 260)))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { graphData, nodeById } = useMemo(() => {
    const visible = rels.filter((r) => kindFilter === 'all' || r.kind === kindFilter)
    const nodeById = new Map()
    const links = []
    for (const r of visible) {
      if (!r.fact_a || !r.fact_b) continue
      for (const f of [r.fact_a, r.fact_b]) {
        if (!nodeById.has(f.fact_id)) {
          nodeById.set(f.fact_id, {
            id: f.fact_id,
            doc: f.doc_id,
            page: f.page,
            claim: f.claim,
            quote: f.quote,
          })
        }
      }
      links.push({
        source: r.fact_a.fact_id,
        target: r.fact_b.fact_id,
        kind: r.kind,
        explanation: r.explanation,
      })
    }
    return {
      graphData: { nodes: [...nodeById.values()], links },
      nodeById,
    }
  }, [rels, kindFilter])

  useEffect(() => {
    const fg = fgRef.current
    if (!fg || !graphData.nodes.length) return
    fg.d3Force('charge').strength(-140)
    const t = setTimeout(() => fg.zoomToFit(600, 40), 900)
    return () => clearTimeout(t)
  }, [graphData])

  const docs = useMemo(
    () => [...new Set([...nodeById.values()].map((n) => n.doc))],
    [nodeById],
  )

  const paintNode = (node, ctx, globalScale) => {
    const isSel = selected?.id === node.id
    const deg = node.degree || 1
    const r = 3 + Math.min(deg, 8) * 1.2
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false)
    ctx.fillStyle = isSel ? '#FFFFFF' : '#E8E8E8'
    ctx.fill()
    if (isSel) {
      ctx.strokeStyle = '#D71921'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
    const label = `${node.doc.slice(0, 14)}·p${node.page}`
    ctx.font = `${5.5 / globalScale}px 'Space Mono', monospace`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = isSel ? '#FFFFFF' : '#666666'
    ctx.fillText(label, node.x, node.y + r + 2)
  }

  const handleClick = (node) => {
    setSelected(selected?.id === node.id ? null : node)
    const fg = fgRef.current
    if (node && fg) {
      const dist = 140
      const dim = dist * 2
      fg.centerAt(node.x, node.y, 600)
      fg.zoom(dim / width < 2.5 ? 2.5 : dim / width, 600)
    }
  }

  return (
    <div ref={wrapRef} className="graph-wrap">
      <div className="graph-toolbar">
        <div className="graph-chips">
          {['all', 'corroborates', 'contradicts', 'reconciles'].map((k) => (
            <button
              key={k}
              className={`chip mono-caps ${kindFilter === k ? 'on' : ''}`}
              onClick={() => {
                setKindFilter(k)
                setSelected(null)
              }}
            >
              {k === 'all' ? 'ALL' : KIND_COLORS[k] ? k.toUpperCase() : k.toUpperCase()}
              <span className="chip-count">
                {' '}
                {k === 'all' ? rels.length : rels.filter((r) => r.kind === k).length}
              </span>
            </button>
          ))}
        </div>
        <span className="graph-meta mono-caps">
          {graphData.nodes.length} FACTS · {graphData.links.length} LINKS
        </span>
      </div>

      {graphData.nodes.length === 0 ? (
        <div className="graph-empty">
          <p className="empty-head">NO RELATIONSHIPS</p>
          <p className="empty-sub">Upload documents to build the knowledge graph.</p>
        </div>
      ) : (
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={width}
          height={height}
          backgroundColor="#000000"
          nodeRelSize={3}
          nodeCanvasObject={paintNode}
          onNodeClick={handleClick}
          linkColor={(l) => KIND_COLORS[l.kind] || '#333333'}
          linkWidth={(l) => (selected && (l.source.id === selected.id || l.target.id === selected.id) ? 1.6 : 0.6)}
          linkOpacity={0.55}
          cooldownTicks={120}
          d3AlphaDecay={0.03}
        />
      )}

      {selected && (
        <div className="graph-detail">
          <div className="graph-detail-head">
            <span className="mono-caps label-sec">
              {selected.doc.slice(0, 44)} · PAGE {selected.page}
            </span>
            <button className="ghost-btn mono-caps" onClick={() => setSelected(null)}>
              [ X ]
            </button>
          </div>
          <p className="graph-claim">{selected.claim || selected.quote}</p>
          <blockquote>“{selected.quote}”</blockquote>
        </div>
      )}

      <div className="graph-legend">
        <span className="mono-caps legend-item">
          <i style={{ background: KIND_COLORS.corroborates }} /> CORROBORATES
        </span>
        <span className="mono-caps legend-item">
          <i style={{ background: KIND_COLORS.contradicts }} /> CONTRADICTS
        </span>
        <span className="mono-caps legend-item">
          <i style={{ background: KIND_COLORS.reconciles }} /> RECONCILES
        </span>
      </div>
    </div>
  )
}

export default GraphView
