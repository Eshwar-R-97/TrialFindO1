import { Loader2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import type { PatientProfileExtracted } from "../types";

export interface PatientProfileGapFormProps {
  missingFields: string[];
  current: PatientProfileExtracted;
  onSave: (patch: Record<string, string | number | string[]>) => Promise<void>;
}

/** Collect ZIP, condition (diagnosis / cancer type), or age when the PDF parse left gaps. */
export function PatientProfileGapForm({
  missingFields,
  current,
  onSave,
}: PatientProfileGapFormProps) {
  const [zip, setZip] = useState(() =>
    (current.zip_code || "").replace(/\D/g, "").slice(0, 5)
  );
  const [diagnosis, setDiagnosis] = useState(() => current.diagnosis || "");
  const [cancerType, setCancerType] = useState(() => current.cancer_type || "");
  const [age, setAge] = useState(
    () => (current.age != null ? String(current.age) : "")
  );
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const needZip = missingFields.includes("zip_code");
  const needCondition = missingFields.includes("condition");
  const needAge = missingFields.includes("age");

  const showForm = needZip || needCondition || needAge;

  const canSubmit = useMemo(() => {
    if (needZip && zip.replace(/\D/g, "").length !== 5) return false;
    if (needCondition && !diagnosis.trim() && !cancerType.trim()) return false;
    if (needAge) {
      const n = parseInt(age, 10);
      if (Number.isNaN(n) || n < 1 || n > 120) return false;
    }
    return true;
  }, [needZip, needCondition, needAge, zip, diagnosis, cancerType, age]);

  const submit = useCallback(async () => {
    setLocalError(null);
    const patch: Record<string, string | number | string[]> = {};
    if (needZip) {
      const d = zip.replace(/\D/g, "").slice(0, 5);
      if (d.length !== 5) {
        setLocalError("Enter a valid 5-digit US ZIP code.");
        return;
      }
      patch.zip_code = d;
    }
    if (needCondition) {
      if (!diagnosis.trim() && !cancerType.trim()) {
        setLocalError("Enter a diagnosis and/or cancer type.");
        return;
      }
      if (diagnosis.trim()) patch.diagnosis = diagnosis.trim();
      if (cancerType.trim()) patch.cancer_type = cancerType.trim();
    }
    if (needAge) {
      const n = parseInt(age, 10);
      if (Number.isNaN(n) || n < 1 || n > 120) {
        setLocalError("Enter a valid age (1–120).");
        return;
      }
      patch.age = n;
    }
    setSaving(true);
    try {
      await onSave(patch);
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [
    needZip,
    needCondition,
    needAge,
    zip,
    diagnosis,
    cancerType,
    age,
    onSave,
  ]);

  if (!showForm) return null;

  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50/90 p-4 text-sm text-slate-800">
      <p className="font-semibold text-slate-900">Complete your profile</p>
      <p className="mt-1 text-muted-foreground">
        We couldn’t get everything from the document alone. Add the details below so
        we can search trials near you and match your condition.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {needZip && (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              US ZIP code (required for nearby trials)
            </span>
            <input
              className="rounded-lg border border-border bg-white px-3 py-2 text-foreground outline-none ring-sky-300 focus:ring-2"
              inputMode="numeric"
              maxLength={5}
              placeholder="e.g. 55401"
              value={zip}
              onChange={(e) => setZip(e.target.value.replace(/\D/g, "").slice(0, 5))}
            />
          </label>
        )}
        {needCondition && (
          <>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Diagnosis (plain language)
              </span>
              <input
                className="rounded-lg border border-border bg-white px-3 py-2 text-foreground outline-none ring-sky-300 focus:ring-2"
                placeholder="e.g. Stage IIIB non-small cell lung cancer"
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Cancer type (short, e.g. lung, breast)
              </span>
              <input
                className="rounded-lg border border-border bg-white px-3 py-2 text-foreground outline-none ring-sky-300 focus:ring-2"
                placeholder="e.g. lung"
                value={cancerType}
                onChange={(e) => setCancerType(e.target.value)}
              />
            </label>
          </>
        )}
        {needAge && (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Age
            </span>
            <input
              className="rounded-lg border border-border bg-white px-3 py-2 text-foreground outline-none ring-sky-300 focus:ring-2"
              inputMode="numeric"
              placeholder="e.g. 67"
              value={age}
              onChange={(e) => setAge(e.target.value.replace(/\D/g, "").slice(0, 3))}
            />
          </label>
        )}
      </div>
      {localError && (
        <p className="mt-3 text-sm text-red-700">{localError}</p>
      )}
      <button
        type="button"
        disabled={!canSubmit || saving}
        onClick={() => void submit()}
        className="mt-4 inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Save for trial search
      </button>
    </div>
  );
}
