export interface Contact {
  name: string;
  role: string;
  phone: string;
  email: string;
}

export interface Trial {
  nct_id?: string | null;
  nct_url?: string;
  mayo_url?: string;
  title: string;
  eligibility_criteria?: string;
  location?: string;
  sites_count?: number;
  phase?: string;
  summary?: string;
  source: string;
  contacts?: Contact[];
}

export interface Score {
  trial_index: number;
  match_score: number | null;
  match_level: "high" | "medium" | "low" | string;
  rationale: string;
  key_eligibility_factors: string[];
  potential_exclusions: string[];
  plain_english_summary: string;
}

export interface ScoredEntry {
  trial: Trial;
  score: Score;
}

export type StepStatus = "idle" | "pending" | "running" | "complete" | "error";

export interface StepState {
  step: 1 | 2 | 3;
  status: StepStatus;
  title: string;
  summary: string;
}

export type LogKind = "step-1" | "step-2" | "step-3" | "error" | "system";

export interface LogLine {
  id: number;
  step: number | null;
  message: string;
  ts: number;
  kind: LogKind;
}

export interface LogEvent {
  type: "log";
  step: number | null;
  message: string;
  ts: number;
}

export interface StepUpdateEvent {
  type: "step_update";
  step: 1 | 2 | 3;
  status: StepStatus;
  title?: string;
  summary?: string;
  ts: number;
}

export interface TrialAddedEvent {
  type: "trial_added";
  trial: Trial;
  ts: number;
}

export interface ScoredAddedEvent {
  type: "scored_added";
  entry: ScoredEntry;
  ts: number;
}

export interface PipelineResult {
  patient_profile: Record<string, unknown>;
  raw_trials: Trial[];
  scored_trials: ScoredEntry[];
  meta: {
    counts: Record<string, number>;
    errors: string[];
    elapsed_ms: number;
  };
}

export interface ResultEvent {
  type: "result";
  payload: PipelineResult;
}

export interface DoneEvent {
  type: "done";
  ts?: number;
}

export type SSEEvent =
  | LogEvent
  | StepUpdateEvent
  | TrialAddedEvent
  | ScoredAddedEvent
  | ResultEvent
  | DoneEvent;
