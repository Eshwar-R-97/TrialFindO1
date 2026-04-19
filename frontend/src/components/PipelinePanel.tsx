import { motion } from "framer-motion";
import { Check, AlertCircle, Loader2, Clock } from "lucide-react";
import type { StepState } from "../types";
import { cn } from "../lib/utils";

const STATUS_LABEL: Record<StepState["status"], string> = {
  idle: "IDLE",
  pending: "PENDING",
  running: "RUNNING",
  complete: "COMPLETE",
  error: "FAILED",
};

const STATUS_BADGE: Record<StepState["status"], string> = {
  idle: "bg-gray-100 text-gray-500 ring-gray-200",
  pending: "bg-gray-100 text-gray-500 ring-gray-200",
  running: "bg-brand-100 text-brand-700 ring-brand-200",
  complete: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  error: "bg-red-100 text-red-700 ring-red-200",
};

const CARD_CLASSES: Record<StepState["status"], string> = {
  idle: "bg-gray-50/60 border-gray-100",
  pending: "bg-gray-50/60 border-gray-100",
  running: "bg-brand-50/70 border-brand-200 shadow-[0_0_0_3px_rgba(29,158,117,0.06)]",
  complete: "bg-emerald-50/60 border-emerald-200",
  error: "bg-red-50/70 border-red-200",
};

const NUM_CLASSES: Record<StepState["status"], string> = {
  idle: "bg-gray-300",
  pending: "bg-gray-300",
  running: "bg-brand-500",
  complete: "bg-emerald-600",
  error: "bg-red-600",
};

function StatusIcon({ status }: { status: StepState["status"] }) {
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  if (status === "complete") return <Check className="h-3.5 w-3.5" strokeWidth={3} />;
  if (status === "error") return <AlertCircle className="h-3.5 w-3.5" />;
  return <Clock className="h-3.5 w-3.5" />;
}

export function StepCard({ state, index }: { state: StepState; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.04 }}
      className={cn(
        "rounded-xl border p-4 transition-colors",
        CARD_CLASSES[state.status]
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white",
            NUM_CLASSES[state.status],
            state.status === "running" && "animate-pulse-ring"
          )}
        >
          {state.step}
        </div>
        <h4 className="flex-1 text-[15px] font-semibold leading-tight tracking-tight text-gray-900">
          {state.title}
        </h4>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em] ring-1 ring-inset",
            STATUS_BADGE[state.status]
          )}
        >
          <StatusIcon status={state.status} />
          {STATUS_LABEL[state.status]}
        </span>
      </div>
      <p className="mt-2 pl-11 text-sm text-gray-500">{state.summary}</p>
    </motion.article>
  );
}

export function PipelinePanel({ steps }: { steps: StepState[] }) {
  return (
    <Panel title="Pipeline" subtitle="Four steps, each streams in real time.">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {steps.map((s, i) => (
          <StepCard key={s.step} state={s} index={i} />
        ))}
      </div>
    </Panel>
  );
}

// Shared Panel wrapper re-used by other sections
export function Panel({
  title,
  subtitle,
  action,
  children,
  countBadge,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  countBadge?: number;
}) {
  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <h3 className="text-base font-bold tracking-tight text-gray-900">{title}</h3>
          {countBadge !== undefined && countBadge > 0 && (
            <span className="inline-flex h-5 items-center justify-center rounded-full bg-brand-500 px-2 text-[11px] font-bold text-white">
              {countBadge}
            </span>
          )}
        </div>
        {subtitle && !action && (
          <p className="text-xs text-gray-400 sm:text-right">{subtitle}</p>
        )}
        {action && <div className="flex items-center gap-2">{action}</div>}
      </header>
      {children}
    </section>
  );
}
