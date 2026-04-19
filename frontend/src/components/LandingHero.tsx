import { ArrowDown, ClipboardCheck, FileText, Shield, Sparkles, Target } from "lucide-react";

interface LandingHeroProps {
  onGetStarted: () => void;
}

const STATS = [
  { value: "500,000+", label: "Trials indexed" },
  { value: "4 sources", label: "Searched in parallel" },
  { value: "Free", label: "Always, for patients" },
];

const HOW_IT_WORKS = [
  {
    step: "01",
    icon: FileText,
    title: "Upload your records",
    description:
      "Share your pathology report or doctor's summary. Our AI reads it and builds a precise medical profile — no account required.",
  },
  {
    step: "02",
    icon: Target,
    title: "AI searches everywhere",
    description:
      "We search ClinicalTrials.gov, Mayo Clinic, MD Anderson, and pharma portals simultaneously — not just one database.",
  },
  {
    step: "03",
    icon: ClipboardCheck,
    title: "Get your match report",
    description:
      "Each trial comes with a plain-English eligibility breakdown and a one-page summary ready to bring to your oncologist.",
  },
];

const TRUST_BADGES = [
  { icon: Shield, text: "HIPAA-conscious design" },
  { icon: Sparkles, text: "AI-powered matching" },
  { icon: Target, text: "Multi-source search" },
];

export function LandingHero({ onGetStarted }: LandingHeroProps) {
  return (
    <>
      {/* ── Hero ── */}
      <section className="relative overflow-hidden bg-white px-6 pb-20 pt-20 sm:pt-28 lg:px-8">
        {/* Subtle green radial glow at top */}
        <div
          className="pointer-events-none absolute inset-x-0 -top-40 -z-10 transform-gpu overflow-hidden"
          aria-hidden="true"
        >
          <div
            className="relative left-[50%] -translate-x-1/2 w-[900px] h-[600px] rounded-full opacity-[0.07]"
            style={{
              background: "radial-gradient(ellipse at center, #1D9E75 0%, transparent 70%)",
            }}
          />
        </div>

        <div className="mx-auto max-w-[860px] text-center">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-4 py-1.5 text-sm font-medium text-brand-700">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
            Free for patients · No account required
          </div>

          {/* Headline */}
          <h1 className="text-5xl font-extrabold tracking-tight text-gray-900 sm:text-6xl lg:text-[72px] lg:leading-[1.05]">
            Find clinical trials{" "}
            <span className="text-brand-500">that could</span>
            <br />
            <span className="text-brand-500">save your life.</span>
          </h1>

          {/* Subtext */}
          <p className="mx-auto mt-7 max-w-[600px] text-lg leading-relaxed text-gray-500 sm:text-xl">
            95% of cancer patients never find out about clinical trials. We search
            every source simultaneously and explain exactly why you qualify — in
            plain English, not medical jargon.
          </p>

          {/* CTAs */}
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <button
              type="button"
              onClick={onGetStarted}
              className="inline-flex items-center gap-2 rounded-full bg-brand-500 px-8 py-3.5 text-base font-semibold text-white shadow-md transition-all hover:bg-brand-600 active:scale-[0.98]"
            >
              Upload your records
            </button>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-2 rounded-full px-6 py-3.5 text-base font-semibold text-gray-600 ring-1 ring-gray-200 transition-all hover:bg-gray-50 hover:ring-gray-300"
            >
              See how it works
              <ArrowDown className="h-4 w-4" />
            </a>
          </div>

          {/* Trust badges */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-6">
            {TRUST_BADGES.map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-2 text-sm text-gray-400">
                <Icon className="h-4 w-4 text-brand-400" strokeWidth={1.75} />
                {text}
              </div>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="mx-auto mt-20 max-w-3xl">
          <div className="grid grid-cols-3 divide-x divide-gray-100 rounded-2xl border border-gray-100 bg-white shadow-sm">
            {STATS.map(({ value, label }) => (
              <div key={label} className="py-8 text-center">
                <p className="text-3xl font-extrabold tracking-tight text-gray-900 sm:text-4xl">
                  {value}
                </p>
                <p className="mt-1 text-sm text-gray-500">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="bg-gray-50/70 px-6 py-20 lg:px-8">
        <div className="mx-auto max-w-[1100px]">
          <div className="mb-14 text-center">
            <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
              How it works
            </p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              From diagnosis to matched trial in minutes
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base text-gray-500">
              What took oncology coordinators days of manual work, TrialFind does
              automatically — across every source that lists trials.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-3">
            {HOW_IT_WORKS.map(({ step, icon: Icon, title, description }) => (
              <div
                key={step}
                className="group relative rounded-2xl border border-gray-100 bg-white p-8 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="mb-5 flex items-center gap-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100 transition-colors group-hover:bg-brand-500 group-hover:text-white group-hover:ring-brand-500">
                    <Icon className="h-5 w-5" strokeWidth={1.75} />
                  </div>
                  <span className="text-xs font-bold tracking-widest text-gray-300">
                    {step}
                  </span>
                </div>
                <h3 className="text-[17px] font-semibold text-gray-900">{title}</h3>
                <p className="mt-2.5 text-sm leading-relaxed text-gray-500">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Disclaimer ── */}
      <div className="border-y border-gray-100 bg-white px-6 py-4 text-center text-xs text-gray-400 lg:px-8">
        TrialFind is a matching and translation tool — not a diagnostic service. Every
        result comes with the recommendation to discuss with your oncologist. Always
        consult a qualified physician before making treatment decisions.
      </div>
    </>
  );
}
