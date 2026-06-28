import React from 'react'
import type { ScientificLoopState } from '@/types'
import { loopColor, statusColor } from '@/lib/utils'

interface LoopInteractionDiagramProps {
  loops: ScientificLoopState[]
  height?: number
}

const LOOP_POSITIONS: Record<string, { x: number; y: number }> = {
  HYDROLOGICAL: { x: 50, y: 20 },
  CHEMICAL: { x: 80, y: 55 },
  ECOLOGICAL: { x: 50, y: 80 },
  INFRASTRUCTURE: { x: 20, y: 55 },
}

const INTERACTIONS = [
  { from: 'HYDROLOGICAL', to: 'CHEMICAL', label: 'Dilution / Flux' },
  { from: 'CHEMICAL', to: 'ECOLOGICAL', label: 'Nutrients' },
  { from: 'ECOLOGICAL', to: 'CHEMICAL', label: 'Oxygen / Decay' },
  { from: 'INFRASTRUCTURE', to: 'HYDROLOGICAL', label: 'Inflow Control' },
  { from: 'INFRASTRUCTURE', to: 'CHEMICAL', label: 'Aeration' },
  { from: 'HYDROLOGICAL', to: 'ECOLOGICAL', label: 'Residence Time' },
]

interface NodeProps {
  loop: ScientificLoopState
  position: { x: number; y: number }
}

const LoopNode: React.FC<NodeProps> = ({ loop, position }) => {
  const color = loopColor(loop.loop)
  const statusCls = statusColor(loop.status)
  const icons: Record<string, string> = {
    HYDROLOGICAL: '💧',
    CHEMICAL: '⚗',
    ECOLOGICAL: '🌿',
    INFRASTRUCTURE: '⚙',
  }

  return (
    <g transform={`translate(${position.x}%, ${position.y}%)`}>
      <foreignObject x="-50" y="-38" width="100" height="76">
        <div
          className="flex flex-col items-center justify-center rounded-lg border-2 text-center"
          style={{
            borderColor: color,
            background: `${color}18`,
            width: 100,
            height: 76,
            padding: '4px',
          }}
        >
          <span className="text-lg">{icons[loop.loop]}</span>
          <span
            className="text-xs font-semibold mt-0.5"
            style={{ color, fontSize: '9px', lineHeight: 1.2 }}
          >
            {loop.loop.replace('LOGICAL', '').replace('TURE', 'TRE')}
          </span>
          <span className={`text-xs font-bold ${statusCls}`} style={{ fontSize: '10px' }}>
            {Math.round(loop.confidence * 100)}%
          </span>
          <span className="text-xs" style={{ fontSize: '8px', color: '#64748B' }}>
            {loop.status}
          </span>
        </div>
      </foreignObject>
    </g>
  )
}

export const LoopInteractionDiagram: React.FC<LoopInteractionDiagramProps> = ({
  loops,
  height = 320,
}) => {
  const loopMap = new Map(loops.map((l) => [l.loop, l]))

  return (
    <div className="relative" style={{ height }}>
      <svg
        width="100%"
        height="100%"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0"
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth="6"
            markerHeight="4"
            refX="6"
            refY="2"
            orient="auto"
          >
            <polygon points="0 0, 6 2, 0 4" fill="#94A3B8" />
          </marker>
        </defs>

        {INTERACTIONS.map((interaction, i) => {
          const from = LOOP_POSITIONS[interaction.from]
          const to = LOOP_POSITIONS[interaction.to]
          if (!from || !to) return null

          const mx = (from.x + to.x) / 2
          const my = (from.y + to.y) / 2

          return (
            <g key={i}>
              <line
                x1={`${from.x}%`}
                y1={`${from.y}%`}
                x2={`${to.x}%`}
                y2={`${to.y}%`}
                stroke="#CBD5E1"
                strokeWidth="0.5"
                markerEnd="url(#arrowhead)"
                strokeDasharray="2,1"
              />
              <text
                x={`${mx}%`}
                y={`${my}%`}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="2.8"
                fill="#94A3B8"
              >
                {interaction.label}
              </text>
            </g>
          )
        })}
      </svg>

      {loops.map((loop) => {
        const pos = LOOP_POSITIONS[loop.loop]
        if (!pos) return null
        return (
          <div
            key={loop.loop}
            className="absolute"
            style={{
              left: `${pos.x}%`,
              top: `${pos.y}%`,
              transform: 'translate(-50%, -50%)',
            }}
          >
            <div
              className="flex flex-col items-center justify-center rounded-xl border-2 text-center shadow-sm"
              style={{
                borderColor: loopColor(loop.loop),
                background: `${loopColor(loop.loop)}18`,
                width: 90,
                height: 70,
                padding: '6px',
              }}
            >
              <span className="text-base">
                {loop.loop === 'HYDROLOGICAL'
                  ? '💧'
                  : loop.loop === 'CHEMICAL'
                    ? '⚗'
                    : loop.loop === 'ECOLOGICAL'
                      ? '🌿'
                      : '⚙'}
              </span>
              <span
                className="font-semibold mt-0.5"
                style={{ color: loopColor(loop.loop), fontSize: '9px', lineHeight: 1.2 }}
              >
                {loop.loop === 'HYDROLOGICAL'
                  ? 'HYDRO'
                  : loop.loop === 'INFRASTRUCTURE'
                    ? 'INFRA'
                    : loop.loop}
              </span>
              <span
                className={`font-bold ${statusColor(loop.status)}`}
                style={{ fontSize: '11px' }}
              >
                {Math.round(loop.confidence * 100)}%
              </span>
              <span style={{ fontSize: '8px', color: '#64748B' }}>{loop.status}</span>
            </div>
          </div>
        )
      })}

      {loops.length === 0 && (
        <div className="flex items-center justify-center h-full text-slate-400 text-sm">
          No loop data available
        </div>
      )}
    </div>
  )
}
