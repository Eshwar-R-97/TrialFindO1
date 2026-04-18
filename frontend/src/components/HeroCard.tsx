import { AlertCircle } from "lucide-react";

interface HeroCardProps {
  statusText: string;
  errors: string[];
  elapsedMs: number | null;
  running: boolean;
}

const PATIENT_CHIPS = [
  { label: "Diagnosis", value: "Stage 3 breast cancer" },
  { label: "Age", value: "48" },
  { label: "Location", value: "Minneapolis, MN" },
  { label: "Prior treatment", value: "Chemotherapy" },
];

export function HeroCard({ statusText, errors, elapsedMs, running }: HeroCardProps) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-soft sm:p-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Demo patient
          </p>
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
            Matching recruiting trials to this profile
          </h2>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            Every step streams live — watch the pipeline collect, normalize, and score
            matching trials in real time.
          </p>
        </div>
        <div className="shrink-0 sm:text-right">
          <div className="inline-flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                running ? "bg-blue-500 animate-pulse" : "bg-slate-400"
              }`}
            />
            <span className="font-medium text-slate-700">{statusText}</span>
          </div>
          {elapsedMs !== null && !running && (
            <p className="mt-1 text-xs text-muted-foreground">
              Total elapsed {(elapsedMs / 1000).toFixed(1)}s
            </p>
          )}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {PATIENT_CHIPS.map((chip) => (
          <div
            key={chip.label}
            className="flex flex-col rounded-xl border border-border/70 bg-slate-50/70 px-3.5 py-2"
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
              {chip.label}
            </span>
            <span className="text-sm font-medium text-foreground">{chip.value}</span>
          </div>
        ))}
      </div>

      {errors.length > 0 && (
        <div className="mt-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3.5 text-sm text-red-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Partial failures</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-red-700">
              {errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
