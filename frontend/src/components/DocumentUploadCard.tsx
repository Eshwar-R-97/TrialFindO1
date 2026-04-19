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
    <section className="rounded-2xl border border-border bg-card p-6 shadow-soft sm:p-7">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Document
          </p>
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
            Upload a pathology or visit-summary PDF
          </h2>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            pypdf turns the file into page-level JSON on the server;{" "}
            <span className="font-medium text-foreground">Featherless AI</span> parses
            that JSON into a patient profile for trial matching — not a diagnosis.
          </p>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border bg-slate-50 px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm transition hover:bg-slate-100">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4 text-slate-500" />
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
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
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
    <div className="mt-5 space-y-4">
      <PatientProfileGapForm
        key={missingFields.join("|")}
        missingFields={missingFields}
        current={profile}
        onSave={onMergeProfile}
      />
      <p className="text-xs text-muted-foreground">
        {meta.filename} · {pdfExtraction.page_count} page(s) ·{" "}
        {meta.text_chars_extracted.toLocaleString()} chars · JSON to model:{" "}
        {meta.json_chars_sent_to_model.toLocaleString()} chars
        {meta.json_truncated_for_model ? " (shrunk to fit context)" : ""}
      </p>
      <div className="rounded-xl border border-border/80 bg-slate-50/80 p-4 text-sm leading-relaxed text-foreground">
        <p className="font-medium text-slate-600">Summary</p>
        <p className="mt-1">{profile.summary}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {chips.map((c) => (
          <div
            key={c.label}
            className="flex min-w-[120px] flex-col rounded-xl border border-border/70 bg-slate-50/70 px-3.5 py-2"
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
              {c.label}
            </span>
            <span className="text-sm font-medium text-foreground">{c.value}</span>
          </div>
        ))}
      </div>
      {biomarkerEntries.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Biomarkers
          </p>
          <div className="flex flex-wrap gap-2">
            {biomarkerEntries.map(([k, v]) => (
              <span
                key={k}
                className="rounded-lg border border-border/70 bg-white px-2.5 py-1 text-xs"
              >
                <span className="font-medium">{k}</span>: {v}
              </span>
            ))}
          </div>
        </div>
      )}
      {Array.isArray(profile.prior_treatments) && profile.prior_treatments.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Prior treatments
          </p>
          <ul className="list-inside list-disc text-sm text-foreground">
            {profile.prior_treatments.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {Array.isArray(profile.comorbidities) && profile.comorbidities.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Comorbidities
          </p>
          <ul className="list-inside list-disc text-sm text-foreground">
            {profile.comorbidities.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="rounded-lg border border-amber-200/80 bg-amber-50/90 px-3 py-2 text-sm text-amber-950">
        {profile.discuss_with_oncologist}
      </p>
    </div>
  );
}
