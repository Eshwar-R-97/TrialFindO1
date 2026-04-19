import { FileText, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";
import { apiUrl } from "../lib/apiBase";
import { PatientProfileGapForm } from "./PatientProfileGapForm";
import type { PatientProfileExtracted, ReadPdfResponse } from "../types";

async function parseJsonResponse(
  res: Response
): Promise<ReadPdfResponse & { error?: string }> {
  const text = await res.text();
  if (!text.trim()) {
    throw new Error(
      `Empty response (HTTP ${res.status}). A 404 usually means the request never reached ` +
        `Flask (check Vite proxy and that python app.py is on :5050). Timeouts while waiting ` +
        `for Featherless more often return 502 with a JSON body — not an empty 404.`
    );
  }
  try {
    return JSON.parse(text) as ReadPdfResponse & { error?: string };
  } catch {
    const preview = text.slice(0, 240).replace(/\s+/g, " ");
    throw new Error(
      `Server did not return JSON (HTTP ${res.status}): ${preview}${text.length > 240 ? "…" : ""}`
    );
  }
}

export interface DocumentUploadCardProps {
  /** Fires when Featherless returns a profile; use to sync Hero + server-side pipeline. */
  onProfileReady?: (profile: PatientProfileExtracted) => void;
}

export function DocumentUploadCard({ onProfileReady }: DocumentUploadCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReadPdfResponse | null>(null);

  const onFile = useCallback(async (file: File | null) => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch(apiUrl("/read-pdf"), { method: "POST", body });
      const json = await parseJsonResponse(res);
      if (!res.ok) {
        throw new Error(json.error || res.statusText || "Request failed");
      }
      if (!("extracted_profile" in json) || !json.extracted_profile) {
        throw new Error("Invalid response from server");
      }
      const ok = json as ReadPdfResponse;
      setResult(ok);
      if (ok.extracted_profile) {
        onProfileReady?.(ok.extracted_profile);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [onProfileReady]);

  const mergeProfile = useCallback(
    async (patch: Record<string, string | number | string[]>) => {
      const res = await fetch(apiUrl("/api/patient-profile"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const text = await res.text();
      if (!text.trim()) {
        throw new Error(`Empty response (${res.status})`);
      }
      const data = JSON.parse(text) as {
        extracted_profile?: PatientProfileExtracted;
        missing_fields?: string[];
        error?: string;
      };
      if (!res.ok) {
        throw new Error(data.error || "Could not update profile");
      }
      if (!data.extracted_profile) {
        throw new Error("Invalid response from server");
      }
      setResult((prev) =>
        prev
          ? {
              ...prev,
              extracted_profile: data.extracted_profile!,
              missing_fields: data.missing_fields ?? [],
            }
          : null
      );
      onProfileReady?.(data.extracted_profile);
    },
    [onProfileReady]
  );

  const profile = result?.extracted_profile;

  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-brand-500">
            Step 1 — Upload your records
          </p>
          <h2 className="text-xl font-bold tracking-tight text-gray-900 sm:text-2xl">
            Upload a pathology or visit-summary PDF
          </h2>
          <p className="mt-2 max-w-prose text-sm text-gray-500">
            Your document is read securely on our server.{" "}
            <span className="font-semibold text-gray-700">Featherless AI</span> extracts
            your medical profile for trial matching — never for diagnosis.
          </p>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-gray-200 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
          ) : (
            <FileText className="h-4 w-4 text-gray-400" />
          )}
          <span>{loading ? "Reading…" : "Choose PDF"}</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            disabled={loading}
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              void onFile(f);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {profile && result?.pdf_extraction && (
        <ExtractedProfileView
          profile={profile}
          meta={result.meta}
          pdfExtraction={result.pdf_extraction}
          missingFields={result.missing_fields ?? []}
          onMergeProfile={mergeProfile}
        />
      )}
    </section>
  );
}

function ExtractedProfileView({
  profile,
  meta,
  pdfExtraction,
  missingFields,
  onMergeProfile,
}: {
  profile: PatientProfileExtracted;
  meta: ReadPdfResponse["meta"];
  pdfExtraction: ReadPdfResponse["pdf_extraction"];
  missingFields: string[];
  onMergeProfile: (patch: Record<string, string | number | string[]>) => Promise<void>;
}) {
  const biomarkersRaw = profile.biomarkers;
  const biomarkerEntries = Object.entries(
    biomarkersRaw &&
      typeof biomarkersRaw === "object" &&
      !Array.isArray(biomarkersRaw)
      ? (biomarkersRaw as Record<string, string>)
      : {}
  );
  const name =
    [profile.first_name, profile.last_name].filter(Boolean).join(" ").trim() || null;
  const chips: { label: string; value: string }[] = [
    { label: "Name", value: name || "—" },
    { label: "Email", value: profile.email || "—" },
    { label: "Diagnosis", value: profile.diagnosis || "—" },
    { label: "Cancer type", value: profile.cancer_type || "—" },
    { label: "Stage", value: profile.stage || "—" },
    { label: "Age", value: profile.age != null ? String(profile.age) : "—" },
    { label: "ZIP", value: profile.zip_code || "—" },
    { label: "ECOG / status", value: profile.performance_status || "—" },
  ];

  return (
    <div className="mt-6 space-y-4">
      <PatientProfileGapForm
        key={missingFields.join("|")}
        missingFields={missingFields}
        current={profile}
        onSave={onMergeProfile}
      />
      <p className="text-xs text-gray-400">
        {meta.filename} · {pdfExtraction.page_count} page(s) ·{" "}
        {meta.text_chars_extracted.toLocaleString()} chars extracted
        {meta.json_truncated_for_model ? " (shrunk to fit context)" : ""}
      </p>
      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm leading-relaxed">
        <p className="font-semibold text-gray-500">Summary</p>
        <p className="mt-1.5 text-gray-800">{profile.summary}</p>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {chips.map((c) => (
          <div
            key={c.label}
            className="flex min-w-[120px] flex-col rounded-xl border border-gray-100 bg-gray-50 px-4 py-2.5"
          >
            <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
              {c.label}
            </span>
            <span className="mt-0.5 text-sm font-semibold text-gray-900">{c.value}</span>
          </div>
        ))}
      </div>
      {biomarkerEntries.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            Biomarkers
          </p>
          <div className="flex flex-wrap gap-2">
            {biomarkerEntries.map(([k, v]) => (
              <span
                key={k}
                className="rounded-lg border border-gray-100 bg-white px-2.5 py-1 text-xs text-gray-700"
              >
                <span className="font-semibold">{k}</span>: {v}
              </span>
            ))}
          </div>
        </div>
      )}
      {Array.isArray(profile.prior_treatments) && profile.prior_treatments.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            Prior treatments
          </p>
          <ul className="list-inside list-disc text-sm text-gray-700">
            {profile.prior_treatments.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {Array.isArray(profile.comorbidities) && profile.comorbidities.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            Comorbidities
          </p>
          <ul className="list-inside list-disc text-sm text-gray-700">
            {profile.comorbidities.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        {profile.discuss_with_oncologist}
      </p>
    </div>
  );
}
