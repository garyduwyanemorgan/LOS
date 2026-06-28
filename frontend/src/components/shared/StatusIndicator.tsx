import React from 'react'
import { cn } from '@/lib/utils'
import type { StatusLevel } from '@/types'

interface StatusIndicatorProps {
  status: StatusLevel | string
  label?: string
  size?: 'sm' | 'md' | 'lg'
  pulse?: boolean
  className?: string
}

const DOT_SIZE: Record<string, string> = {
  sm: 'w-2 h-2',
  md: 'w-2.5 h-2.5',
  lg: 'w-3 h-3',
}

const DOT_COLOR: Record<string, string> = {
  healthy: 'bg-green-500',
  warning: 'bg-amber-400',
  critical: 'bg-red-500',
  unknown: 'bg-slate-400',
  online: 'bg-green-500',
  offline: 'bg-red-500',
  degraded: 'bg-amber-400',
}

const LABEL_COLOR: Record<string, string> = {
  healthy: 'text-green-700',
  warning: 'text-amber-700',
  critical: 'text-red-700',
  unknown: 'text-slate-500',
  online: 'text-green-700',
  offline: 'text-red-700',
  degraded: 'text-amber-700',
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  size = 'md',
  pulse = false,
  className,
}) => {
  const dotColor = DOT_COLOR[status] ?? 'bg-slate-400'
  const labelColor = LABEL_COLOR[status] ?? 'text-slate-600'
  const dotSize = DOT_SIZE[size]

  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className="relative flex">
        {pulse && (
          <span
            className={cn(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-60',
              dotColor
            )}
          />
        )}
        <span className={cn('relative inline-flex rounded-full', dotSize, dotColor)} />
      </span>
      {label && (
        <span
          className={cn(
            'font-medium capitalize',
            labelColor,
            size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-sm' : 'text-xs'
          )}
        >
          {label}
        </span>
      )}
    </span>
  )
}
