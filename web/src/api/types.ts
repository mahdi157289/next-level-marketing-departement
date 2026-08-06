export interface Lead {
  id: string;
  name: string | null;
  url: string | null;
  country: string | null;
  industry: string | null;
  business_type: string | null;
  email: string | null;
  phone: string | null;
  seo_score: number | null;
  lead_score: number | null;
  status: string | null;
  status_notes: string | null;
  source: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LeadEvent {
  id: string;
  lead_id: string;
  agent_run_id: string | null;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface LeadDetail extends Lead {
  events: LeadEvent[];
}

export interface AgentRun {
  id: string;
  pipeline_run_id: string;
  agent_name: string;
  model: string | null;
  status: string | null;
  input_summary: string | null;
  output_summary: string | null;
  output_json: Record<string, unknown> | null;
  apis_consumed: Array<Record<string, unknown>> | null;
  records_processed: number | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineRun {
  id: string;
  trigger: string | null;
  seed_query: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  meta: Record<string, unknown> | null;
  agent_run_count?: number;
}

export interface ToolInfo {
  id: string;
  label: string;
  agents: string[];
}

export interface AgentProfile {
  agent_name: string;
  display_name: string;
  mission_prompt: string;
  enabled_tools: string[];
  model: string | null;
  default_seed_query: string | null;
  updated_at: string | null;
  available_tools: ToolInfo[];
}

export interface Stats {
  leads_total: number;
  leads_by_status: Record<string, number>;
  leads_avg_score: number;
  runs_today: number;
  run_success_rate: number;
  recent_runs: Array<{
    id: string;
    trigger: string | null;
    seed_query: string | null;
    status: string | null;
    started_at: string | null;
  }>;
  scout_active: boolean;
  scout_last_seed: string | null;
}

export interface ScoutStatus {
  scout_active: boolean;
  scout_last_seed: string | null;
  latest_missions: PipelineRun[];
}

export interface ScoutThread {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ScoutMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "tool";
  content: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: { result?: unknown; error?: string | null } | Record<string, unknown> | null;
  created_at: string | null;
}

export interface DiscoveryStartOut {
  pipeline_run_id: string;
  status: string;
  seed_query: string;
  note?: string | null;
}

export interface DiscoveryFinishOut {
  pipeline_run_id: string;
  status: string;
}
