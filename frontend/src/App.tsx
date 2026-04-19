import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  Building2,
  Calendar,
  Database,
  Lock,
  Mail,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { DocumentUploadCard } from "./components/DocumentUploadCard";
import { Header } from "./components/Header";
import { HeroCard } from "./components/HeroCard";
import { ScoredMatchesTable } from "./components/ScoredMatchesTable";
import { StatusTicker } from "./components/StatusTicker";
import { useTrialStream } from "./hooks/useTrialStream";
import type { PatientProfileExtracted } from "./types";

const CLINIC_FEATURES = [
  {
    icon: Brain,
    title: "AI-powered pre-screening",
    description:
      "Automatically match patient cohorts against your open trials using structured clinical criteria.",
  },
  {
    icon: Database,
    title: "Multi-source aggregation",
    description:
      "Pull from ClinicalTrials.gov, pharma portals, and regional registries — all normalized in one API call.",
  },
  {
    icon: Zap,
    title: "EHR integration",
    description:
      "Connect directly with Epic, Cerner, and HL7 FHIR endpoints to match patients as records update.",
  },
  {
    icon: BarChart3,
    title: "Enrollment analytics",
    description:
      "Track pipeline conversion, screen-fail reasons, and site performance across all active trials.",
  },
  {
    icon: Lock,
    title: "HIPAA compliance built-in",
    description:
      "End-to-end encryption, full audit logs, BAA available. Designed for regulated healthcare environments.",
  },
  {
    icon: Activity,
    title: "Real-time alerts",
    description:
      "Get notified when new trials open that match your patient population or when eligibility windows close.",
  },
];

const revealUp = {
  hidden: { opacity: 0, y: 22 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.25 } },
};

const stagger = {
  visible: { transition: { staggerChildren: 0.12 } },
};

