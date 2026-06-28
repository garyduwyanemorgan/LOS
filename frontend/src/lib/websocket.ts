import type { LOSEvent } from '@/types'

type EventHandler = (event: LOSEvent) => void
type ConnectionHandler = () => void
type ErrorHandler = (error: Event) => void

interface WSSubscription {
  eventType?: string
  handler: EventHandler
}

const MAX_RETRIES = 5

class LOSWebSocket {
  private ws: WebSocket | null = null
  private url: string
  private subscriptions: Map<string, WSSubscription[]> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private retryCount = 0
  private isIntentionalClose = false
  private lagoonId: string | null = null

  private onConnectHandlers: ConnectionHandler[] = []
  private onDisconnectHandlers: ConnectionHandler[] = []
  private onErrorHandlers: ErrorHandler[] = []

  constructor() {
    this.url = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
  }

  connect(lagoonId: string): void {
    this.lagoonId = lagoonId
    this.isIntentionalClose = false
    this.retryCount = 0
    this._connect()
  }

  private _connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return

    const token = localStorage.getItem('los_access_token')
    const wsUrl = `${this.url}/lagoons/${this.lagoonId}?token=${token ?? ''}`

    try {
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('[LOS WS] Connected')
        this.retryCount = 0
        this.onConnectHandlers.forEach((h) => h())
      }

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as LOSEvent
          this._dispatch(data)
        } catch (err) {
          console.error('[LOS WS] Failed to parse message', err)
        }
      }

      this.ws.onclose = () => {
        console.log('[LOS WS] Disconnected')
        this.onDisconnectHandlers.forEach((h) => h())
        if (!this.isIntentionalClose) this._scheduleReconnect()
      }

      this.ws.onerror = (error: Event) => {
        if (this.retryCount < 2) {
          console.error('[LOS WS] Error Event', error)
        }
        this.onErrorHandlers.forEach((h) => h(error))
      }
    } catch (err) {
      console.error('[LOS WS] Connection failed', err)
      this._scheduleReconnect()
    }
  }

  private _scheduleReconnect(): void {
    if (this.retryCount >= MAX_RETRIES) {
      console.log('[LOS WS] Max retries reached — running in polling-only mode')
      return
    }

    const delay = Math.min(30000, 1000 * 2 ** this.retryCount)
    console.log(`[LOS WS] Reconnecting in ${Math.round(delay)}ms (attempt ${this.retryCount + 1})`)

    this.reconnectTimer = setTimeout(() => {
      this.retryCount++
      this._connect()
    }, delay)
  }

  disconnect(): void {
    this.isIntentionalClose = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  private _dispatch(event: LOSEvent): void {
    // Dispatch to all-events subscribers
    const allSubs = this.subscriptions.get('*') ?? []
    allSubs.forEach((sub) => sub.handler(event))

    // Dispatch to event-type subscribers
    const typeSubs = this.subscriptions.get(event.event_type) ?? []
    typeSubs.forEach((sub) => sub.handler(event))

    // Dispatch to loop subscribers
    const loopSubs = this.subscriptions.get(`loop:${event.loop}`) ?? []
    loopSubs.forEach((sub) => sub.handler(event))
  }

  subscribe(key: string, handler: EventHandler): () => void {
    const existing = this.subscriptions.get(key) ?? []
    const sub: WSSubscription = { eventType: key, handler }
    this.subscriptions.set(key, [...existing, sub])

    return () => {
      const current = this.subscriptions.get(key) ?? []
      this.subscriptions.set(
        key,
        current.filter((s) => s !== sub)
      )
    }
  }

  /** Subscribe to all events */
  onEvent(handler: EventHandler): () => void {
    return this.subscribe('*', handler)
  }

  /** Subscribe to a specific event type */
  onEventType(eventType: string, handler: EventHandler): () => void {
    return this.subscribe(eventType, handler)
  }

  /** Subscribe to events from a specific loop */
  onLoop(loop: string, handler: EventHandler): () => void {
    return this.subscribe(`loop:${loop}`, handler)
  }

  onConnect(handler: ConnectionHandler): void {
    this.onConnectHandlers.push(handler)
  }

  onDisconnect(handler: ConnectionHandler): void {
    this.onDisconnectHandlers.push(handler)
  }

  onError(handler: ErrorHandler): void {
    this.onErrorHandlers.push(handler)
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.warn('[LOS WS] Cannot send — not connected')
    }
  }
}

export const losWS = new LOSWebSocket()
export default losWS
