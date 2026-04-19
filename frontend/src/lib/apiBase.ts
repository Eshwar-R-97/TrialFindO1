/**
 * Build an absolute API URL when `VITE_API_BASE_URL` is set (bypasses Vite proxy),
 * otherwise return a same-origin path for the dev proxy / production Flask host.
 */
export function apiUrl(path: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!base) return p;
  return `${base}${p}`;
}
