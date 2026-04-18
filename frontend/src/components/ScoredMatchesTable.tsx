import { Fragment, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, ExternalLink, MapPin } from "lucide-react";
import type { ScoredEntry } from "../types";
import { Panel } from "./PipelinePanel";
import {
  cn,
  eligibilitySnippet,
  firstSentence,
  trialLocationLabel,
  trialSourceUrl,
} from "../lib/utils";

function ScoreChip({
  score,
  level,
}: {
  score: number | string;
  level: string;
}) {
  const normalized = (level || "low").toLowerCase();
  const styles: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    medium: "bg-amber-100 text-amber-800 ring-amber-200",
    low: "bg-red-100 text-red-800 ring-red-200",
  };
  const levelClass = styles[normalized] ?? "bg-slate-100 text-slate-700 ring-slate-200";
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 rounded-lg px-2.5 py-1 text-sm font-bold ring-1 ring-inset",
        levelClass
      )}
    >
      {score}
      <span className="text-[10px] font-semibold uppercase tracking-[0.06em]">
        {normalized}
      </span>
    </span>
  );
}

function SourceTag({ source }: { source: string }) {
  return (
    <span className="inline-block rounded-md bg-sky-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.05em] text-sky-700">
      {source}
    </span>
  );
}

function DetailRow({ entry }: { entry: ScoredEntry }) {
  const { trial, score } = entry;
  const url = trialSourceUrl(trial);
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div className="space-y-3 bg-slate-50/70 px-5 py-5 text-[13.5px] leading-relaxed text-foreground">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
            Plain-English summary
          </p>
          <p className="mt-1 text-foreground">
            {score.plain_english_summary || "Not provided."}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
            Why this might or might not fit you
          </p>
          <p className="mt-1">{score.rationale || "Not provided."}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
              Key things you'd need
            </p>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-muted-foreground marker:text-slate-400">
              {(score.key_eligibility_factors?.length
                ? score.key_eligibility_factors
                : ["None provided"]
              ).map((f, i) => (
                <li key={i} className="text-foreground/90">
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
              Things that could disqualify you
            </p>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-muted-foreground marker:text-slate-400">
              {(score.potential_exclusions?.length
                ? score.potential_exclusions
                : ["None provided"]
              ).map((f, i) => (
                <li key={i} className="text-foreground/90">
                  {f}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
            Full eligibility text
          </p>
          <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
            {trial.eligibility_criteria || "Not provided."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-1 text-xs text-muted-foreground">
          <span>
            <span className="font-semibold text-foreground">Phase:</span>{" "}
            {trial.phase || "Unknown"}
          </span>
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md font-semibold text-brand-700 hover:underline"
            >
              View source <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </motion.div>
  );
}

interface ScoredMatchesTableProps {
  scored: ScoredEntry[];
  running: boolean;
}

export function ScoredMatchesTable({ scored, running }: ScoredMatchesTableProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  const toggle = (id: string) => setOpenId((cur) => (cur === id ? null : id));

  const getId = (e: ScoredEntry) =>
    `${e.score.trial_index}-${e.trial.nct_id ?? e.trial.title.slice(0, 24)}`;

  // Auto-open the top result when it arrives.
  const topId = scored.length > 0 ? getId(scored[0]) : null;
  if (topId && openId === null) {
    queueMicrotask(() => setOpenId(topId));
  }

  return (
    <Panel
      title="Scored matches"
      subtitle="Ranked best-fit first · click any row for plain-English details."
      countBadge={scored.length}
    >
      {scored.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-slate-50/60 px-4 py-6 text-center text-sm italic text-muted-foreground">
          {running
            ? "Scored matches will appear here as soon as Step 3 finishes."
            : "No scored matches yet. Click Find Trials above to run the pipeline."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-slate-50/80">
                  {[
                    { label: "Score", cls: "w-[110px] whitespace-nowrap" },
                    { label: "Source", cls: "w-[150px] whitespace-nowrap" },
                    { label: "Title", cls: "min-w-[280px]" },
                    { label: "One-line summary", cls: "min-w-[260px]" },
                    { label: "Location", cls: "min-w-[160px]" },
                    { label: "Eligibility", cls: "min-w-[240px]" },
                  ].map((c) => (
                    <th
                      key={c.label}
                      className={cn(
                        "px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground",
                        c.cls
                      )}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scored.map((entry) => {
                  const id = getId(entry);
                  const isOpen = openId === id;
                  const { trial, score } = entry;
                  const level = (score.match_level || "low").toLowerCase();
                  const summary = firstSentence(score.plain_english_summary) || "—";
                  const eligibility = eligibilitySnippet(trial.eligibility_criteria, 150);

                  return (
                    <Fragment key={id}>
                      <motion.tr
                        layout
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.22 }}
                        onClick={() => toggle(id)}
                        className={cn(
                          "cursor-pointer border-b border-slate-100 align-top transition-colors hover:bg-slate-50",
                          isOpen && "bg-blue-50/40"
                        )}
                      >
                        <td className="px-4 py-3.5">
                          <ScoreChip score={score.match_score ?? "–"} level={level} />
                        </td>
                        <td className="px-4 py-3.5">
                          <SourceTag source={trial.source || "Unknown"} />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex items-start gap-2">
                            <ChevronRight
                              className={cn(
                                "mt-0.5 h-4 w-4 shrink-0 text-slate-400 transition-transform",
                                isOpen && "rotate-90 text-blue-600"
                              )}
                            />
                            <div>
                              <p className="font-semibold leading-snug text-foreground">
                                {trial.title || "Untitled trial"}
                              </p>
                              {trial.nct_id && (
                                <p className="mt-0.5 text-[11px] font-medium text-slate-400">
                                  {trial.nct_id}
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-muted-foreground">{summary}</td>
                        <td className="px-4 py-3.5">
                          <span className="inline-flex items-start gap-1.5 text-muted-foreground">
                            <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                            <span>{trialLocationLabel(trial)}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-muted-foreground">
                          {eligibility}
                        </td>
                      </motion.tr>
                      <tr>
                        <td colSpan={6} className="p-0">
                          <AnimatePresence initial={false}>
                            {isOpen && <DetailRow entry={entry} />}
                          </AnimatePresence>
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
