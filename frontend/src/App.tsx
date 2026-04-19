import { useRef, useState } from "react";
import { DocumentUploadCard } from "./components/DocumentUploadCard";
import { Header } from "./components/Header";
import { LandingHero } from "./components/LandingHero";
import { ScoredMatchesTable } from "./components/ScoredMatchesTable";
import { StatusTicker } from "./components/StatusTicker";
import { HeroCard } from "./components/HeroCard";
import { useTrialStream } from "./hooks/useTrialStream";
import type { PatientProfileExtracted } from "./types";

export default function App() {
  const stream = useTrialStream();
  const [pdfPatient, setPdfPatient] = useState<PatientProfileExtracted | null>(null);
  const toolRef = useRef<HTMLDivElement>(null);

  const scrollToTool = () => {
    toolRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="min-h-screen bg-white">
      <Header running={stream.running} onRun={stream.start} />

      <LandingHero onGetStarted={scrollToTool} />

      {/* ── Tool sections ── */}
      <div
        ref={toolRef}
        id="get-started"
        className="scroll-mt-20 bg-white px-4 py-16 sm:px-6 lg:px-8"
      >
        <div className="mx-auto max-w-[1200px] space-y-6">
          {/* Section header */}
          <div className="mb-10 text-center">
            <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
              Get started
            </p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              Upload your records and find your match
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-base text-gray-500">
              Upload a pathology report or visit summary, then let TrialFind search
              every source simultaneously.
            </p>
          </div>

          <DocumentUploadCard onProfileReady={setPdfPatient} />

          <HeroCard
            statusText={stream.statusText}
            errors={stream.errors}
            elapsedMs={stream.elapsedMs}
            running={stream.running}
            patientProfile={pdfPatient}
          />

          <StatusTicker
            friendlyStatus={stream.friendlyStatus}
            running={stream.running}
            trialsFound={stream.rawTrials.length}
            scoredCount={stream.scored.length}
          />

          <ScoredMatchesTable
            rawTrials={stream.rawTrials}
            scored={stream.scored}
            running={stream.running}
          />
        </div>
      </div>

      <footer className="border-t border-gray-100 bg-white px-6 py-10 text-center lg:px-8">
        <div className="mx-auto max-w-[1200px]">
          <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
            <span className="font-semibold text-brand-600">TrialFind</span>
            <span>·</span>
            <span>Data from ClinicalTrials.gov &amp; Mayo Clinic</span>
            <span>·</span>
            <span>Scoring by Featherless AI</span>
          </div>
          <p className="mt-2 text-xs text-gray-300">
            For informational purposes only. Not a substitute for professional medical advice.
          </p>
        </div>
      </footer>
    </div>
  );
}
