import { motion } from "framer-motion";
import { Loader2, Search, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "../lib/utils";

interface HeaderProps {
  running: boolean;
  onRun: () => void;
  hasProfile: boolean;
}

const NAV_LINKS = [
  { label: "For Patients", href: "#for-patients" },
  { label: "For Clinics", href: "#for-clinics" },
];

function TrialFindMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 200 200" fill="none" aria-hidden="true">
      <circle cx="100" cy="100" r="68" stroke="#1D9E75" strokeWidth="5" />
      <circle cx="100" cy="100" r="44" stroke="#1D9E75" strokeWidth="2.5" />
      <circle cx="100" cy="100" r="20" fill="#1D9E75" />
      <line x1="32" y1="100" x2="56" y2="100" stroke="#1D9E75" strokeWidth="4" strokeLinecap="round" />
      <line x1="144" y1="100" x2="168" y2="100" stroke="#1D9E75" strokeWidth="4" strokeLinecap="round" />
      <line x1="100" y1="32" x2="100" y2="56" stroke="#1D9E75" strokeWidth="4" strokeLinecap="round" />
      <line x1="100" y1="144" x2="100" y2="168" stroke="#1D9E75" strokeWidth="4" strokeLinecap="round" />
      <circle cx="100" cy="100" r="7" fill="white" />
    </svg>
  );
}

export function Header({ running, onRun, hasProfile }: HeaderProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const isDisabled = !hasProfile || running;

  return (
    <motion.header
      initial={{ y: -16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "sticky top-0 z-40 bg-black transition-all duration-300",
        scrolled && "border-b border-white/10 shadow-lg shadow-black/40"
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-4 px-6 lg:px-8">
        {/* Logo */}
        <a href="#" className="flex select-none items-center gap-2.5">
          <TrialFindMark size={28} />
          <span
            className="text-[20px] font-bold leading-none tracking-tight text-white"
            style={{ fontFamily: "Georgia, serif" }}
          >
            Trial<span style={{ color: "#1D9E75" }}>Find</span>
          </span>
        </a>

        {/* Nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              className="relative rounded-lg px-4 py-2 text-sm font-medium text-gray-400 transition-colors hover:text-white"
            >
              {label}
            </a>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-3">
          {running && (
            <motion.span
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="hidden items-center gap-1.5 rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs font-semibold text-brand-400 sm:inline-flex"
            >
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-400" />
              Searching…
            </motion.span>
          )}

          {/* Tooltip wrapper */}
          <div className="group relative">
            <motion.button
              type="button"
              onClick={onRun}
              disabled={isDisabled}
              whileHover={!isDisabled ? { scale: 1.03 } : undefined}
              whileTap={!isDisabled ? { scale: 0.97 } : undefined}
              className={cn(
                "inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold transition-all duration-200",
                !isDisabled
                  ? "bg-brand-500 text-white shadow-glow-brand hover:bg-brand-400 hover:shadow-glow-brand-lg"
                  : "cursor-not-allowed bg-white/8 text-white/30"
              )}
            >
              {running ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching…
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Find Trials
                </>
              )}
            </motion.button>

            {/* Tooltip — only shows when disabled due to no PDF */}
            {!hasProfile && !running && (
              <div className="pointer-events-none absolute right-0 top-full mt-2 w-max rounded-lg border border-white/10 bg-surface-900 px-3 py-1.5 text-xs text-gray-400 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                <Upload className="mr-1.5 inline h-3 w-3" />
                Upload a PDF first
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.header>
  );
}
