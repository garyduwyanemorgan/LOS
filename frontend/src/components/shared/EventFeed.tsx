import React, { useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, Info, Zap } from 'lucide-react'
import type { LOSEvent } from '@/types'
import { cn, priorityColor, formatRelative, loopColor } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'

interface EventFeedProps {
  events: LOSEvent[]
  maxItems?: number
  autoScroll?: boolean
  className?: string
  compact?: boolean
}

const PRIORITY_ICONS: Record<string, React.ReactNode> = {
  critical: <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />,
  high: <Zap className="h-3.5 w-3.5 text-orange-500 shrink-0" />,
  medium: <Activity className="h-3.5 w-3.5 text-amber-500 shrink-0" />,
  low: <Info className="h-3.5 w-3.5 text-blue-400 shrink-0" />,
  background: <Info className="h-3.5 w-3.5 text-slate-400 shrink-0" />,
}

interface EventItemProps {
  event: LOSEvent
  compact: boolean
}

const EventItem: React.FC<EventItemProps> = ({ event, compact }) => {
  const loopClr = loopColor(event.loop)

  return (
    <div
      className={cn(
        'flex items-start gap-2.5 py-2 px-3 border-b border-slate-100 last:border-b-0 hover:bg-slate-50 transition-colors',
        event.priority === 'critical' && 'bg-red-50 hover:bg-red-50 border-l-2 border-l-red-400'
      )}
    >
      {PRIORITY_ICONS[event.priority] ?? <Info className="h-3.5 w-3.5 text-slate-400 shrink-0" />}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-semibold text-slate-800 truncate">
            {event.event_type.replace(/_/g, ' ')}
          </span>
          <span
            className="text-xs px-1.5 py-0.5 rounded font-medium"
            style={{ background: `${loopClr}22`, color: loopClr }}
          >
            {event.loop}
          </span>
        </div>

        {!compact && (
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            Source: {event.source} · {Math.round(event.confidence * 100)}% confidence
          </p>
        )}
      </div>

      <span className="text-xs text-slate-400 shrink-0 mt-0.5">
        {formatRelative(event.created_at)}
      </span>
    </div>
  )
}

export const EventFeed: React.FC<EventFeedProps> = ({
  events,
  maxItems = 50,
  autoScroll = true,
  className,
  compact = false,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isUserScrolled, setIsUserScrolled] = useState(false)
  const displayEvents = events.slice(0, maxItems)

  useEffect(() => {
    if (autoScroll && !isUserScrolled && scrollRef.current) {
      scrollRef.current.scrollTop = 0
    }
  }, [events, autoScroll, isUserScrolled])

  if (!events.length) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center py-8 text-slate-400',
          className
        )}
      >
        <Activity className="h-8 w-8 mb-2 opacity-40" />
        <p className="text-sm">No events yet</p>
        <p className="text-xs">Waiting for real-time data...</p>
      </div>
    )
  }

  return (
    <ScrollArea className={cn('border rounded-lg', className)} ref={scrollRef as React.Ref<HTMLDivElement>}>
      <div className="divide-y divide-slate-100">
        {displayEvents.map((event) => (
          <EventItem key={event.id} event={event} compact={compact} />
        ))}
      </div>
    </ScrollArea>
  )
}
