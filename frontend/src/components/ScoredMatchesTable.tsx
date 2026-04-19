import { Fragment, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  MapPin,
} from "lucide-react";
import type { GeoPoint, ScoredEntry, Trial } from "../types";
import { Panel } from "./PipelinePanel";
import { ContactCell, ContactList } from "./Contacts";
import {
  cn,
  eligibilitySnippet,
  firstSentence,
  formatMiles,
  haversineMiles,
  trialLocationLabel,
  trialSourceUrl,
} from "../lib/utils";

interface MatchRow {
  trial: Trial;
  scored: ScoredEntry | null;
  arrivalIdx: number;
  /** Miles from the patient's anchor lat/lng, or null if unknown. */
  distanceMi: number | null;
}

// Single source of truth for the table's row ordering. We always sort by
// exactly one column at a time; the string form makes the UI trivial to
// drive and keeps the sort comparator easy to read.
//   - score-desc (DEFAULT): highest match score first, unscored rows at
//     the bottom in arrival order.
//   - score-asc: lowest match score first (unscored still bottom).
//   - distance-asc: closest to the patient first; no-geo rows at bottom.
//   - distance-desc: farthest first; no-geo rows at bottom.
type SortMode = "score-desc" | "score-asc" | "distance-asc" | "distance-desc";

const DEFAULT_SORT: SortMode = "score-desc";

// Score header click: flip between the two score directions, always
// leaving "distance-*" states on Location clicks.
function toggleScoreSort(cur: SortMode): SortMode {
  return cur === "score-desc" ? "score-asc" : "score-desc";
}

// Location header click: first click starts a distance sort (closest),
// second flips to farthest, third hands control back to the default
// score ordering. This matches the Score toggle's two-state feel while
// still offering an obvious "turn it off" path.
function toggleDistanceSort(cur: SortMode): SortMode {
  if (cur === "distance-asc") return "distance-desc";
  if (cur === "distance-desc") return DEFAULT_SORT;
  return "distance-asc";
}

function ScoreChip({
  score,
  level,
  reason,
}: {
  score: number | string;
  level: string;
  reason?: string;
}) {
  const normalized = (level || "low").toLowerCase();
  const styles: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    medium: "bg-amber-100 text-amber-800 ring-amber-200",
    low: "bg-red-100 text-red-800 ring-red-200",
  };
  const levelClass = styles[normalized] ?? "bg-gray-100 text-gray-700 ring-gray-200";
  return (
    <motion.span
      layout
      initial={{ scale: 0.85, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
      title={reason || undefined}
      className={cn(
        "inline-flex items-baseline gap-1.5 rounded-lg px-2.5 py-1 text-sm font-bold ring-1 ring-inset",
        levelClass
      )}
    >
      {score}
      <span className="text-[10px] font-semibold uppercase tracking-[0.06em]">
        {normalized}
      </span>
    </motion.span>
  );
}

function ScoringPill() {
  return (
    <motion.span
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.05em] text-brand-700 ring-1 ring-inset ring-brand-200"
    >
      <Loader2 className="h-3 w-3 animate-spin" />
      Scoring…
    </motion.span>
  );
}

// Shared clickable-header button used by both the Score and Location
// columns. It knows nothing about the underlying data — callers just pass
// which sort directions "belong" to this column and which (if any) is
// currently active, and we render the label + arrow + active styling.
interface SortHeaderProps {
  label: string;
  ascLabel: string;
  descLabel: string;
  /** Currently-active direction on THIS column, or null if another column owns the sort. */
  direction: "asc" | "desc" | null;
  disabled?: boolean;
  disabledTitle?: string;
  enabledTitle?: string;
  onToggle: () => void;
}

function SortHeader({
  label,
  ascLabel,
  descLabel,
  direction,
  disabled = false,
  disabledTitle,
  enabledTitle,
  onToggle,
}: SortHeaderProps) {
  const Icon =
    direction === "asc" ? ArrowUp : direction === "desc" ? ArrowDown : ArrowUpDown;
  const displayLabel =
    direction === "asc" ? ascLabel : direction === "desc" ? descLabel : label;
  const active = direction !== null;
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      title={disabled ? disabledTitle : enabledTitle}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 -ml-1.5 text-[11px] font-bold uppercase tracking-[0.07em] transition-colors",
        active
          ? "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200"
          : "text-gray-400 hover:bg-gray-100 hover:text-gray-600",
        disabled && "cursor-not-allowed opacity-50 hover:bg-transparent"
      )}
    >
      {displayLabel}
      <Icon className="h-3 w-3" />
    </button>
  );
}

function DistanceChip({ miles }: { miles: number }) {
  return (
    <motion.span
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className="mt-1 inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-semibold text-gray-600 ring-1 ring-inset ring-gray-200"
    >
      {formatMiles(miles)} away
    </motion.span>
  );
}

function SourceTag({ source }: { source: string }) {
  return (
    <span className="inline-block rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.05em] text-brand-700">
      {source}
    </span>
  );
}

