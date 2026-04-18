import { useCallback, useEffect, useRef, useState } from "react";
import type {
  LogLine,
  PipelineResult,
  SSEEvent,
  ScoredEntry,
  StepState,
  Trial,
} from "../types";

const INITIAL_STEPS: StepState[] = [
  { step: 1, status: "idle", title: "ClinicalTrials.gov API", summary: "Waiting to start." },
  { step: 2, status: "idle", title: "Mayo Clinic browser agent (Tinyfish)", summary: "Waiting to start." },
  { step: 3, status: "idle", title: "Featherless AI scoring", summary: "Waiting to start." },
];

function logKind(message: string, step: number | null): LogLine["kind"] {
  const lower = (message || "").toLowerCase();
  if (lower.includes("failed") || lower.includes("crashed") || lower.startsWith("error")) {
    return "error";
  }
  if (step === 1) return "step-1";
  if (step === 2) return "step-2";
  if (step === 3) return "step-3";
  return "system";
}

export interface TrialStream {
  running: boolean;
  steps: StepState[];
  logs: LogLine[];
  rawTrials: Trial[];
  scored: ScoredEntry[];
  elapsedMs: number | null;
  errors: string[];
  statusText: string;
  start: () => void;
  clearLogs: () => void;
}

export function useTrialStream(): TrialStream {
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepState[]>(INITIAL_STEPS);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [rawTrials, setRawTrials] = useState<Trial[]>([]);
  const [scored, setScored] = useState<ScoredEntry[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [statusText, setStatusText] = useState<string>(
    "Click Find Trials to start the pipeline."
  );

  const sourceRef = useRef<EventSource | null>(null);
  const logIdRef = useRef(0);
  const finalPayloadRef = useRef<PipelineResult | null>(null);

  const clearLogs = useCallback(() => setLogs([]), []);

  const start = useCallback(() => {
    sourceRef.current?.close();

    setRunning(true);
    setSteps(INITIAL_STEPS);
    setLogs([]);
    setRawTrials([]);
    setScored([]);
    setElapsedMs(null);
    setErrors([]);
    setStatusText("Running Step 1 → Step 2 → Step 3 …");
    finalPayloadRef.current = null;

    const es = new EventSource("/find-trials-stream");
    sourceRef.current = es;

    es.onmessage = (event) => {
      let data: SSEEvent;
      try {
        data = JSON.parse(event.data) as SSEEvent;
      } catch {
        return;
      }

      switch (data.type) {
        case "log": {
          setLogs((prev) => [
            ...prev,
            {
              id: ++logIdRef.current,
              step: data.step,
              message: data.message,
              ts: data.ts,
              kind: logKind(data.message, data.step),
            },
          ]);
          break;
        }
        case "step_update": {
          setSteps((prev) =>
            prev.map((s) =>
              s.step === data.step
                ? {
                    ...s,
                    status: data.status,
                    title: data.title || s.title,
                    summary: data.summary || s.summary,
                  }
                : s
            )
          );
          break;
        }
        case "trial_added": {
          setRawTrials((prev) => [...prev, data.trial]);
          break;
        }
        case "scored_added": {
          setScored((prev) =>
            [...prev, data.entry].sort(
              (a, b) => (b.score.match_score ?? -1) - (a.score.match_score ?? -1)
            )
          );
          break;
        }
        case "result": {
          finalPayloadRef.current = data.payload;
          setElapsedMs(data.payload.meta?.elapsed_ms ?? null);
          setErrors(data.payload.meta?.errors ?? []);
          break;
        }
        case "done": {
          es.close();
          sourceRef.current = null;
          setRunning(false);
          const meta = finalPayloadRef.current?.meta;
          const elapsed = meta?.elapsed_ms ?? 0;
          const rawCount = meta?.counts?.total_raw ?? 0;
          const scoredCount = meta?.counts?.total_scored ?? 0;
          setStatusText(
            `Done in ${(elapsed / 1000).toFixed(1)}s · ${rawCount} raw trial${
              rawCount === 1 ? "" : "s"
            } · ${scoredCount} scored`
          );
          break;
        }
      }
    };

    es.onerror = () => {
      es.close();
      sourceRef.current = null;
      setRunning(false);
      if (!finalPayloadRef.current) {
        setStatusText("Stream connection failed before completion.");
      }
    };
  }, []);

  // Cleanup on unmount.
  useEffect(() => () => sourceRef.current?.close(), []);

  return {
    running,
    steps,
    logs,
    rawTrials,
    scored,
    elapsedMs,
    errors,
    statusText,
    start,
    clearLogs,
  };
}
