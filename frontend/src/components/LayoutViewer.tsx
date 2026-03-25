import { useCallback, useRef, useState } from 'react'
import type { LayoutData, LayoutPage } from '../types'

// ---------------------------------------------------------------------------
// SVG colour constants (inline — Tailwind classes don't apply to SVG attrs)
// ---------------------------------------------------------------------------

const C = {
  pageBg:       '#ffffff',
  blockBorder:  '#475569',   // slate-600
  textUnchanged:'#94a3b8',   // slate-400
  textChanged:  '#d97706',   // amber-600 (readable on white)
  rectChanged:  'rgba(253,230,138,0.25)',  // amber-200 25%
  hyphenBar:    '#f59e0b',   // amber-500
} as const

// ---------------------------------------------------------------------------
// PageSVG — renders one page in one SVG, for one side (ocr | corrected)
// ---------------------------------------------------------------------------

interface PageSVGProps {
  page: LayoutPage
  side: 'ocr' | 'corrected'
}

function PageSVG({ page, side }: PageSVGProps) {
  const { page_width: W, page_height: H, blocks } = page

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      preserveAspectRatio="xMinYMin meet"
      style={{ display: 'block' }}
    >
      {/* Page background */}
      <rect x={0} y={0} width={W} height={H} fill={C.pageBg} />

      {blocks.map((block) => (
        <g key={block.block_id}>
          {/* Block outline */}
          <rect
            x={block.hpos}
            y={block.vpos}
            width={block.width}
            height={block.height}
            fill="none"
            stroke={C.blockBorder}
            strokeWidth={6}
          />

          {block.lines.map((line) => {
            const displayText = side === 'ocr' ? line.ocr_text : line.corrected_text
            const fontSize = Math.max(line.height * 0.7, 1)
            const textY = line.vpos + line.height * 0.75
            const textX = line.hpos + 4
            const maxW = line.width - 8
            const hasHyphen = line.hyphen_role !== 'none'

            return (
              <g key={line.line_id}>
                {/* Modified line background */}
                {line.modified && (
                  <rect
                    x={line.hpos}
                    y={line.vpos}
                    width={line.width}
                    height={line.height}
                    fill={C.rectChanged}
                  />
                )}

                {/* Hyphen left border (2px amber bar) */}
                {hasHyphen && (
                  <rect
                    x={line.hpos}
                    y={line.vpos}
                    width={8}
                    height={line.height}
                    fill={C.hyphenBar}
                  />
                )}

                {/* Line text */}
                <text
                  x={textX}
                  y={textY}
                  fontSize={fontSize}
                  fill={line.modified ? C.textChanged : C.textUnchanged}
                  textLength={maxW > 0 ? maxW : undefined}
                  lengthAdjust="spacingAndGlyphs"
                  style={{ fontFamily: 'serif' }}
                >
                  {displayText}
                </text>
              </g>
            )
          })}
        </g>
      ))}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// LayoutViewer
// ---------------------------------------------------------------------------

interface LayoutViewerProps {
  data: LayoutData
}

export function LayoutViewer({ data }: LayoutViewerProps) {
  const [pageIdx, setPageIdx] = useState(0)
  const leftRef  = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const syncing  = useRef(false)

  const currentPage = data.pages[pageIdx] ?? data.pages[0]

  const onScrollLeft = useCallback(() => {
    if (syncing.current || !leftRef.current || !rightRef.current) return
    syncing.current = true
    rightRef.current.scrollTop = leftRef.current.scrollTop
    syncing.current = false
  }, [])

  const onScrollRight = useCallback(() => {
    if (syncing.current || !leftRef.current || !rightRef.current) return
    syncing.current = true
    leftRef.current.scrollTop = rightRef.current.scrollTop
    syncing.current = false
  }, [])

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-800/40 overflow-hidden">

      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700/60 flex items-center justify-between gap-4 flex-wrap">
        <h3 className="font-serif text-sm font-semibold text-slate-200">
          Visionneuse structurelle
        </h3>
        {data.pages.length > 1 && (
          <select
            value={pageIdx}
            onChange={(e) => setPageIdx(Number(e.target.value))}
            className="font-mono text-xs bg-slate-700 border border-slate-600 text-slate-200
                       rounded px-2 py-1 focus:outline-none focus:border-amber-500"
          >
            {data.pages.map((p, i) => (
              <option key={p.page_id} value={i}>
                Page {i + 1} — {p.page_id}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Panel column headers */}
      <div className="grid grid-cols-2 border-b border-slate-700/40 bg-slate-800/60">
        <div className="px-3 py-1.5 font-mono text-[10px] text-slate-500 uppercase tracking-wider
                        border-r border-slate-700/40">
          OCR source
        </div>
        <div className="px-3 py-1.5 font-mono text-[10px] text-slate-500 uppercase tracking-wider">
          Corrigé
        </div>
      </div>

      {/* Dual SVG panels with synchronised scroll */}
      <div className="grid grid-cols-2 divide-x divide-slate-700/40">
        <div
          ref={leftRef}
          onScroll={onScrollLeft}
          className="overflow-auto max-h-[60vh]"
        >
          <PageSVG page={currentPage} side="ocr" />
        </div>
        <div
          ref={rightRef}
          onScroll={onScrollRight}
          className="overflow-auto max-h-[60vh]"
        >
          <PageSVG page={currentPage} side="corrected" />
        </div>
      </div>

      {/* Legend */}
      <div className="px-4 py-2.5 border-t border-slate-700/40 flex items-center gap-6 flex-wrap">
        <span className="font-mono text-[10px] text-slate-600 uppercase tracking-wider mr-1">
          Légende :
        </span>
        <div className="flex items-center gap-1.5">
          <div
            className="w-4 h-3 rounded-sm border border-amber-400/40"
            style={{ background: 'rgba(253,230,138,0.25)' }}
          />
          <span className="font-mono text-[10px] text-slate-500">ligne modifiée</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-3 rounded-sm" style={{ background: '#f59e0b' }} />
          <span className="font-mono text-[10px] text-slate-500">césure</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-3 rounded-sm border border-slate-600/60" />
          <span className="font-mono text-[10px] text-slate-500">ligne inchangée</span>
        </div>
      </div>
    </div>
  )
}
