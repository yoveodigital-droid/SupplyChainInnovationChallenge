/** Mirrors backend/app/schemas.py. */

export type RiskLevel = "green" | "amber" | "red";

export interface Port {
  id: string;
  name: string;
  short_name: string;
  country: string;
  region: string;
  lat: number;
  lon: number;
  capacity_teu_per_day: number;
  base_congestion: number;
  base_waiting_days: number;
  demurrage_usd_per_teu_day: number;
  free_days: number;
  is_hub: boolean;
  congestion_threshold: number;
  blurb: string;
}

export interface PortStatus extends Port {
  congestion_now: number;
  waiting_now: number;
  weather_now: number;
  congestion_7d: number;
  disruption_probability_7d: number;
  confidence_7d: number;
  risk_level: RiskLevel;
}

export interface Chokepoint {
  id: string;
  name: string;
  lat: number;
  lon: number;
  base_risk: number;
  current_risk: number;
  delay_days_at_max_risk: number;
  note: string;
  risk_level: RiskLevel;
}

export interface Leg {
  id: string;
  origin_id: string;
  dest_id: string;
  mode: "sea" | "land";
  service: "mainline" | "feeder" | "truck";
  distance_nm: number;
  transit_days: number;
  cost_per_teu: number;
  co2_tonnes_per_teu: number;
  sailings_per_week: number;
  chokepoints: string[];
}

export interface Persona {
  id: string;
  name: string;
  role: string;
  org: string;
  location: string;
  view: "phone" | "dashboard" | "port";
  home_port_id: string | null;
  language: string;
  avatar: string;
  blurb: string;
  shipment_count: number;
}

export interface DisruptionEvent {
  id: string;
  day: string;
  type: "security" | "weather" | "labor" | "congestion" | "policy";
  severity: number;
  headline: string;
  detail: string;
  port_id: string | null;
  chokepoint_id: string | null;
  lat: number;
  lon: number;
  source: string;
  scenario: boolean;
}

export interface Observation {
  day: string;
  congestion_index: number;
  waiting_days: number;
  weather_severity: number;
  vessel_arrivals: number;
}

export interface ForecastPoint {
  port_id: string;
  day: string;
  horizon: number;
  congestion: number;
  congestion_low: number;
  congestion_high: number;
  waiting_days: number;
  waiting_low: number;
  waiting_high: number;
  disruption_probability: number;
  confidence: number;
  expected_arrivals: number;
  congestion_baseline: number;
  event_uplift: number;
  event_drivers: { headline: string; points: number }[];
}

export interface Contribution {
  feature: string;
  label: string;
  effect: number;
  direction: "raises" | "lowers";
}

export interface Forecast {
  port_id: string;
  port_name: string;
  as_of: string;
  horizon_days: number;
  congestion_threshold: number;
  points: ForecastPoint[];
  explanation: Contribution[];
  model_note: string;
}

export interface PortPressure {
  port: PortStatus;
  as_of: string;
  history: Observation[];
  forecast: ForecastPoint[];
  explanation: Contribution[];
  upstream_events: DisruptionEvent[];
  inbound_shipments: number;
  summary: string;
  peak_day: string | null;
  peak_congestion: number;
}

export interface Shipment {
  id: string;
  persona_id: string;
  reference: string;
  origin_id: string;
  dest_id: string;
  origin_name: string;
  dest_name: string;
  leg_ids: string[];
  etd: string;
  required_by: string;
  cargo: string;
  cargo_short: string;
  teu: number;
  perishable: boolean;
  shelf_life_days: number | null;
  value_usd: number;
  status: string;
  buyer: string;
  applied_option: string | null;
  rerouted: boolean;
  risk_level: RiskLevel;
  risk_score: number;
  expected_delay_days: number;
  spoilage_probability: number | null;
}

export interface Call {
  port_id: string;
  port_name: string;
  port_short_name: string;
  day: string;
  role: "load" | "transship" | "discharge";
  service: string;
  forecast_congestion: number;
  forecast_waiting: number;
  normal_waiting: number;
  delay_days: number;
  disruption_probability: number;
  confidence: number;
  risk_level: RiskLevel;
}

