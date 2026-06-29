import axios, { AxiosInstance, AxiosError } from 'axios'
import type {
  Lagoon,
  Observation,
  Recommendation,
  LOSEvent,
  OperatingObjective,
  Sensor,
  Intervention,
  Report,
  User,
  SystemState,
  PaginatedResponse,
  LagoonPerformance,
} from '@/types'

const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Auth interceptor: add Bearer token
// Reads from plain key first (set on login), falls back to Zustand persist state
function getAccessToken(): string | null {
  return (
    localStorage.getItem('los_access_token') ||
    (() => {
      try {
        const stored = localStorage.getItem('los-auth')
        return stored ? JSON.parse(stored)?.state?.accessToken ?? null : null
      } catch {
        return null
      }
    })()
  )
}

http.interceptors.request.use(
  (config) => {
    const token = getAccessToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: unwrap data, handle 401
http.interceptors.response.use(
  (response) => response.data,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('los_refresh_token')
      if (refreshToken) {
        try {
          const resp = await axios.post(
            `${import.meta.env.VITE_API_URL || '/api/v1'}/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`
          )
          const { access_token } = resp.data as { access_token: string }
          localStorage.setItem('los_access_token', access_token)
          if (error.config) {
            error.config.headers.Authorization = `Bearer ${access_token}`
            return http.request(error.config)
          }
        } catch {
          localStorage.removeItem('los_access_token')
          localStorage.removeItem('los_refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// Helper to normalise backend {items, meta} paginated responses to PaginatedResponse<T>
function normPage<T>(r: any): PaginatedResponse<T> {
  return {
    items: r?.items ?? [],
    total: r?.meta?.total ?? r?.items?.length ?? 0,
    skip: r?.meta?.skip ?? 0,
    limit: r?.meta?.limit ?? 100,
  }
}

// Transform raw /status API response → frontend SystemState shape
function _parseSystemState(r: any): SystemState {
  const loopStates: Record<string, any> = r?.loop_states ?? {}
  const confScores: Record<string, number> = r?.confidence_scores ?? {}

  const LOOP_NAMES = ['hydrological', 'chemical', 'ecological', 'infrastructure'] as const

  const loops = LOOP_NAMES.map((name) => {
    const st = loopStates[name]?.state ?? {}
    const conf: number = st.confidence ?? confScores[name] ?? 0
    const status =
      conf >= 0.7 ? 'healthy' : conf >= 0.4 ? 'warning' : conf > 0 ? 'critical' : 'unknown'
    return {
      loop: name.toUpperCase() as SystemState['loops'][number]['loop'],
      status,
      confidence: conf,
      last_updated: st.timestamp ?? r.timestamp ?? new Date().toISOString(),
      state: st,
    }
  })

  const cs = loopStates['chemical']?.state ?? {}
  const es = loopStates['ecological']?.state ?? {}
  const hs = loopStates['hydrological']?.state ?? {}
  const is_ = loopStates['infrastructure']?.state ?? {}

  const chemical: SystemState['chemical'] = {
    do_mg_l: cs.do_mg_l ?? null,
    do_saturation_pct: cs.do_saturation_pct ?? null,
    orp_mv: cs.orp_mv ?? null,
    ph: cs.ph ?? null,
    ec_us_cm: cs.ec_us_cm ?? cs.conductivity_us_cm ?? null,
    salinity_ppt: cs.salinity_ppt ?? null,
    tn_mg_l: cs.tn_mg_l ?? null,
    tp_mg_l: cs.tp_mg_l ?? null,
    nh4_mg_l: cs.nh4_mg_l ?? null,
    no3_mg_l: cs.no3_mg_l ?? null,
    redox_class: cs.redox_class ?? null,
    internal_loading_risk: cs.internal_loading_risk ?? null,
    trophic_state: cs.trophic_state ?? null,
    confidence: cs.confidence ?? 0,
  }

  const bloomProb: number | null = es.bloom_probability ?? null
  const cyanRisk =
    es.toxin_risk === 'critical' || (bloomProb !== null && bloomProb > 0.9)
      ? 'critical'
      : es.toxin_risk === 'high' || (bloomProb !== null && bloomProb > 0.6)
        ? 'high'
        : es.toxin_risk === 'medium' || (bloomProb !== null && bloomProb > 0.3)
          ? 'medium'
          : 'low'

  const ecological: SystemState['ecological'] = {
    bloom_probability: bloomProb,
    bloom_detected: es.succession_stage === 'active_bloom' || (bloomProb !== null && bloomProb > 0.7),
    dominant_community: es.dominant_species ?? null,
    cyanobacteria_risk: cyanRisk as SystemState['ecological']['cyanobacteria_risk'],
    ecological_stability_score: es.ecological_stability_score ?? null,
    recovery_potential: es.recovery_potential ?? null,
    confidence: es.confidence ?? 0,
  }

  const hydrological: SystemState['hydrological'] = {
    water_level_m: hs.water_level_m ?? null,
    volume_m3: hs.volume_m3 ?? null,
    residence_time_days: hs.residence_time_days ?? null,
    inflow_m3_day: hs.inflow_m3_day ?? null,
    outflow_m3_day: hs.outflow_m3_day ?? null,
    groundwater_flux_m3_day: hs.groundwater_flux_m3_day ?? null,
    confidence: hs.confidence ?? 0,
  }

  const hasAeration = (is_.active_aeration_kg_hr ?? 0) > 0
  const hasPumps = (is_.pumps ?? []).some((p: any) => p.status === 'online')
  const infrastructure: SystemState['infrastructure'] = {
    aeration_status: hasAeration ? 'online' : (is_.total_aeration_capacity_kg_hr ?? 0) > 0 ? 'offline' : 'unknown',
    pump_status: hasPumps ? 'online' : (is_.pumps ?? []).length > 0 ? 'offline' : 'unknown',
    sensor_coverage_pct: is_.data_completeness_pct ?? 0,
    maintenance_due: (is_.overdue_maintenance_count ?? 0) > 0,
    active_alerts: is_.active_alerts ?? 0,
    confidence: is_.confidence ?? 0,
  }

  const avgConf =
    loops.reduce((s, l) => s + l.confidence, 0) / Math.max(loops.length, 1)

  // ── Water Quality Index (0–100) ──────────────────────────────────────────────
  let wqi = 100
  const doVal = cs.do_mg_l ?? null
  const phVal = cs.ph ?? null
  const trophic = cs.trophic_state ?? null
  if (doVal !== null) wqi -= doVal < 5 ? 20 : doVal < 7 ? 10 : 0
  if (phVal !== null) wqi -= (phVal < 6.5 || phVal > 9.0) ? 15 : (phVal < 7.5 || phVal > 8.5) ? 5 : 0
  if (trophic === 'hypereutrophic') wqi -= 20
  else if (trophic === 'eutrophic') wqi -= 10
  wqi = Math.max(0, Math.min(100, Math.round(wqi)))
  const wqiValue: number | null =
    (doVal !== null || phVal !== null || trophic !== null) ? wqi : null

  // ── Compliance Score (0–100) ─────────────────────────────────────────────────
  const chemConf = cs.confidence ?? 0
  const ecoConf = (loopStates['ecological']?.state ?? {}).confidence ?? 0
  const infraConf = (loopStates['infrastructure']?.state ?? {}).confidence ?? 0
  const hydroConf = (loopStates['hydrological']?.state ?? {}).confidence ?? 0
  const hasAnyData = chemConf > 0 || ecoConf > 0 || infraConf > 0 || hydroConf > 0
  const complianceScore: number | null = hasAnyData
    ? Math.round((chemConf * 0.4 + ecoConf * 0.3 + infraConf * 0.2 + hydroConf * 0.1) * 100)
    : null

  return {
    lagoon_id: r.lagoon_id,
    timestamp: r.timestamp ?? new Date().toISOString(),
    overall_health_score: r.overall_health_score || avgConf,
    overall_confidence: r.overall_confidence || avgConf,
    loops,
    chemical,
    ecological,
    hydrological,
    infrastructure,
    wqi: wqiValue,
    compliance_score: complianceScore,
  }
}

// ─── Lagoon endpoints ──────────────────────────────────────────────────────────
export const lagoonApi = {
  list: (): Promise<Lagoon[]> =>
    http.get<any>('/lagoons').then((r: any) => r.items ?? []),
  get: (id: string): Promise<Lagoon> => http.get(`/lagoons/${id}`),
  create: (data: Partial<Lagoon>): Promise<Lagoon> => http.post('/lagoons', data),
  update: (id: string, data: Partial<Lagoon>): Promise<Lagoon> =>
    http.patch(`/lagoons/${id}`, data),
  getStatus: (id: string): Promise<SystemState> =>
    http.get<any>(`/lagoons/${id}/status`).then(_parseSystemState),
  getObjectives: (id: string): Promise<OperatingObjective[]> =>
    http.get(`/lagoons/${id}/objectives`),
  updateObjectives: (
    id: string,
    objectives: Partial<OperatingObjective>[]
  ): Promise<OperatingObjective[]> => http.put(`/lagoons/${id}/objectives`, objectives),
  getPerformance: (id: string, days?: number): Promise<LagoonPerformance> =>
    http.get(`/lagoons/${id}/performance`, { params: { days } }),
}

// ─── Observation endpoints ─────────────────────────────────────────────────────
// Backend: GET /lagoons/{id}/observations/latest → {lagoon_id, timestamp, readings: {param: {value, unit, ...}}}
//          GET /lagoons/{id}/observations/timeseries/{param}?start&end → {data: [...]}
function _readingsToObservations(lagoonId: string, r: any): Observation[] {
  return Object.entries((r.readings ?? {}) as Record<string, any>).map(([parameter, d]: [string, any]) => ({
    id: `${lagoonId}-${parameter}`,
    lagoon_id: lagoonId,
    parameter,
    value: d?.value ?? 0,
    unit: d?.unit ?? '',
    timestamp: d?.timestamp ?? r.timestamp ?? new Date().toISOString(),
    quality_flag: (d?.quality_flag ?? 'good') as Observation['quality_flag'],
    confidence: d?.confidence ?? 1.0,
    depth_m: d?.depth_m ?? null,
    source: (d?.source ?? 'sensor') as Observation['source'],
    sensor_id: d?.sensor_id ?? null,
  }))
}

export const observationApi = {
  ingest: (lagoonId: string, data: Partial<Observation>): Promise<Observation> =>
    http.post(`/lagoons/${lagoonId}/observations`, data),
  getLatest: (lagoonId: string): Promise<Observation[]> =>
    http.get<any>(`/lagoons/${lagoonId}/observations/latest`)
      .then((r: any) => _readingsToObservations(lagoonId, r)),
  getTimeSeries: (lagoonId: string, parameter: string, start: string, end: string): Promise<Observation[]> =>
    http.get<any>(`/lagoons/${lagoonId}/observations/timeseries/${parameter}`, {
      params: { start, end },
    }).then((r: any) =>
      (r?.data ?? []).map((d: any) => ({
        id: d.id ?? `${lagoonId}-${parameter}-${d.timestamp}`,
        lagoon_id: lagoonId,
        parameter,
        value: d.value ?? 0,
        unit: d.unit ?? '',
        timestamp: d.timestamp,
        quality_flag: (d.quality_flag ?? 'good') as Observation['quality_flag'],
        confidence: d.confidence ?? 1.0,
        depth_m: d.depth_m ?? null,
        source: (d.source ?? 'sensor') as Observation['source'],
        sensor_id: d.sensor_id ?? null,
      }))
    ),
  // Legacy list shim → maps to latest readings
  list: (params: Record<string, unknown>): Promise<PaginatedResponse<Observation>> => {
    const lagoonId = String(params.lagoon_id ?? '')
    if (!lagoonId) return Promise.resolve({ items: [], total: 0, skip: 0, limit: 0 })
    return http.get<any>(`/lagoons/${lagoonId}/observations/latest`)
      .then((r: any) => {
        const items = _readingsToObservations(lagoonId, r)
        return { items, total: items.length, skip: 0, limit: items.length }
      })
      .catch(() => ({ items: [], total: 0, skip: 0, limit: 0 }))
  },
}

// ─── Recommendation endpoints ──────────────────────────────────────────────────
export const recommendationApi = {
  list: (lagoonId: string, status?: string): Promise<PaginatedResponse<Recommendation>> =>
    http.get<any>(`/lagoons/${lagoonId}/recommendations`, {
      params: status ? { status } : undefined,
    }).then(normPage<Recommendation>),
  approve: (lagoonId: string, id: string, notes?: string): Promise<Recommendation> =>
    http.post(`/lagoons/${lagoonId}/recommendations/${id}/approve`, { notes }),
  reject: (lagoonId: string, id: string, reason: string): Promise<Recommendation> =>
    http.post(`/lagoons/${lagoonId}/recommendations/${id}/reject`, { reason }),
}

// ─── Event endpoints ───────────────────────────────────────────────────────────
export const eventApi = {
  list: (lagoonId: string, params?: Record<string, unknown>): Promise<PaginatedResponse<LOSEvent>> =>
    http.get<any>(`/lagoons/${lagoonId}/events`, { params }).then(normPage<LOSEvent>),
  get: (lagoonId: string, id: string): Promise<LOSEvent> =>
    http.get(`/lagoons/${lagoonId}/events/${id}`),
}

// ─── Sensor endpoints ──────────────────────────────────────────────────────────
export const sensorApi = {
  list: (lagoonId: string): Promise<Sensor[]> =>
    http.get<any>(`/lagoons/${lagoonId}/sensors`).then((r: any) => r?.items ?? []),
  get: (lagoonId: string, id: string): Promise<Sensor> =>
    http.get(`/lagoons/${lagoonId}/sensors/${id}`),
  create: (lagoonId: string, data: Partial<Sensor>): Promise<Sensor> =>
    http.post(`/lagoons/${lagoonId}/sensors`, data),
  update: (lagoonId: string, id: string, data: Partial<Sensor>): Promise<Sensor> =>
    http.patch(`/lagoons/${lagoonId}/sensors/${id}`, data),
  delete: (lagoonId: string, id: string): Promise<void> =>
    http.delete(`/lagoons/${lagoonId}/sensors/${id}`),
}

// ─── Intervention endpoints ────────────────────────────────────────────────────
export const interventionApi = {
  list: (lagoonId: string, params?: Record<string, unknown>): Promise<PaginatedResponse<Intervention>> =>
    http.get<any>(`/lagoons/${lagoonId}/interventions`, { params }).then(normPage<Intervention>),
  get: (lagoonId: string, id: string): Promise<Intervention> =>
    http.get(`/lagoons/${lagoonId}/interventions/${id}`),
  create: (lagoonId: string, data: Partial<Intervention>): Promise<Intervention> =>
    http.post(`/lagoons/${lagoonId}/interventions`, data),
  update: (lagoonId: string, id: string, data: Partial<Intervention>): Promise<Intervention> =>
    http.patch(`/lagoons/${lagoonId}/interventions/${id}`, data),
  complete: (lagoonId: string, id: string, notes: string): Promise<Intervention> =>
    http.post(`/lagoons/${lagoonId}/interventions/${id}/outcome`, {
      outcome_description: notes,
      effectiveness_score: 1.0,
    }),
}

// ─── Report endpoints ──────────────────────────────────────────────────────────
export const reportApi = {
  list: (lagoonId: string): Promise<Report[]> =>
    http.get<any>(`/lagoons/${lagoonId}/reports`)
      .then((r: any) => r?.items ?? r ?? [])
      .catch(() => [] as Report[]),
  generate: (data: {
    lagoon_id: string
    report_type: string
    period_start?: string
    period_end?: string
    period_days?: number
    format?: string
  }): Promise<any> => {
    const periodDays =
      data.period_days ??
      (data.period_start && data.period_end
        ? Math.max(1, Math.round(
            (new Date(data.period_end).getTime() - new Date(data.period_start).getTime()) /
            (1000 * 60 * 60 * 24)
          ))
        : 30)
    return http.post(`/lagoons/${data.lagoon_id}/reports`, {
      report_type: data.report_type,
      period_days: Math.min(365, periodDays),
      format: data.format ?? 'markdown',
    })
  },
  download: (id: string): Promise<Blob> =>
    http.get(`/reports/${id}/download`, { responseType: 'blob' } as Parameters<typeof http.get>[1]),
}

// ─── Simulation endpoints ──────────────────────────────────────────────────────
export const simulationApi = {
  list: (lagoonId: string): Promise<Record<string, unknown>[]> =>
    http.get<any>(`/lagoons/${lagoonId}/simulations`).then((r: any) => r?.items ?? []),
  runForecast: (lagoonId: string, horizonDays: number): Promise<Record<string, unknown>> =>
    http.get<any>(`/lagoons/${lagoonId}/simulations`)
      .then((r: any) => ({ items: r?.items ?? [], horizon_days: horizonDays }))
      .catch(() => ({ items: [], horizon_days: horizonDays })),
  getScenario: (lagoonId: string, id: string): Promise<Record<string, unknown>> =>
    http.get(`/lagoons/${lagoonId}/simulations/${id}`),
  listScenarios: (lagoonId: string): Promise<Record<string, unknown>[]> =>
    http.get<any>(`/lagoons/${lagoonId}/simulations`).then((r: any) => r?.items ?? []),
}

// ─── User / Admin endpoints ────────────────────────────────────────────────────
export const userApi = {
  me: (): Promise<User> => http.get('/users/me'),
  list: (): Promise<User[]> => http.get('/users'),
  get: (id: string): Promise<User> => http.get(`/users/${id}`),
  create: (data: Partial<User> & { password: string }): Promise<User> =>
    http.post('/users', data),
  update: (id: string, data: Partial<User>): Promise<User> =>
    http.put(`/users/${id}`, data),
  delete: (id: string): Promise<void> => http.delete(`/users/${id}`),
}

export const authApi = {
  login: (email: string, password: string): Promise<{ access_token: string; refresh_token: string }> =>
    http.post('/auth/login', { email, password }),
  logout: (): Promise<void> => http.post('/auth/logout'),
  refresh: (refreshToken: string): Promise<{ access_token: string }> =>
    http.post('/auth/refresh', { refresh_token: refreshToken }),
}

export const healthApi = {
  check: (): Promise<{ status: string; version: string; timestamp: string }> =>
    http.get('/health'),
  detailed: (): Promise<Record<string, unknown>> => http.get('/health/detailed'),
}

export const adaptiveSamplingApi = {
  getSchedule: (_lagoonId: string): Promise<Record<string, unknown>> =>
    Promise.resolve({ schedule: [] }),
  updateSchedule: (_lagoonId: string, _data: Record<string, unknown>): Promise<Record<string, unknown>> =>
    Promise.resolve({}),
  getSuggestions: (_lagoonId: string): Promise<Record<string, unknown>[]> =>
    Promise.resolve([]),
}

// Unified namespace client — pages import { api } from '@/lib/api'
export const api = {
  lagoons: {
    ...lagoonApi,
    getSystemState: (id: string) => lagoonApi.getStatus(id),
  },
  observations: {
    ...observationApi,
    getRecent: async (lagoonId: string, params: Record<string, unknown>) => {
      const hours = (params?.hours as number) ?? 24
      const now = new Date()
      const start = new Date(now.getTime() - hours * 3600 * 1000)
      const KEY_PARAMS = ['dissolved_oxygen', 'ph', 'orp', 'conductivity', 'chlorophyll_a', 'water_temperature', 'turbidity']
      const results = await Promise.allSettled(
        KEY_PARAMS.map(p => observationApi.getTimeSeries(lagoonId, p, start.toISOString(), now.toISOString()))
      )
      return results.flatMap(r => r.status === 'fulfilled' ? r.value : [] as Observation[])
    },
    getLabResults: (lagoonId: string, _params: Record<string, unknown>) =>
      observationApi.getLatest(lagoonId)
        .then((obs) => obs.filter((o) => o.source === 'laboratory'))
        .catch(() => [] as Observation[]),
  },
  recommendations: {
    ...recommendationApi,
    list: (lagoonId: string, params?: Record<string, unknown>) =>
      recommendationApi.list(lagoonId, params?.status as string | undefined).then((r) => r.items),
    approve: (lagoonId: string, id: string, opts?: { notes?: string }) =>
      recommendationApi.approve(lagoonId, id, opts?.notes),
    reject: (lagoonId: string, id: string, opts?: { reason: string }) =>
      recommendationApi.reject(lagoonId, id, opts?.reason ?? ''),
  },
  events: {
    ...eventApi,
    listByLagoon: (lagoonId: string, params?: Record<string, unknown>) =>
      eventApi.list(lagoonId, params).then((r) => r.items),
  },
  sensors: sensorApi,
  interventions: interventionApi,
  reports: reportApi,
  simulations: {
    ...simulationApi,
    getPredictions: (_lagoonId: string, _params?: Record<string, unknown>) =>
      Promise.resolve(null as any),
  },
  users: userApi,
  auth: authApi,
  health: healthApi,
  adaptiveSampling: adaptiveSamplingApi,
}

export default api
