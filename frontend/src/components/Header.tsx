import { Loader2, Search } from "lucide-react";
import { cn } from "../lib/utils";

interface HeaderProps {
  running: boolean;
  onRun: () => void;
}

function TrialFindMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      fill="none"
      aria-hidden="true"
    >
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

export function Header({ running, onRun }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/95 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-4 px-6 lg:px-8">
        {/* Logo */}
        <div className="flex items-center gap-2.5 select-none">
          <TrialFindMark size={30} />
          <div className="flex items-baseline gap-0">
            <span
              className="text-[22px] font-bold leading-none tracking-tight"
              style={{ color: "#1D9E75", fontFamily: "Georgia, serif" }}
            >
              Trial
            </span>
            <span
              className="text-[22px] font-bold leading-none tracking-tight"
              style={{ color: "#085041", fontFamily: "Georgia, serif" }}
            >
              Find
            </span>
          </div>
        </div>

        {/* Nav */}
        <nav className="hidden items-center gap-7 md:flex">
          {["How it works", "For Patients", "For Clinics"].map((label) => (
            <a
              key={label}
              href="#how-it-works"
              className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900"
            >
              {label}
            </a>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-3">
          {running && (
            <span className="hidden items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 ring-1 ring-inset ring-brand-200 sm:inline-flex">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              Searching…
            </span>
          )}
          <button
            type="button"
            onClick={onRun}
            disabled={running}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all",
              "bg-brand-500 hover:bg-brand-600 active:scale-[0.98]",
              "disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none"
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
          </button>
        </div>
      </div>
    </header>
  );
}