function DetailRow({ row }: { row: MatchRow }) {
  const { trial, scored } = row;
  const score = scored?.score;
  const url = trialSourceUrl(trial);

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div className="space-y-4 border-t border-gray-100 bg-gray-50/60 px-5 py-5 text-[13.5px] leading-relaxed text-gray-800">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-gray-400">
            Plain-English summary
          </p>
          <p className="mt-1.5 text-gray-800">
            {score?.plain_english_summary ||
              trial.summary ||
              "Scoring in progress — a plain-English summary will appear once review finishes."}
          </p>
        </div>

        {score ? (
          <>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-gray-400">
                Why this might or might not fit you
              </p>
              <p className="mt-1.5">{score.rationale || "Not provided."}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-gray-400">
                  Key things you'd need
                </p>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 marker:text-gray-300">
                  {(score.key_eligibility_factors?.length
                    ? score.key_eligibility_factors
                    : ["None provided"]
                  ).map((f, i) => (
                    <li key={i} className="text-gray-700">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-gray-400">
                  Things that could disqualify you
                </p>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 marker:text-gray-300">
                  {(score.potential_exclusions?.length
                    ? score.potential_exclusions
                    : ["None provided"]
                  ).map((f, i) => (
                    <li key={i} className="text-gray-700">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-[12.5px] font-medium text-brand-800">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Our AI is reviewing this trial — the rationale and fit details will fill in shortly.
          </div>
        )}

        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.07em] text-gray-400">
            Study contacts
          </p>
          <div className="mt-1.5">
            <ContactList contacts={trial.contacts} />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 pt-1 text-xs text-gray-400">
          <span>
            <span className="font-semibold text-gray-700">Phase:</span>{" "}
            {trial.phase || "Unknown"}
          </span>
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline"
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
  rawTrials: Trial[];
  scored: ScoredEntry[];
  running: boolean;
  /** Patient anchor lat/lng; null until the backend emits `patient_geo`. */
  patientGeo?: GeoPoint | null;
}

export function ScoredMatchesTable({
  rawTrials,
  scored,
  running,
  patientGeo,
}: ScoredMatchesTableProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>(DEFAULT_SORT);

  // Derive per-column "am I active, and in which direction?" flags for the
  // SortHeader buttons. Exactly one of these is non-null at any time.
  const scoreDirection: "asc" | "desc" | null =
    sortMode === "score-desc" ? "desc" : sortMode === "score-asc" ? "asc" : null;
  const distanceDirection: "asc" | "desc" | null =
    sortMode === "distance-asc"
      ? "asc"
      : sortMode === "distance-desc"
      ? "desc"
      : null;

  const scoredByIndex = useMemo(() => {
    const m = new Map<number, ScoredEntry>();
    for (const entry of scored) {
      m.set(entry.score.trial_index, entry);
    }
    return m;
  }, [scored]);

  const rows: MatchRow[] = useMemo(() => {
    const all: MatchRow[] = rawTrials.map((trial, idx) => {
      const geo = trial.geo;
      const distanceMi =
        patientGeo && geo ? haversineMiles(patientGeo, geo) : null;
      return {
        trial,
        scored: scoredByIndex.get(idx) ?? null,
        arrivalIdx: idx,
        distanceMi,
      };
    });

    if (sortMode === "distance-asc" || sortMode === "distance-desc") {
      // Rows with no distance (no coords from source) always sink to the
      // bottom so the user still sees them but they don't pollute the
      // ordered-by-distance section.
      return all.sort((a, b) => {
        const aHas = a.distanceMi != null;
        const bHas = b.distanceMi != null;
        if (aHas !== bHas) return aHas ? -1 : 1;
        if (!aHas && !bHas) return a.arrivalIdx - b.arrivalIdx;
        const diff = (a.distanceMi as number) - (b.distanceMi as number);
        return sortMode === "distance-asc" ? diff : -diff;
      });
    }

    // Score modes: unscored rows always sink to the bottom (by arrival) —
    // a "still scoring" row isn't a low score, it's unknown, so we don't
    // want it mixed in regardless of direction. Among scored rows the
    // direction flag flips the compare.
    const dir = sortMode === "score-desc" ? -1 : 1;
    return all.sort((a, b) => {
      const aScored = a.scored !== null;
      const bScored = b.scored !== null;
      if (aScored !== bScored) return aScored ? -1 : 1;
      if (aScored && bScored) {
        const aScore = a.scored!.score.match_score ?? 0;
        const bScore = b.scored!.score.match_score ?? 0;
        return dir * (aScore - bScore);
      }
      return a.arrivalIdx - b.arrivalIdx;
    });
  }, [rawTrials, scoredByIndex, sortMode, patientGeo]);

  const toggle = (id: string) => setOpenId((cur) => (cur === id ? null : id));
  const getId = (row: MatchRow) =>
    `${row.arrivalIdx}-${row.trial.nct_id ?? row.trial.title.slice(0, 24)}`;

  const scoredCount = scored.length;
  const pendingCount = rawTrials.length - scoredCount;

  const subtitleParts: string[] = [];
  if (rawTrials.length > 0) {
    subtitleParts.push(
      `${scoredCount} scored${pendingCount > 0 ? ` · ${pendingCount} reviewing…` : ""}`
    );
  }
  subtitleParts.push("Click any row for plain-English details.");

  return (
    <Panel title="Matches" subtitle={subtitleParts.join(" · ")} countBadge={rawTrials.length}>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-gray-200 bg-gray-50/60 px-4 py-8 text-center text-sm italic text-gray-400">
          {running
            ? "Trials will appear here the moment each source returns — scores fill in as our AI reviews each one."
            : "No matches yet. Click Find Trials above to run the pipeline."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/80">
                  <th className="w-[120px] whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    <SortHeader
                      label="Score"
                      ascLabel="Score · lowest first"
                      descLabel="Score · highest first"
                      direction={scoreDirection}
                      enabledTitle="Click to flip highest ↔ lowest score"
                      onToggle={() => setSortMode(toggleScoreSort)}
                    />
                  </th>
                  <th className="w-[140px] whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    Source
                  </th>
                  <th className="min-w-[280px] px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    Title
                  </th>
                  <th className="min-w-[240px] px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    One-line summary
                  </th>
                  <th className="min-w-[180px] px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    <SortHeader
                      label="Location"
                      ascLabel="Location · closest first"
                      descLabel="Location · farthest first"
                      direction={distanceDirection}
                      disabled={!patientGeo}
                      disabledTitle="Waiting for your location from the uploaded report…"
                      enabledTitle="Click to sort by distance from your location"
                      onToggle={() => setSortMode(toggleDistanceSort)}
                    />
                  </th>
                  <th className="min-w-[200px] px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    Contact
                  </th>
                  <th className="min-w-[220px] px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.07em] text-gray-400">
                    Eligibility
                  </th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {rows.map((row) => {
                    const id = getId(row);
                    const isOpen = openId === id;
                    const { trial, scored: entryScored } = row;
                    const score = entryScored?.score;
                    const level = (score?.match_level || "low").toLowerCase();
                    const summary =
                      firstSentence(score?.plain_english_summary) ||
                      firstSentence(trial.summary) ||
                      (entryScored ? "—" : "Scoring…");
                    const eligibility = eligibilitySnippet(trial.eligibility_criteria, 150);

                    return (
                      <Fragment key={id}>
                        <motion.tr
                          layout
                          initial={{ opacity: 0, y: -6 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.25 }}
                          onClick={() => toggle(id)}
                          className={cn(
                            "cursor-pointer border-b border-gray-50 align-top transition-colors hover:bg-brand-50/30",
                            isOpen && "bg-brand-50/40",
                            !entryScored && "bg-gray-50/30"
                          )}
                        >
                          <td className="px-4 py-3.5">
                            {score ? (
                              <div className="flex flex-col gap-1.5">
                                <ScoreChip
                                  score={score.match_score ?? "–"}
                                  level={level}
                                  reason={score.score_reason}
                                />
                                {score.score_reason && (
                                  <p className="text-[11px] leading-snug text-gray-500">
                                    {score.score_reason}
                                  </p>
                                )}
                              </div>
                            ) : (
                              <ScoringPill />
                            )}
                          </td>
                          <td className="px-4 py-3.5">
                            <SourceTag source={trial.source || "Unknown"} />
                          </td>
                          <td className="px-4 py-3.5">
                            <div className="flex items-start gap-2">
                              <ChevronRight
                                className={cn(
                                  "mt-0.5 h-4 w-4 shrink-0 text-gray-300 transition-transform",
                                  isOpen && "rotate-90 text-brand-500"
                                )}
                              />
                              <div>
                                <p className="font-semibold leading-snug text-gray-900">
                                  {trial.title || "Untitled trial"}
                                </p>
                                {trial.nct_id && (
                                  <p className="mt-0.5 text-[11px] font-medium text-gray-400">
                                    {trial.nct_id}
                                  </p>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 text-gray-500">{summary}</td>
                          <td className="px-4 py-3.5">
                            <div className="flex flex-col items-start gap-0.5">
                              <span className="inline-flex items-start gap-1.5 text-gray-500">
                                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-300" />
                                <span>{trialLocationLabel(trial)}</span>
                              </span>
                              {row.distanceMi != null && (
                                <DistanceChip miles={row.distanceMi} />
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3.5">
                            <ContactCell contacts={trial.contacts} />
                          </td>
                          <td className="px-4 py-3.5 text-gray-500">{eligibility}</td>
                        </motion.tr>
                        <tr>
                          <td colSpan={7} className="p-0">
                            <AnimatePresence initial={false}>
                              {isOpen && <DetailRow row={row} />}
                            </AnimatePresence>
                          </td>
                        </tr>
                      </Fragment>
                    );
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
