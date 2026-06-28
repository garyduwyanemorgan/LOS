import React from 'react'
import type { ScientificLoopState } from '@/types'
import { cn, loopColor, statusBg, formatRelative } from '@/lib/utils'
import { StatusIndicator } from './StatusIndicator'
import { ConfidenceIndicator } from './ConfidenceIndicator'

interface ScientificLoopStatusProps {
  loops: ScientificLoopState[]
  compact?: boolean
  className?: string
}

const LOOP_META: Record<string, { label: string; icon: string; description: string }> = {
  HYDROLOGICAL: {
    label: 'Hydrology',
    icon: '💧',
    description: 'Water balance, level & flow',
  },
  CHEMICAL: {
    label: 'Chemistry',
    icon: '⚗',
    description: 'Nutrients, redox & DO',
  },
  ECOLOGICAL: {
    label: 'Ecology',
    icon: '🌿',
    description: 'Bloom risk & community',
  },
  INFRASTRUCTURE: {
    label: 'Infrastructure',
    icon: '⚙',
    description: 'Aeration, pumps & sensors',
  },
}

interface LoopCardProps {
  loop: ScientificLoopState
  compact: boolean
}

const LoopCard: React.FC<LoopCardProps> = ({ loop, compact }) => {
  const meta = LOOP_META[loop.loop] ?? { label: loop.loop, icon: '○', description: '' }
  const borderColor = loopColor(loop.loop)

  return (
    <div
      className="flex flex-col bg-white rounded-lg border-l-4 p-3 shadow-sm"
      style={{ borderLeftColor: borderColor }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className={compact ? 'text-base' : 'text-lg'}>{meta.icon}</span>
          <span className="font-semibold text-slate-800 text-sm">{meta.label}</span>
        </div>
        <StatusIndicator status={loop.status} pulse={loop.status === 'critical'} />
      </div>

      {!compact && (
        <p className="text-xs text-slate-400 mb-2">{meta.description}</p>
      )}

      <div className="flex items-center justify-between">
        <ConfidenceIndicator confidence={loop.confidence} />
        {!compact && (
          <span className="text-xs text-slate-400">
            {formatRelative(loop.last_updated)}
          </span>
        )}
      </div>
    </div>
  )
}

export const ScientificLoopStatus: React.FC<ScientificLoopStatusProps> = ({
  loops,
  compact = false,
  className,
}) => {
  const orderedLoops = ['HYDROLOGICAL', 'CHEMICAL', 'ECOLOGICAL', 'INFRASTRUCTURE']
    .map((name) => loops.find((l) => l.loop === name))
    .filter((l): l is ScientificLoopState => l !== undefined)

  // Fill missing loops with unknown state
  const fullLoops: ScientificLoopState[] = orderedLoops.length === 4
    ? orderedLoops
    : (['HYDROLOGICAL', 'CHEMICAL', 'ECOLOGICAL', 'INFRASTRUCTURE'] as const).map(
        (name) =>
          loops.find((l) => l.loop === name) ?? {
            loop: name,
            status: 'unknown' as const,
            confidence: 0,
            last_updated: new Date().toISOString(),
            state: {},
          }
      )

  return (
    <div className={cn('grid grid-cols-2 gap-3 lg:grid-cols-4', className)}>
      {fullLoops.map((loop) => (
        <LoopCard key={loop.loop} loop={loop} compact={compact} />
      ))}
    </div>
  )
}
