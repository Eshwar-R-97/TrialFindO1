// Small helper utilities shared across components.

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function firstSentence(text: string | undefined, maxLen = 160): string {
  if (!text) return "";
  const match = String(text).match(/^.*?[.!?](?:\s|$)/);
  const first = (match ? match[0] : String(text)).trim();
  return first.length > maxLen ? first.slice(0, maxLen - 1) + "…" : first;
}

export function eligibilitySnippet(text: string | undefined, maxLen = 180): string {
  if (!text) return "Not provided.";
  const cleaned = String(text).replace(/\s+/g, " ").trim();
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen - 1) + "…" : cleaned;
}

export function formatTimestamp(epochSeconds: number | undefined): string {
  const d = epochSeconds ? new Date(epochSeconds * 1000) : new Date();
  return (
    String(d.getHours()).padStart(2, "0") +
    ":" +
    String(d.getMinutes()).padStart(2, "0") +
    ":" +
    String(d.getSeconds()).padStart(2, "0")
  );
}

export function trialSourceUrl(trial: {
  nct_url?: string;
  nct_id?: string | null;
  mayo_url?: string;
}): string | null {
  if (trial.nct_url) return trial.nct_url;
  if (trial.nct_id) return `https://clinicaltrials.gov/study/${trial.nct_id}`;
  if (trial.mayo_url) return trial.mayo_url;
  return null;
}

export function trialLocationLabel(trial: { location?: string }): string {
  const loc = (trial.location || "").trim();
  if (loc && loc.toLowerCase() !== "unknown") return loc;
  return "Location not listed";
}
