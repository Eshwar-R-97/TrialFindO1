import { AnimatePresence, motion } from "framer-motion";
import { Activity, Search, Sparkles } from "lucide-react";
import type { FriendlyStatus } from "../types";
import { cn } from "../lib/utils";

interface StatusTickerProps {
  friendlyStatus: FriendlyStatus | null;
  running: boolean;
  trialsFound: number;
  scoredCount: number;
}

function CounterPill({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "brand" | "emerald";
}) {
  const tones = {
    brand: "bg-brand-50 text-brand-700 ring-brand-100",
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  };
  return (
    <div
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset",
        tones[tone]
      )}
    >
      {icon}
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 6 }}
          transition={{ duration: 0.18 }}
          className="tabular-nums"
        >
          {value}
        </motion.span>
      </AnimatePresence>
      <span className="font-medium opacity-70">{label}</span>
    </div>
  );
}

export function StatusTicker({
  friendlyStatus,
  running,
  trialsFound,
  scoredCount,
}: StatusTickerProps) {
  const showIdleRunning = running && !friendlyStatus;
  const showIdle = !running && !friendlyStatus;
  const showCounters = running || trialsFound > 0 || scoredCount > 0;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex items-center gap-4">
        <span
          className={cn(
            "h-2.5 w-2.5 shrink-0 rounded-full",
            running ? "animate-pulse-ring bg-brand-500" : "bg-gray-200"
          )}
        />

        <div className="relative min-h-[1.25rem] min-w-0 flex-1 overflow-hidden">
          <AnimatePresence mode="popLayout" initial={false}>
            {friendlyStatus ? (
              <motion.div
                key={`f-${friendlyStatus.id}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.22, ease: "easeOut" }}
              >
                <span className="truncate text-sm text-gray-800" title={friendlyStatus.message}>
                  {friendlyStatus.message}
                </span>
              </motion.div>
            ) : showIdleRunning ? (
              <motion.div
                key="warming"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="text-sm text-gray-500"
              >
                Getting your search started…
              </motion.div>
            ) : showIdle ? (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-2 text-sm text-gray-400"
              >
                <Activity className="h-4 w-4" />
                <span>Idle — click Find Trials to begin.</span>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>

        {showCounters && (
          <div className="hidden shrink-0 items-center gap-2 sm:flex">
            <CounterPill
              tone="brand"
              icon={<Search className="h-3.5 w-3.5" />}
              value={trialsFound}
              label={trialsFound === 1 ? "trial found" : "trials found"}
            />
            <CounterPill
              tone="emerald"
              icon={<Sparkles className="h-3.5 w-3.5" />}
              value={scoredCount}
              label={scoredCount === 1 ? "match scored" : "matches scored"}
            />
          </div>
        )}
      </div>
    </div>
  );
}
