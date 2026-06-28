export interface Lagoon {
  id: string
  name: string
  slug: string
  location: { lat: number; lng: number; country: string; city: string }
  volume_m3: number
  surface_area_m2: number
  max_depth_m: number
  is_active: boolean
  created_at: string
}

export interface Observation {
  id: string
  lagoon_id: string
  sensor_id: string | null
  parameter: string
  value: number
  unit: string
  timestamp: string
  quality_flag: 'good' | 'suspect' | 'bad' | 'missing'
  confidence: number
  depth_m: number | null
  source: 'sensor' | 'laboratory' | 'manual' | 'satellite'
}

export interface ScientificLoopState {
  loop: 'HYDROLOGICAL' | 'CHEMICAL' | 'ECOLOGICAL' | 'INFRASTRUCTURE'
  status: 'healthy' | 'warning' | 'critical' | 'unknown'
  confidence: number
  last_updated: string
  state: Record<string, unknown>
}

export interface HydrologicalState {
  water_level_m: number | null
  volume_m3: number | null
  residence_time_days: number | null
  inflow_m3_day: number | null
  outflow_m3_day: number | null
  groundwater_flux_m3_day: number | null
  confidence: number
}

export interface ChemicalState {
  do_mg_l: number | null
  do_saturation_pct: number | null
  orp_mv: number | null
  ph: number | null
  ec_us_cm: number | null
  salinity_ppt: number | null
  tn_mg_l: number | null
  tp_mg_l: number | null
  nh4_mg_l: number | null
  no3_mg_l: number | null
  redox_class: 'oxic' | 'suboxic' | 'anoxic' | 'reducing' | null
  internal_loading_risk: 'low' | 'medium' | 'high' | 'critical' | null
  trophic_state: string | null
  confidence: number
}

export interface EcologicalState {
  bloom_probability: number | null
  bloom_detected: boolean
  dominant_community: string | null
  cyanobacteria_risk: 'low' | 'medium' | 'high' | 'critical'
  ecological_stability_score: number | null
  recovery_potential: 'low' | 'medium' | 'high' | null
  confidence: number
}

export interface InfrastructureState {
  aeration_status: 'online' | 'offline' | 'degraded' | 'unknown'
  pump_status: 'online' | 'offline' | 'degraded' | 'unknown'
  sensor_coverage_pct: number
  maintenance_due: boolean
  active_alerts: number
  confidence: number
}

export interface SystemState {
  lagoon_id: string
  timestamp: string
  overall_health_score: number
  overall_confidence: number
  loops: ScientificLoopState[]
  hydrological: HydrologicalState
  chemical: ChemicalState
  ecological: EcologicalState
  infrastructure: InfrastructureState
  wqi?: number | null
  compliance_score?: number | null
}

export interface AlternativeOption {
  action: string
  reason_not_recommended: string
  relative_score: number
}

export interface Recommendation {
  id: string
  lagoon_id: string
  action: string
  action_category: string
  scientific_reason: string
  contributing_loops: string[]
  evidence: Array<{ source: string; description: string; confidence: number }>
  confidence: number
  priority: 'critical' | 'high' | 'medium' | 'low'
  expected_outcome: string
  expected_timeframe_days: number
  alternative_options: AlternativeOption[]
  status: 'pending' | 'approved' | 'rejected' | 'implemented' | 'measured'
  created_at: string
  reviewed_at?: string
  reviewer_notes?: string
}

export interface LOSEvent {
  id: string
  lagoon_id: string
  event_type: string
  loop: string
  source: string
  priority: 'critical' | 'high' | 'medium' | 'low' | 'background'
  confidence: number
  payload: Record<string, unknown>
  correlation_id: string
  created_at: string
}

export interface OperatingObjective {
  id: string
  objective_type: string
  name: string
  description: string
  target_value: number
  current_value: number
  unit: string
  priority: number
  weight: number
  trend: 'improving' | 'stable' | 'deteriorating'
}

export interface Sensor {
  id: string
  lagoon_id: string
  name: string
  sensor_type: string
  parameters: string[]
  location: { lat: number; lng: number; depth_m: number }
  is_active: boolean
  last_reading_at: string | null
  battery_pct: number | null
  signal_strength: number | null
}

export interface Intervention {
  id: string
  lagoon_id: string
  recommendation_id: string | null
  intervention_type: string
  description: string
  scheduled_date: string
  completed_date: string | null
  status: 'planned' | 'in_progress' | 'completed' | 'cancelled'
  performed_by: string | null
  outcome_notes: string | null
}

export interface Report {
  id: string
  lagoon_id: string
  report_type: string
  title: string
  period_start: string
  period_end: string
  status: 'generating' | 'ready' | 'failed'
  file_url: string | null
  created_at: string
  created_by: string
}

export interface User {
  id: string
  email: string
  full_name: string
  role: 'superadmin' | 'admin' | 'engineer' | 'scientist' | 'operator' | 'viewer'
  org_id: string
  avatar_url?: string
  is_active: boolean
  last_login?: string
}

export interface Organisation {
  id: string
  name: string
  slug: string
  plan: 'starter' | 'professional' | 'enterprise'
  lagoon_count: number
  is_active: boolean
}

export interface APIResponse<T> {
  success: boolean
  timestamp: string
  request_id: string
  data: T
  errors?: Array<{ code: string; message: string }>
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface TimeSeriesPoint {
  timestamp: string
  value: number
  confidence?: number
  quality_flag?: string
}

export interface ForecastPoint {
  timestamp: string
  predicted: number
  lower_bound: number
  upper_bound: number
  confidence: number
}

export interface WaterQualityIndex {
  score: number
  grade: 'A' | 'B' | 'C' | 'D' | 'F'
  components: Array<{
    parameter: string
    score: number
    weight: number
    value: number | null
    unit: string
  }>
  trend: 'improving' | 'stable' | 'deteriorating'
}

export interface ComplianceStatus {
  overall_compliant: boolean
  compliance_score: number
  violations: Array<{
    parameter: string
    value: number
    limit: number
    unit: string
    severity: 'minor' | 'major' | 'critical'
  }>
  next_assessment_date: string
}

export interface LagoonPerformance {
  period_days: number
  water_quality_index: number
  bloom_events: number
  compliance_score: number
  intervention_count: number
  avg_residence_time_days: number | null
  trend_wqi: 'improving' | 'stable' | 'deteriorating'
}

export type LoopName = 'HYDROLOGICAL' | 'CHEMICAL' | 'ECOLOGICAL' | 'INFRASTRUCTURE'
export type StatusLevel = 'healthy' | 'warning' | 'critical' | 'unknown'
export type PriorityLevel = 'critical' | 'high' | 'medium' | 'low'
export type QualityFlag = 'good' | 'suspect' | 'bad' | 'missing'
