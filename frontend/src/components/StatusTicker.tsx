import { AnimatePresence, motion } from "framer-motion";
import { Activity } from "lucide-react";
import type { LogLine } from "../types";
import { cn, formatTimestamp } from "../lib/utils";

interface StatusTickerProps {
  logs: LogLine[];
  running: boolean;
}

// Color chip per log "kind" — matches the step card colors so the eye can
// track which step the current event belongs to.
const CHIP_CLASSES: Record<LogLine["kind"], string> = {
  "step-1": "bg-emerald-100 text-emerald-700 ring-emerald-200",
  "step-2": "bg-amber-100 text-amber-800 ring-amber-200",
  "step-3": "bg-orange-100 text-orange-700 ring-orange-200",
  "step-4": "bg-pink-100 text-pink-700 ring-pink-200",
  error: "bg-red-100 text-red-700 ring-red-200",
  system: "bg-violet-100 text-violet-700 ring-violet-200",
};

const CHIP_LABEL: Record<LogLine["kind"], string> = {
  "step-1": "Step 1",
  "step-2": "Step 2",
  "step-3": "Step 3",
  "step-4": "Step 4",
  error: "Error",
  system: "System",
};

export function StatusTicker({ logs, running }: StatusTickerProps) {
  const latest = logs.length > 0 ? logs[logs.length - 1] : null;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft sm:p-6">
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "h-2.5 w-2.5 shrink-0 rounded-full",
            running ? "bg-emerald-500 animate-pulse-ring" : "bg-slate-300"
          )}
        />

        <div className="relative min-h-[1.25rem] flex-1 overflow-hidden">
          <AnimatePresence mode="popLayout" initial={false}>
            {latest ? (
              <motion.div
                key={latest.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.22, ease: "easeOut" }}
                className="flex items-center gap-2.5"
              >
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em] ring-1 ring-inset",
                    CHIP_CLASSES[latest.kind]
                  )}
                >
                  {CHIP_LABEL[latest.kind]}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                  {formatTimestamp(latest.ts)}
                </span>
                <span
                  className="truncate text-sm text-foreground"
                  title={latest.message}
                >
                  {latest.message}
                </span>
              </motion.div>
            ) : (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-2 text-sm text-muted-foreground"
              >
                <Activity className="h-4 w-4" />
                <span>Idle — click Find Trials to begin.</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
