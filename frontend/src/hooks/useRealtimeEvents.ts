import { useEffect, useState, useCallback, useRef } from 'react'
import type { LOSEvent } from '@/types'
import { losWS } from '@/lib/websocket'
import { useLagoonStore } from '@/stores/lagoon.store'

interface UseRealtimeEventsOptions {
  maxEvents?: number
  eventTypes?: string[]
  loops?: string[]
  onCritical?: (event: LOSEvent) => void
}

export function useRealtimeEvents({
  maxEvents = 100,
  eventTypes,
  loops,
  onCritical,
}: UseRealtimeEventsOptions = {}) {
  const [events, setEvents] = useState<LOSEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const { selectedLagoonId } = useLagoonStore()
  const unsubscribeFns = useRef<Array<() => void>>([])

  const addEvent = useCallback(
    (event: LOSEvent) => {
      // Filter by event type if specified
      if (eventTypes && !eventTypes.includes(event.event_type)) return
      // Filter by loop if specified
      if (loops && !loops.includes(event.loop)) return

      setEvents((prev) => [event, ...prev].slice(0, maxEvents))

      if (event.priority === 'critical' && onCritical) {
        onCritical(event)
      }
    },
    [eventTypes, loops, maxEvents, onCritical]
  )

  useEffect(() => {
    if (!selectedLagoonId) return

    // Connect
    losWS.connect(selectedLagoonId)

    losWS.onConnect(() => setIsConnected(true))
    losWS.onDisconnect(() => setIsConnected(false))

    // Subscribe to events
    const unsub = losWS.onEvent(addEvent)
    unsubscribeFns.current.push(unsub)

    return () => {
      unsubscribeFns.current.forEach((fn) => fn())
      unsubscribeFns.current = []
    }
  }, [selectedLagoonId, addEvent])

  const clearEvents = useCallback(() => setEvents([]), [])

  return { events, isConnected, clearEvents }
}

export function useEventCount(priority?: string): number {
  const [count, setCount] = useState(0)
  const { selectedLagoonId } = useLagoonStore()

  useEffect(() => {
    if (!selectedLagoonId) return
    const unsub = losWS.onEvent((event) => {
      if (!priority || event.priority === priority) {
        setCount((c) => c + 1)
      }
    })
    return unsub
  }, [selectedLagoonId, priority])

  return count
}
