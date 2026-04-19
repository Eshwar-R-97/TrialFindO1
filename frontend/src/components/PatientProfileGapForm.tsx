import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Loader2, Lock, Shield } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import type { PatientProfileExtracted } from "../types";

export interface PatientProfileGapFormProps {
  current: PatientProfileExtracted;
  onSave: (patch: Record<string, string | number | string[]>) => Promise<void>;
}

// ── Field definitions ─────────────────────────────────────────────────────────

type FieldType = "text" | "number" | "zip" | "tags" | "select";

interface FieldDef {
  key: keyof PatientProfileExtracted;
  label: string;
  type: FieldType;
  placeholder: string;
  hint: string;
  options?: string[];
}

const PERFORMANCE_STATUS_OPTIONS = [
  "0 – Fully active, no restrictions",
  "1 – Restricted strenuous activity, light work ok",
  "2 – Ambulatory, capable of self-care, no work",
  "3 – Limited self-care, confined to bed/chair >50% of day",
  "4 – Completely disabled, no self-care",
];

const FIELD_GROUPS: { group: string; fields: FieldDef[] }[] = [
  {
    group: "Basic Information",
    fields: [
      {
        key: "age",
        label: "Age",
        type: "number",
        placeholder: "67",
        hint: "Many trials have minimum and maximum age requirements.",
      },
      {
        key: "zip_code",
        label: "ZIP Code",
        type: "zip",
        placeholder: "55401",
        hint: "Lets us surface trials within travel distance.",
      },
    ],
  },
  {
    group: "Diagnosis",
    fields: [
      {
        key: "diagnosis",
        label: "Full Diagnosis",
        type: "text",
        placeholder: "e.g. Stage IIIB non-small cell lung cancer",
        hint: "Your primary diagnosis as written in your records.",
      },
      {
        key: "cancer_type",
        label: "Cancer Type",
        type: "text",
        placeholder: "e.g. lung, breast, colorectal",
        hint: "Short name used to filter trials by indication.",
      },
      {
        key: "stage",
        label: "Stage",
        type: "text",
        placeholder: "e.g. III, IIIB, T3N2M0",
        hint: "Staging directly controls eligibility in most oncology trials.",
      },
    ],
  },
  {
    group: "Treatment & Performance",
    fields: [
      {
        key: "prior_treatments",
        label: "Prior Treatments",
        type: "tags",
        placeholder: "e.g. Carboplatin, Pemetrexed, Radiation therapy",
        hint: "Separate treatments with commas. Many trials require or exclude specific prior therapies.",
      },
      {
        key: "performance_status",
        label: "Performance Status (ECOG)",
        type: "select",
        placeholder: "",
        hint: "Physical functioning level — most trials cap eligibility at ECOG 0–2.",
        options: PERFORMANCE_STATUS_OPTIONS,
      },
    ],
  },
  {
    group: "Other Medical History",
    fields: [
      {
        key: "comorbidities",
        label: "Other Medical Conditions",
        type: "tags",
        placeholder: "e.g. Type 2 diabetes, Hypertension, CKD stage 3",
        hint: "Separate conditions with commas. May match or exclude you from certain trials.",
      },
    ],
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function isMissing(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string" && value.trim() === "") return true;
  if (Array.isArray(value) && value.length === 0) return true;
  return false;
}

function getEmptyKeys(profile: PatientProfileExtracted): Set<string> {
  const empty = new Set<string>();
  for (const { fields } of FIELD_GROUPS) {
    for (const fd of fields) {
      if (isMissing(profile[fd.key])) empty.add(fd.key);
    }
  }
  return empty;
}

// ── Main component ────────────────────────────────────────────────────────────

export function PatientProfileGapForm({ current, onSave }: PatientProfileGapFormProps) {
  const emptyKeys = useMemo(() => getEmptyKeys(current), [current]);

  // If nothing is missing, don't render
  const hasAnyMissing = emptyKeys.size > 0;
  if (!hasAnyMissing) return null;

  return <GapFormInner emptyKeys={emptyKeys} current={current} onSave={onSave} />;
}

// Separate inner component so state resets when current changes
function GapFormInner({
  emptyKeys,
  current,
  onSave,
}: {
  emptyKeys: Set<string>;
  current: PatientProfileExtracted;
  onSave: PatientProfileGapFormProps["onSave"];
}) {
  // Text state for simple fields
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const { fields } of FIELD_GROUPS) {
      for (const fd of fields) {
        if (!emptyKeys.has(fd.key)) continue;
        const v = current[fd.key];
        if (Array.isArray(v)) init[fd.key] = v.join(", ");
        else init[fd.key] = v != null ? String(v) : "";
      }
    }
    return init;
  });

  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const setValue = useCallback((key: string, val: string) => {
    setValues((prev) => ({ ...prev, [key]: val }));
  }, []);

  // Build patch from non-empty values the user filled in
  const buildPatch = useCallback((): Record<string, string | number | string[]> | null => {
    const patch: Record<string, string | number | string[]> = {};

    for (const { fields } of FIELD_GROUPS) {
      for (const fd of fields) {
        if (!emptyKeys.has(fd.key)) continue;
        const raw = (values[fd.key] ?? "").trim();
        if (!raw) continue;

        if (fd.type === "number") {
          const n = parseInt(raw, 10);
          if (Number.isNaN(n) || n < 0 || n > 130) {
            setError(`"${fd.label}" must be a valid number.`);
            return null;
          }
          patch[fd.key] = n;
        } else if (fd.type === "zip") {
          const d = raw.replace(/\D/g, "").slice(0, 5);
          if (d.length !== 5) {
            setError("ZIP code must be exactly 5 digits.");
            return null;
          }
          patch[fd.key] = d;
        } else if (fd.type === "tags") {
          const arr = raw
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          if (arr.length > 0) patch[fd.key] = arr;
        } else {
          patch[fd.key] = raw;
        }
      }
    }

    return patch;
  }, [values, emptyKeys]);

  const submit = useCallback(async () => {
    setError(null);
    const patch = buildPatch();
    if (patch === null) return; // validation error already set
    if (Object.keys(patch).length === 0) {
      // Nothing filled in — that's allowed; just save the consent
      return;
    }
    setSaving(true);
    try {
      await onSave(patch);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [buildPatch, onSave]);

  const visibleGroups = FIELD_GROUPS.map((g) => ({
    ...g,
    fields: g.fields.filter((fd) => emptyKeys.has(fd.key)),
  })).filter((g) => g.fields.length > 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="overflow-hidden rounded-2xl border border-brand-100 bg-white shadow-sm"
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 ring-1 ring-brand-100">
            <Lock className="h-4 w-4 text-brand-500" strokeWidth={1.75} />
          </div>
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-brand-500">
              Optional — improve your matches
            </p>
            <h3 className="text-[15px] font-semibold text-gray-900">
              Fill in what we couldn't read from your PDF
            </h3>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-gray-400">
          <span>{emptyKeys.size} field{emptyKeys.size !== 1 ? "s" : ""} missing</span>
          {collapsed ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-gray-100 px-6 pb-6 pt-5">
              <p className="mb-5 text-sm text-gray-500">
                Every field below is <span className="font-semibold text-gray-700">completely optional</span>.
                The more you share, the more precisely we can rank and filter trials for you.
                Nothing here is used for diagnosis.
              </p>

              {/* Field groups */}
              <div className="space-y-6">
                {visibleGroups.map(({ group, fields }) => {
                  // Hide the group header when it would just duplicate the
                  // lone field's own label (e.g. "Other Medical History" →
                  // "Other Medical Conditions"). The field's bold label is
                  // already clear on its own.
                  const showGroupHeading = fields.length > 1;
                  return (
                    <div key={group}>
                      {showGroupHeading && (
                        <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.15em] text-gray-400">
                          {group}
                        </p>
                      )}
                      <div className="grid gap-3 sm:grid-cols-2">
                        {fields.map((fd) => (
                          <FieldInput
                            key={fd.key}
                            def={fd}
                            value={values[fd.key] ?? ""}
                            onChange={(v) => setValue(fd.key, v)}
                            fullWidth={fd.type === "tags" || fd.key === "diagnosis"}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* HIPAA consent */}
              <div className="mt-7 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
                  <Shield className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" strokeWidth={1.75} />
                  <div>
                    <p className="text-sm font-semibold text-slate-800">Your data, your control</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                      Before we use this supplemental information for matching, please review how it's handled.
                    </p>
                  </div>
                </div>
                <ul className="space-y-2 px-5 py-4 text-xs leading-relaxed text-slate-600">
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-brand-500">✓</span>
                    <span>
                      <span className="font-semibold text-slate-700">Used only for trial matching.</span>{" "}
                      This data is processed solely to identify potentially relevant clinical trials on your behalf.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-brand-500">✓</span>
                    <span>
                      <span className="font-semibold text-slate-700">Never sold or shared.</span>{" "}
                      Your health information is never sold to third parties, advertisers, or data brokers.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-brand-500">✓</span>
                    <span>
                      <span className="font-semibold text-slate-700">Session-scoped by default.</span>{" "}
                      Supplemental data is retained only for this active session unless you explicitly request otherwise.
                      Processed in accordance with HIPAA Security Rule safeguards.
                    </span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-brand-500">✓</span>
                    <span>
                      <span className="font-semibold text-slate-700">Not a medical service.</span>{" "}
                      TrialFind is a matching and translation tool. Nothing here constitutes a diagnosis,
                      medical advice, or a recommendation to enroll in any specific trial.
                    </span>
                  </li>
                </ul>
                <label className="flex cursor-pointer items-start gap-3 border-t border-slate-200 px-5 py-4">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-slate-300 accent-brand-500"
                  />
                  <span className="text-xs leading-relaxed text-slate-600">
                    I voluntarily consent to share the supplemental health information above with TrialFind
                    solely to identify relevant clinical trials on my behalf, in accordance with the data
                    handling practices described here.
                  </span>
                </label>
              </div>

              {error && (
                <p className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </p>
              )}

              <button
                type="button"
                disabled={!consent || saving}
                onClick={() => void submit()}
                className="mt-4 inline-flex items-center gap-2 rounded-full bg-brand-500 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save & improve my matches
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Field input component ─────────────────────────────────────────────────────

function FieldInput({
  def,
  value,
  onChange,
  fullWidth,
}: {
  def: FieldDef;
  value: string;
  onChange: (v: string) => void;
  fullWidth: boolean;
}) {
  const baseInput =
    "w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100 placeholder:text-gray-300";

  return (
    <label className={`flex flex-col gap-1 ${fullWidth ? "sm:col-span-2" : ""}`}>
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-gray-500">
        {def.label}
        <span className="ml-1.5 normal-case font-normal tracking-normal text-gray-400">
          — optional
        </span>
      </span>

      {def.type === "select" ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        >
          <option value="">Select…</option>
          {def.options!.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : def.type === "number" ? (
        <input
          type="text"
          inputMode="numeric"
          maxLength={3}
          placeholder={def.placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 3))}
          className={baseInput}
        />
      ) : def.type === "zip" ? (
        <input
          type="text"
          inputMode="numeric"
          maxLength={5}
          placeholder={def.placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 5))}
          className={baseInput}
        />
      ) : (
        <input
          type="text"
          placeholder={def.placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        />
      )}

      <span className="text-[11px] leading-relaxed text-gray-400">{def.hint}</span>
    </label>
  );
}
