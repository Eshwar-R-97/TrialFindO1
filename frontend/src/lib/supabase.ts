import { createClient } from "@supabase/supabase-js";

// Anon key only — safe to ship to the browser.
// RLS is enabled with no permissive policies, so this key can't read
// any patient data. It exists here for future auth flows (e.g. magic link).
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    "Supabase env vars missing. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to your .env"
  );
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
