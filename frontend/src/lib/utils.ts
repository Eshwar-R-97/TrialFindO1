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

// --- Distance helpers --------------------------------------------------------
//
// We show a "X mi away" chip next to each trial's location and let the user
// sort the Matches table by distance. Coordinates come from the backend:
//   - ClinicalTrials.gov provides `geoPoint` on each site
//   - NCI CTRP provides `org_coordinates` (or flat lat/lng fields)
//   - Mayo's scrape has no geo; backend falls back to known campus coords
// The patient anchor lat/lng comes from the `patient_geo` SSE event.

export interface LatLng {
  lat: number;
  lng: number;
}

const EARTH_RADIUS_MI = 3958.7613;

export function haversineMiles(a: LatLng, b: LatLng): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Format a distance in miles for a per-trial chip. */
export function formatMiles(miles: number): string {
  if (!Number.isFinite(miles)) return "";
  if (miles < 1) return "<1 mi";
  if (miles < 10) return `${miles.toFixed(1)} mi`;
  return `${Math.round(miles)} mi`;
}
