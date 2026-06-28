import { describe, it, expect } from 'vitest'
import {
  cn,
  confidenceColor,
  confidenceBg,
  priorityColor,
  priorityBg,
  statusColor,
  statusBg,
  formatValue,
  formatPercent,
  trendIcon,
  trendColor,
  healthScoreColor,
  healthScoreBg,
  loopColor,
  loopIcon,
  truncate,
  groupBy,
} from './utils'

describe('cn', () => {
  it('merges class strings', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('deduplicates tailwind classes — last wins', () => {
    const result = cn('text-red-500', 'text-blue-500')
    expect(result).toBe('text-blue-500')
  })

  it('ignores falsy values', () => {
    expect(cn('a', false && 'b', undefined, null as unknown as string, 'c')).toBe('a c')
  })
})

describe('confidenceColor', () => {
  it('returns green for high confidence', () => {
    expect(confidenceColor(0.9)).toBe('text-green-600')
    expect(confidenceColor(0.75)).toBe('text-green-600')
  })

  it('returns amber for medium confidence', () => {
    expect(confidenceColor(0.6)).toBe('text-amber-600')
    expect(confidenceColor(0.5)).toBe('text-amber-600')
  })

  it('returns red for low confidence', () => {
    expect(confidenceColor(0.3)).toBe('text-red-600')
    expect(confidenceColor(0.0)).toBe('text-red-600')
  })
})

describe('confidenceBg', () => {
  it('returns green bg for high confidence', () => {
    expect(confidenceBg(0.8)).toContain('green')
  })

  it('returns amber bg for medium confidence', () => {
    expect(confidenceBg(0.6)).toContain('amber')
  })

  it('returns red bg for low confidence', () => {
    expect(confidenceBg(0.2)).toContain('red')
  })
})

describe('priorityColor', () => {
  it('maps all priority levels', () => {
    expect(priorityColor('critical')).toBe('text-red-600')
    expect(priorityColor('high')).toBe('text-orange-500')
    expect(priorityColor('medium')).toBe('text-amber-500')
    expect(priorityColor('low')).toBe('text-blue-500')
    expect(priorityColor('background')).toBe('text-slate-400')
  })

  it('returns fallback for unknown priority', () => {
    expect(priorityColor('unknown-level')).toBe('text-slate-500')
  })
})

describe('priorityBg', () => {
  it('returns bg classes for all priorities', () => {
    expect(priorityBg('critical')).toContain('red')
    expect(priorityBg('high')).toContain('orange')
    expect(priorityBg('medium')).toContain('amber')
    expect(priorityBg('low')).toContain('blue')
  })
})

describe('statusColor', () => {
  it('maps status levels to text colors', () => {
    expect(statusColor('healthy')).toBe('text-green-600')
    expect(statusColor('warning')).toBe('text-amber-500')
    expect(statusColor('critical')).toBe('text-red-600')
    expect(statusColor('unknown')).toBe('text-slate-400')
  })
})

describe('statusBg', () => {
  it('maps status levels to bg classes', () => {
    expect(statusBg('healthy')).toContain('green')
    expect(statusBg('critical')).toContain('red')
  })
})

describe('formatValue', () => {
  it('formats with unit and default precision', () => {
    expect(formatValue(7.35, 'mg/L')).toBe('7.35 mg/L')
  })

  it('uses custom precision', () => {
    expect(formatValue(7.3456, 'mg/L', 1)).toBe('7.3 mg/L')
  })

  it('returns em-dash for null', () => {
    expect(formatValue(null, 'mg/L')).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(formatValue(undefined, 'mg/L')).toBe('—')
  })
})

describe('formatPercent', () => {
  it('formats percentage with default precision', () => {
    expect(formatPercent(42.5)).toBe('42.5%')
  })

  it('uses custom precision', () => {
    expect(formatPercent(42.567, 2)).toBe('42.57%')
  })

  it('returns em-dash for null', () => {
    expect(formatPercent(null)).toBe('—')
  })
})

describe('trendIcon', () => {
  it('returns up arrow for improving', () => {
    expect(trendIcon('improving')).toBe('↑')
  })

  it('returns down arrow for deteriorating', () => {
    expect(trendIcon('deteriorating')).toBe('↓')
  })

  it('returns right arrow for stable', () => {
    expect(trendIcon('stable')).toBe('→')
  })
})

describe('trendColor', () => {
  it('maps trends to appropriate colors', () => {
    expect(trendColor('improving')).toBe('text-green-600')
    expect(trendColor('deteriorating')).toBe('text-red-600')
    expect(trendColor('stable')).toBe('text-slate-500')
  })
})

describe('healthScoreColor', () => {
  it('returns green for high health', () => {
    expect(healthScoreColor(80)).toBe('text-green-600')
    expect(healthScoreColor(75)).toBe('text-green-600')
  })

  it('returns amber for moderate health', () => {
    expect(healthScoreColor(60)).toBe('text-amber-500')
  })

  it('returns orange for low health', () => {
    expect(healthScoreColor(30)).toBe('text-orange-500')
  })

  it('returns red for critical health', () => {
    expect(healthScoreColor(10)).toBe('text-red-600')
  })
})

describe('healthScoreBg', () => {
  it('returns hex colors for health thresholds', () => {
    expect(healthScoreBg(80)).toBe('#16A34A')
    expect(healthScoreBg(60)).toBe('#D97706')
    expect(healthScoreBg(30)).toBe('#EA580C')
    expect(healthScoreBg(10)).toBe('#DC2626')
  })
})

describe('loopColor', () => {
  it('returns expected colors for scientific loops', () => {
    expect(loopColor('HYDROLOGICAL')).toBe('#0891B2')
    expect(loopColor('CHEMICAL')).toBe('#7C3AED')
    expect(loopColor('ECOLOGICAL')).toBe('#16A34A')
    expect(loopColor('INFRASTRUCTURE')).toBe('#D97706')
  })

  it('returns fallback for unknown loop', () => {
    expect(loopColor('UNKNOWN')).toBe('#64748B')
  })
})

describe('loopIcon', () => {
  it('returns emoji icons for each loop', () => {
    expect(loopIcon('HYDROLOGICAL')).toBe('💧')
    expect(loopIcon('CHEMICAL')).toBe('⚗️')
    expect(loopIcon('ECOLOGICAL')).toBe('🌿')
    expect(loopIcon('INFRASTRUCTURE')).toBe('⚙️')
  })

  it('returns fallback for unknown loop', () => {
    expect(loopIcon('UNKNOWN')).toBe('○')
  })
})

describe('truncate', () => {
  it('returns string unchanged if within limit', () => {
    expect(truncate('hello', 10)).toBe('hello')
  })

  it('truncates and appends ellipsis', () => {
    expect(truncate('hello world', 8)).toBe('hello...')
  })

  it('handles exact length', () => {
    expect(truncate('hello', 5)).toBe('hello')
  })
})

describe('groupBy', () => {
  it('groups items by string key', () => {
    const items = [
      { type: 'a', val: 1 },
      { type: 'b', val: 2 },
      { type: 'a', val: 3 },
    ]
    const result = groupBy(items, 'type')
    expect(result['a']).toHaveLength(2)
    expect(result['b']).toHaveLength(1)
  })

  it('returns empty object for empty array', () => {
    expect(groupBy([], 'any' as never)).toEqual({})
  })
})
