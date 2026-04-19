import { Header } from "./components/Header";
import { HeroCard } from "./components/HeroCard";
import { PipelinePanel } from "./components/PipelinePanel";
import { RawTrialsPanel } from "./components/RawTrialsPanel";
import { ScoredMatchesTable } from "./components/ScoredMatchesTable";
import { StatusTicker } from "./components/StatusTicker";
import { useTrialStream } from "./hooks/useTrialStream";

export default function App() {
  const stream = useTrialStream();

  return (
    <div className="min-h-screen">
      <Header running={stream.running} onRun={stream.start} />

      <main className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <HeroCard
          statusText={stream.statusText}
          errors={stream.errors}
          elapsedMs={stream.elapsedMs}
          running={stream.running}
        />

        <PipelinePanel steps={stream.steps} />

        <StatusTicker
          friendlyStatus={stream.friendlyStatus}
          running={stream.running}
          trialsFound={stream.rawTrials.length}
          scoredCount={stream.scored.length}
        />

        <ScoredMatchesTable scored={stream.scored} running={stream.running} />

        <RawTrialsPanel rawTrials={stream.rawTrials} />

        <footer className="pt-4 text-center text-xs text-muted-foreground">
          <p>
            TrialFind MVP · data from ClinicalTrials.gov &amp; Mayo Clinic · scoring by
            Featherless AI
          </p>
        </footer>
      </main>
    </div>
  );
}