export default function App() {
  const stream = useTrialStream();
  const [pdfPatient, setPdfPatient] = useState<PatientProfileExtracted | null>(null);
  const hasProfile = pdfPatient !== null;

  return (
    <div className="min-h-screen" style={{ background: "#020c07" }}>
      <Header running={stream.running} onRun={stream.start} hasProfile={hasProfile} />

      {/* ── COMPACT HERO INTRO ── */}
      <section
        id="for-patients"
        className="relative overflow-hidden px-6 pb-0 pt-20 sm:pt-28 lg:px-8"
        style={{ background: "#020c07" }}
      >
        {/* Background glow */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          <div
            className="absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[800px] rounded-full opacity-20"
            style={{ background: "radial-gradient(ellipse, #1D9E75 0%, transparent 65%)" }}
          />
          <div className="absolute inset-0 dot-grid" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto max-w-[720px] pb-14 text-center"
        >
          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-[60px] lg:leading-[1.06]">
            Find clinical trials matched
            <br />
            <span className="gradient-text">to your diagnosis.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-gray-400 sm:text-lg">
            Upload your pathology report or visit summary to get started. No account
            required — free for patients.
          </p>
        </motion.div>
      </section>

      {/* ── TOOL AREA ── */}
      <section className="bg-white px-4 pb-20 pt-10 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1280px] space-y-5">
          {/* Upload card — always visible */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <DocumentUploadCard onProfileReady={setPdfPatient} />
          </motion.div>

          {/* Results — only after upload */}
          <AnimatePresence>
            {hasProfile && (
              <motion.div
                key="results"
                variants={stagger}
                initial="hidden"
                animate="visible"
                exit="hidden"
                className="space-y-5"
              >
                <motion.div variants={revealUp}>
                  <HeroCard
                    errors={stream.errors}
                    patientProfile={pdfPatient}
                    onRun={stream.start}
                    running={stream.running}
                  />
                </motion.div>

                <motion.div variants={revealUp}>
                  <StatusTicker
                    friendlyStatus={stream.friendlyStatus}
                    running={stream.running}
                    trialsFound={stream.rawTrials.length}
                    scoredCount={stream.scored.length}
                  />
                </motion.div>

                <motion.div variants={revealUp}>
                  <ScoredMatchesTable
                    rawTrials={stream.rawTrials}
                    scored={stream.scored}
                    running={stream.running}
                    patientGeo={stream.patientGeo}
                  />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </section>

      {/* ── FOR CLINICS ── */}
      <section
        id="for-clinics"
        className="scroll-mt-16 overflow-hidden bg-gray-50 px-6 py-28 lg:px-8"
      >
        <div className="relative mx-auto max-w-[1100px]">
          <div className="pointer-events-none absolute inset-0 line-grid opacity-60" aria-hidden />

          <div className="relative">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.55 }}
              className="mb-16 text-center"
            >
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-surface-950/90 px-4 py-1.5 text-sm font-semibold text-brand-400 ring-1 ring-inset ring-white/10">
                <Building2 className="h-3.5 w-3.5" />
                For Healthcare Providers
              </div>
              <h2 className="text-3xl font-extrabold tracking-tight text-gray-900 sm:text-4xl lg:text-5xl">
                Built for clinical research teams
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-base text-gray-500">
                Give your coordinators superpowers. TrialFind automates patient-trial
                matching so your team can focus on enrollment and care.
              </p>
            </motion.div>

            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {CLINIC_FEATURES.map(({ icon: Icon, title, description }, i) => (
                <motion.div
                  key={title}
                  initial={{ opacity: 0, y: 28 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-50px" }}
                  transition={{ delay: i * 0.08, duration: 0.5 }}
                  whileHover={{ y: -4, transition: { duration: 0.2 } }}
                  className="group relative rounded-2xl border border-gray-200 bg-white p-7 shadow-soft transition-shadow hover:shadow-card"
                >
                  <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 ring-1 ring-brand-100 transition-all group-hover:bg-brand-500 group-hover:ring-brand-500">
                    <Icon
                      className="h-5 w-5 text-brand-500 transition-colors group-hover:text-white"
                      strokeWidth={1.75}
                    />
                  </div>
                  <h3 className="mb-2.5 text-[16px] font-semibold text-gray-900">{title}</h3>
                  <p className="text-sm leading-relaxed text-gray-500">{description}</p>
                </motion.div>
              ))}
            </div>

            {/* CTA banner */}
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.55, delay: 0.2 }}
              className="relative mt-14 overflow-hidden rounded-3xl"
              style={{ background: "#020c07" }}
            >
              <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
                <div
                  className="absolute -right-40 -top-40 h-[400px] w-[400px] rounded-full opacity-20"
                  style={{
                    background: "radial-gradient(ellipse at center, #1D9E75 0%, transparent 65%)",
                  }}
                />
              </div>
              <div className="dot-grid relative flex flex-col items-center gap-8 px-10 py-14 text-center sm:flex-row sm:text-left">
                <div className="flex-1">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-brand-400">
                    Enterprise access
                  </p>
                  <h3 className="mt-2 text-2xl font-extrabold text-white sm:text-3xl">
                    Ready to automate your
                    <br className="hidden sm:block" /> enrollment pipeline?
                  </h3>
                  <p className="mt-3 max-w-md text-sm text-gray-400">
                    We work directly with research teams to configure matching, integrate
                    with your EHR, and streamline IRB-ready patient outreach workflows.
                  </p>
                </div>
                <div className="flex shrink-0 flex-col gap-3 sm:items-end">
                  <motion.a
                    href="mailto:eshwar.rajasekar@gmail.com"
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.97 }}
                    className="group inline-flex items-center gap-2.5 rounded-full bg-brand-500 px-7 py-3.5 text-sm font-semibold text-white shadow-glow-brand transition-shadow hover:shadow-glow-brand-lg"
                  >
                    <Calendar className="h-4 w-4" />
                    Schedule a Demo
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </motion.a>
                  <motion.a
                    href="mailto:eshwar.rajasekar@gmail.com"
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.97 }}
                    className="group inline-flex items-center gap-2.5 rounded-full border border-white/20 px-7 py-3.5 text-sm font-semibold text-white transition-colors hover:border-white/30 hover:bg-white/5"
                  >
                    <Mail className="h-4 w-4" />
                    Get in touch
                  </motion.a>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer
        className="border-t border-white/[0.06] px-6 py-12 lg:px-8"
        style={{ background: "#020c07" }}
      >
        <div className="mx-auto max-w-[1200px]">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <img src="/trialfind_wordmark.svg" alt="TrialFind" height={36} className="select-none" />
            <div className="flex flex-wrap items-center justify-center gap-6 text-sm text-gray-600">
              <a href="#for-patients" className="transition-colors hover:text-gray-300">
                For Patients
              </a>
              <a href="#for-clinics" className="transition-colors hover:text-gray-300">
                For Clinics
              </a>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span>Data: ClinicalTrials.gov · Mayo Clinic</span>
              <span className="text-gray-700">·</span>
              <span>AI: Featherless</span>
            </div>
          </div>
          <div className="mt-8 border-t border-white/[0.05] pt-6 text-center text-xs text-gray-700">
            For informational purposes only. Not a substitute for professional medical advice.
            Always consult a qualified physician before making treatment decisions.
          </div>
        </div>
      </footer>
    </div>
  );
}
