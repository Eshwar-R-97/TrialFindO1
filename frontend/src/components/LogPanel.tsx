import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import type { LogLine } from "../types";
import { Panel } from "./PipelinePanel";
import { formatTimestamp } from "../lib/utils";

interface LogPanelProps {
  logs: LogLine[];
  onClear: () => void;
}

export function LogPanel({ logs, onClear }: LogPanelProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as new log lines arrive.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  return (
    <Panel
      title="Live activity"
      action={
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-slate-50 hover:text-foreground"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Clear
        </button>
      }
    >
      <div
        ref={ref}
        className="log-panel max-h-[360px] overflow-y-auto rounded-xl bg-[#0b1021] p-4 font-mono text-[12.5px] leading-relaxed text-slate-200 ring-1 ring-white/5"
      >
        {logs.length === 0 ? (
          <span className="text-slate-500">
            No activity yet. Click Find Trials to start.
          </span>
        ) : (
          logs.map((line) => (
            <span key={line.id} className={`log-line ${line.kind}`}>
              <span className="ts">{formatTimestamp(line.ts)}</span>
              {line.step != null && (
                <span className="step-tag">[Step {line.step}]</span>
              )}
              <span className="msg">{line.message}</span>
            </span>
          ))
        )}
      </div>
    </Panel>
  );
}
