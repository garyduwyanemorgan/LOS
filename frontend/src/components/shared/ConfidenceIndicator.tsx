import React from 'react'
import { cn, confidenceBg } from '@/lib/utils'

interface ConfidenceIndicatorProps {
  confidence: number // 0-1
  showLabel?: boolean
  showValue?: boolean
  size?: 'sm' | 'md'
  className?: string
}

export const ConfidenceIndicator: React.FC<ConfidenceIndicatorProps> = ({
  confidence,
  showLabel = true,
  showValue,
  size = 'sm',
  className,
}) => {
  const effectiveShowLabel = showValue !== undefined ? showValue : showLabel
  const pct = Math.round(confidence * 100)
  const bgClass = confidenceBg(confidence)

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        bgClass,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
        className
      )}
    >
      {effectiveShowLabel ? `${pct}% conf.` : `${pct}%`}
    </span>
  )
}
