const API_BASE = "http://127.0.0.1:19823/api/v1";

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.token) {
    headers["Authorization"] = `Bearer ${opts.token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json();
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  netguard_active: boolean;
  database: {
    status: string;
    path?: string;
    detail?: string;
  };
  ollama: {
    status: string;
    models?: string[];
    primary_available?: boolean;
    secondary_available?: boolean;
    detail?: string;
  };
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export interface MineOption {
  id: number;
  code: string;
  name: string;
}

export interface BenchOption {
  id: number;
  code: string;
  name: string;
  bench_type: string;
}

export interface ShiftEntry {
  id: number;
  uuid: string;
  mine_id: number;
  bench_id: number;
  work_date: string;
  shift_code: string;
  foreman_id: number;
  planned_min: number;
  workers_present: number;
  production_milli_t: number;
  ob_milli_m3: number;
  stoppage_min: number;
  operating_min: number;
  weather_code: string | null;
  rainfall_mm_x10: number | null;
  temperature_c_x10: number | null;
  remarks: string | null;
  status: string;
  version: number;
  current_step: number;
  created_at: string;
  updated_at: string;
  downtime_events: DowntimeEvent[];
  warnings: string[];
}

export interface DowntimeEvent {
  id?: number;
  equipment_id?: number | null;
  category: string;
  start_min: number;
  end_min: number;
  duration_min?: number;
  cause_text?: string | null;
  evidence_path?: string | null;
}

export interface ReportMetric {
  metric_code: string;
  value_int: number;
  unit: string;
  is_additive: boolean;
}

export interface LineageEdge {
  id: number;
  child_kind: string;
  child_report_id: number | null;
  child_shift_entry_id: number | null;
}

export interface Report {
  id: number;
  uuid: string;
  level: string;
  mine_id: number;
  bench_id: number | null;
  period_start: string;
  period_end: string;
  status: string;
  version: number;
  generated_at: string | null;
  input_hash: string | null;
  expected_children: number;
  present_children: number;
  metrics: ReportMetric[];
  lineage_edges: LineageEdge[];
}

export interface MetricContribution {
  metric_code: string;
  edge_id: number;
  child_kind: string;
  child_id: number;
  contributed_value_int: number;
}

export interface LineageDetail {
  report_id: number;
  level: string;
  metrics: ReportMetric[];
  edges: LineageEdge[];
  contributions: MetricContribution[];
}

export interface ApprovalQueueItem {
  id: number;
  uuid: string;
  mine_id: number;
  bench_id: number;
  work_date: string;
  shift_code: string;
  status: string;
  production_milli_t: number;
  ob_milli_m3: number;
}

export function milliToDisplay(v: number, decimals = 3): string {
  return (v / 1000).toFixed(decimals);
}

export function bpToPercent(v: number): string {
  return (v / 100).toFixed(2) + "%";
}
