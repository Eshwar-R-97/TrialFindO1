import { FlaskConical, Loader2, Search } from "lucide-react";
import { cn } from "../lib/utils";

interface HeaderProps {
  running: boolean;
  onRun: () => void;
}

export function Header({ running, onRun }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-600 to-sky-500 text-white shadow-soft">
            <FlaskConical className="h-5 w-5" strokeWidth={2.25} />
          </div>
          <div className="min-w-0">
            <h1 className="text-[15px] font-semibold leading-tight tracking-tight text-foreground">
              TrialFind
            </h1>
            <p className="hidden text-xs text-muted-foreground sm:block">
              AI-powered clinical trial matching
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={cn(
              "hidden rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex items-center gap-1.5 transition-colors",
              running
                ? "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200"
                : "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200"
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                running ? "bg-blue-500 animate-pulse" : "bg-slate-400"
              )}
            />
            {running ? "Pipeline running" : "Idle"}
          </span>

          <button
            type="button"
            onClick={onRun}
            disabled={running}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-soft transition-all",
              "bg-brand-700 hover:bg-brand-800 active:translate-y-px",
              "disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-100 disabled:shadow-none"
            )}
          >
            {running ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running…
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
