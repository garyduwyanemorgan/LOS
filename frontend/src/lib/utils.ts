import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, formatDistanceToNow } from 'date-fns'
import type { PriorityLevel, StatusLevel, QualityFlag } from '@/types'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  return format(new Date(date), 'dd MMM yyyy HH:mm')
}

export function formatDateShort(date: string | Date): string {
  return format(new Date(date), 'dd MMM HH:mm')
}

export function formatRelative(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true })
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 0.75) return 'text-green-600'
  if (confidence >= 0.5) return 'text-amber-600'
  return 'text-red-600'
}

export function confidenceBg(confidence: number): string {
  if (confidence >= 0.75) return 'bg-green-100 text-green-800'
  if (confidence >= 0.5) return 'bg-amber-100 text-amber-800'
  return 'bg-red-100 text-red-800'
}

export function priorityColor(priority: PriorityLevel | string): string {
  const colors: Record<string, string> = {
    critical: 'text-red-600',
    high: 'text-orange-500',
    medium: 'text-amber-500',
    low: 'text-blue-500',
    background: 'text-slate-400',
  }
  return colors[priority] ?? 'text-slate-500'
}

export function priorityBg(priority: PriorityLevel | string): string {
  const colors: Record<string, string> = {
    critical: 'bg-red-100 text-red-800 border-red-200',
    high: 'bg-orange-100 text-orange-800 border-orange-200',
    medium: 'bg-amber-100 text-amber-800 border-amber-200',
    low: 'bg-blue-100 text-blue-800 border-blue-200',
    background: 'bg-slate-100 text-slate-600 border-slate-200',
  }
  return colors[priority] ?? 'bg-slate-100 text-slate-600 border-slate-200'
}

export function statusColor(status: StatusLevel | string): string {
  const colors: Record<string, string> = {
    healthy: 'text-green-600',
    warning: 'text-amber-500',
    critical: 'text-red-600',
    unknown: 'text-slate-400',
  }
  return colors[status] ?? 'text-slate-500'
}

export function statusBg(status: StatusLevel | string): string {
  const colors: Record<string, string> = {
    healthy: 'bg-green-100 text-green-800',
    warning: 'bg-amber-100 text-amber-800',
    critical: 'bg-red-100 text-red-800',
    unknown: 'bg-slate-100 text-slate-600',
  }
  return colors[status] ?? 'bg-slate-100 text-slate-600'
}

export function qualityFlagColor(flag: QualityFlag | string): string {
  const colors: Record<string, string> = {
    good: 'text-green-600',
    suspect: 'text-amber-500',
    bad: 'text-red-600',
    missing: 'text-slate-400',
  }
  return colors[flag] ?? 'text-slate-500'
}

export function formatValue(
  value: number | null | undefined,
  unit: string,
  precision: number = 2
): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(precision)} ${unit}`
}

export function formatPercent(value: number | null | undefined, precision: number = 1): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(precision)}%`
}

export function trendIcon(trend: 'improving' | 'stable' | 'deteriorating' | string): string {
  if (trend === 'improving') return '↑'
  if (trend === 'deteriorating') return '↓'
  return '→'
}

export function trendColor(trend: 'improving' | 'stable' | 'deteriorating' | string): string {
  if (trend === 'improving') return 'text-green-600'
  if (trend === 'deteriorating') return 'text-red-600'
  return 'text-slate-500'
}

export function healthScoreColor(score: number): string {
  if (score >= 75) return 'text-green-600'
  if (score >= 50) return 'text-amber-500'
  if (score >= 25) return 'text-orange-500'
  return 'text-red-600'
}

export function healthScoreBg(score: number): string {
  if (score >= 75) return '#16A34A'
  if (score >= 50) return '#D97706'
  if (score >= 25) return '#EA580C'
  return '#DC2626'
}

export function loopColor(loop: string): string {
  const colors: Record<string, string> = {
    HYDROLOGICAL: '#0891B2',
    CHEMICAL: '#7C3AED',
    ECOLOGICAL: '#16A34A',
    INFRASTRUCTURE: '#D97706',
  }
  return colors[loop] ?? '#64748B'
}

export function loopIcon(loop: string): string {
  const icons: Record<string, string> = {
    HYDROLOGICAL: '💧',
    CHEMICAL: '⚗️',
    ECOLOGICAL: '🌿',
    INFRASTRUCTURE: '⚙️',
  }
  return icons[loop] ?? '○'
}

export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 3) + '...'
}

export function groupBy<T>(arr: T[], key: keyof T): Record<string, T[]> {
  return arr.reduce(
    (groups, item) => {
      const groupKey = String(item[key])
      return {
        ...groups,
        [groupKey]: [...(groups[groupKey] ?? []), item],
      }
    },
    {} as Record<string, T[]>
  )
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