export interface LegExposure {
  leg_id: string;
  origin_id: string;
  dest_id: string;
  mode: "sea" | "land";
  service: string;
  depart: string;
  arrive: string;
  transit_days: number;
  chokepoints: string[];
  chokepoint_risk: number;
  chokepoint_delay_days: number;
  connection_delay_days: number;
  risk_level: RiskLevel;
}

export interface Exposure {
  shipment_id: string;
  etd: string;
  required_by: string;
  scheduled_transit_days: number;
  scheduled_arrival: string;
  expected_delay_days: number;
  delay_p10: number;
  delay_p90: number;
  expected_arrival: string;
  prob_delay_over_3: number;
  prob_delay_over_7: number;
  prob_miss_deadline: number;
  demurrage_usd: number;
  demurrage_days: number;
  spoilage_probability: number | null;
  spoilage_band: RiskLevel | null;
  expected_spoilage_loss_usd: number;
  risk_score: number;
  risk_level: RiskLevel;
  confidence: number;
  calls: Call[];
  legs: LegExposure[];
  drivers: { kind: string; label: string; days: number }[];
  delay_distribution: { days: number; probability: number; plus?: boolean }[];
}

export interface CostBreakdown {
  freight_usd: number;
  demurrage_usd: number;
  spoilage_loss_usd: number;
  late_penalty_usd: number;
  holding_usd: number;
  carbon_usd: number;
  total_usd: number;
}

export interface Option {
  id: string;
  kind: "hold" | "reroute" | "delay" | "reroute_delay";
  label: string;
  summary: string;
  rationale: string;
  leg_ids: string[];
  route_ports: string[];
  route_port_names: string[];
  via: string[];
  etd: string;
  departure_delay_days: number;
  scheduled_transit_days: number;
  scheduled_arrival: string;
  expected_arrival: string;
  required_by: string;
  days_late: number;
  delta_cost_usd: number;
  delta_transit_days: number;
  delta_risk_days: number;
  delta_co2_tonnes: number;
  freight_usd: number;
  co2_tonnes: number;
  expected_delay_days: number;
  prob_delay_over_3: number;
  prob_delay_over_7: number;
  prob_miss_deadline: number;
  demurrage_usd: number;
  spoilage_probability: number | null;
  spoilage_band: RiskLevel | null;
  risk_level: RiskLevel;
  confidence: number;
  costs: CostBreakdown;
  savings_usd: number;
  score: number;
  rank: number;
  recommended: boolean;
  dominated_by: string | null;
  caveats: string[];
}

export interface Recommendations {
  shipment_id: string;
  as_of: string;
  options: Option[];
  objective: string;
  assumptions: Record<string, number | string>;
}

export interface Chip {
  key: "cost" | "time" | "risk" | "co2";
  label: string;
  tone: "good" | "bad";
}

export interface ChatMessage {
  id: string;
  sender: "portpulse" | "user";
  kind: "alert" | "prompt" | "option" | "confirmation" | "calm" | "followup";
  text: string;
  chips: Chip[];
  option_id: string | null;
  recommended: boolean;
}

export interface Alert {
  shipment_id: string;
  language: string;
  risk_level: RiskLevel;
  alert_text: string;
  alert_chars: number;
  within_limit: boolean;
  messages: ChatMessage[];
  quick_replies: string[];
}

export interface DemoState {
  sim_date: string;
  seed_date: string;
  days_advanced: number;
  scenario_active: boolean;
  scenario_day: number;
  scenario_start: string | null;
  data_version: number;
  can_advance: boolean;
}

export interface Meta {
  name: string;
  tagline: string;
  disclaimer: string;
  languages: string[];
  risk_thresholds: { amber: number; red: number };
  max_horizon_days: number;
  model: Record<string, number | string>;
  demo: DemoState;
}

export interface AcceptResult {
  shipment: Shipment;
  message: ChatMessage;
  exposure: Exposure;
}
