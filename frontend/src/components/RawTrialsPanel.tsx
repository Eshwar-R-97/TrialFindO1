import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, ExternalLink, FlaskConical, MapPin } from "lucide-react";
import type { Trial } from "../types";
import { Panel } from "./PipelinePanel";
import {
  cn,
  firstSentence,
  trialLocationLabel,
  trialSourceUrl,
} from "../lib/utils";

function RawTrialCard({ trial }: { trial: Trial }) {
  const [open, setOpen] = useState(false);
  const url = trialSourceUrl(trial);

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "rounded-xl border bg-white transition-all",
        open ? "border-blue-200 shadow-soft" : "border-border hover:border-slate-300"
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <ChevronRight
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-slate-400 transition-transform",
            open && "rotate-90 text-blue-600"
          )}
        />
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-sky-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.05em] text-sky-700">
              {trial.source || "Unknown"}
            </span>
            <h4 className="flex-1 text-[15px] font-semibold leading-snug tracking-tight text-foreground">
              {trial.title || "Untitled trial"}
            </h4>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {trialLocationLabel(trial)}
            </span>
            <span className="inline-flex items-center gap-1">
              <FlaskConical className="h-3 w-3" />
              Phase: {trial.phase || "Unknown"}
            </span>
            {trial.nct_id && <span>ID: {trial.nct_id}</span>}
          </div>
          <p className="text-[13.5px] leading-relaxed text-foreground/80">
            {firstSentence(trial.summary) || "No short summary available."}
          </p>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-3 border-t border-border bg-slate-50/60 px-5 py-4 text-[13.5px] leading-relaxed">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
                  Full summary
                </p>
                <p className="mt-1 whitespace-pre-wrap text-foreground/90">
                  {trial.summary || "Not provided."}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
                  Eligibility criteria
                </p>
                <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                  {trial.eligibility_criteria || "Not provided."}
                </p>
              </div>
              {url && (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline"
                >
                  View source <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function RawTrialsPanel({ rawTrials }: { rawTrials: Trial[] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Panel
      title="Raw trial data"
      subtitle="Unscored records from each source, pre-normalized."
      countBadge={rawTrials.length}
    >
      {rawTrials.length === 0 ? (
        <p className="text-sm text-muted-foreground">No raw trials yet.</p>
      ) : (
        <div>
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="mb-3 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
          >
            <ChevronRight
              className={cn(
                "h-4 w-4 transition-transform",
                expanded && "rotate-90"
              )}
            />
            {expanded ? "Hide" : "Show"} {rawTrials.length} raw trial
            {rawTrials.length === 1 ? "" : "s"}
          </button>

          <AnimatePresence initial={false}>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="space-y-2.5 pt-1">
                  {rawTrials.map((t, i) => (
                    <RawTrialCard key={`${t.source}-${t.nct_id ?? i}`} trial={t} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </Panel>
  );
}
