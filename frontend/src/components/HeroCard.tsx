import { AlertCircle } from "lucide-react";
import type { PatientProfileExtracted } from "../types";

interface HeroCardProps {
  errors: string[];
  patientProfile?: PatientProfileExtracted | null;
}

function chipsFromProfile(p: PatientProfileExtracted) {
  const name = [p.first_name, p.last_name].filter(Boolean).join(" ").trim();
  const priors = Array.isArray(p.prior_treatments)
    ? p.prior_treatments.join(", ")
    : "—";
  return [
    { label: "Name", value: name || "—" },
    { label: "Diagnosis", value: p.diagnosis || "—" },
    { label: "Cancer / stage", value: [p.cancer_type, p.stage].filter(Boolean).join(" · ") || "—" },
    { label: "Age", value: p.age != null ? String(p.age) : "—" },
    { label: "Location", value: p.zip_code ? `ZIP ${p.zip_code}` : "—" },
    { label: "Prior treatment", value: priors },
  ];
}

export function HeroCard({ errors, patientProfile }: HeroCardProps) {
  if (!patientProfile) return null;

  const chips = chipsFromProfile(patientProfile);

  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <p className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-brand-500">
          Patient profile · from PDF
        </p>
        <h3 className="text-xl font-bold tracking-tight text-gray-900 sm:text-2xl">
          Matching recruiting trials to this profile
        </h3>
        <p className="mt-2 max-w-prose text-sm text-gray-500">
          Every step streams live — watch the pipeline collect, normalize, and score
          matching trials in real time.
        </p>
      </div>

      <div className="mt-6 flex flex-wrap gap-2.5">
        {chips.map((chip) => (
          <div
            key={chip.label}
            className="flex flex-col rounded-xl border border-gray-100 bg-gray-50 px-4 py-2.5"
          >
            <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
              {chip.label}
            </span>
            <span className="mt-0.5 text-sm font-semibold text-gray-900">{chip.value}</span>
          </div>
        ))}
      </div>

      {errors.length > 0 && (
        <div className="mt-5 flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
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
