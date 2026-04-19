import { motion } from "framer-motion";
import {
  ArrowRight,
  Building2,
  ClipboardCheck,
  FileText,
  Shield,
  Sparkles,
  Target,
  User,
} from "lucide-react";

const STATS = [
  { value: "500K+", label: "Trials indexed" },
  { value: "4 sources", label: "Searched simultaneously" },
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

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
};

export function LandingHero() {
  return (
    <>
      {/* ── HERO ── */}
      <section
        className="relative overflow-hidden px-6 pb-32 pt-24 sm:pt-40 lg:px-8"
        style={{ background: "#020c07" }}
      >
        {/* Background orbs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          {/* Primary green glow */}
          <div
            className="absolute -top-48 left-1/2 -translate-x-1/2 h-[700px] w-[900px] rounded-full opacity-25"
            style={{
              background: "radial-gradient(ellipse at center, #1D9E75 0%, transparent 65%)",
            }}
          />
          {/* Secondary glow right */}
          <div
            className="absolute -right-32 top-20 h-[450px] w-[600px] animate-float-alt rounded-full opacity-10"
            style={{
              background: "radial-gradient(ellipse at center, #3dbb96 0%, transparent 70%)",
            }}
          />
          {/* Tertiary glow left */}
          <div
            className="absolute -left-32 bottom-0 h-[350px] w-[500px] animate-float rounded-full opacity-8"
            style={{
              background: "radial-gradient(ellipse at center, #1D9E75 0%, transparent 70%)",
              animationDelay: "3s",
            }}
          />
          {/* Dot grid */}
          <div className="absolute inset-0 dot-grid" />
          {/* Bottom fade */}
          <div
            className="absolute bottom-0 left-0 right-0 h-48"
            style={{
              background: "linear-gradient(to bottom, transparent, #020c07)",
            }}
          />
        </div>

        {/* Content */}
        <motion.div
          variants={container}
          initial="hidden"
          animate="visible"
          className="relative mx-auto max-w-[900px] text-center"
        >
          {/* Badge */}
          <motion.div variants={fadeUp}>
            <span className="mb-8 inline-flex items-center gap-2.5 rounded-full border border-brand-700/40 bg-brand-950/60 px-4 py-1.5 text-sm font-medium text-brand-400 backdrop-blur-sm">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-400" />
              Free for patients · No account required
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={fadeUp}
            className="text-5xl font-extrabold tracking-tight text-white sm:text-6xl lg:text-[80px] lg:leading-[1.04]"
          >
            The fastest path to
            <br />
            <span className="gradient-text">clinical trial enrollment.</span>
          </motion.h1>

          {/* Subtext */}
          <motion.p
            variants={fadeUp}
            className="mx-auto mt-8 max-w-[600px] text-lg leading-relaxed text-gray-400 sm:text-xl"
          >
            95% of cancer patients never find out about clinical trials. TrialFind
            searches every source simultaneously and explains exactly why you qualify —
            in plain English, not medical jargon.
          </motion.p>

          {/* CTAs */}
          <motion.div
            variants={fadeUp}
            className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row"
          >
            <motion.a
              href="#for-patients"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="group inline-flex items-center gap-2.5 rounded-full bg-brand-500 px-8 py-4 text-base font-semibold text-white shadow-glow-brand transition-shadow hover:shadow-glow-brand-lg"
            >
              <User className="h-4 w-4" />
              I'm a Patient
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </motion.a>

            <motion.a
              href="#for-clinics"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="group inline-flex items-center gap-2.5 rounded-full border border-white/20 bg-white/5 px-8 py-4 text-base font-semibold text-white backdrop-blur-sm transition-colors hover:border-white/35 hover:bg-white/10"
            >
              <Building2 className="h-4 w-4" />
              I'm a Healthcare Provider
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </motion.a>
          </motion.div>

          {/* Trust row */}
          <motion.div
            variants={fadeUp}
            className="mt-10 flex flex-wrap items-center justify-center gap-8"
          >
            {[
              { icon: Shield, text: "HIPAA-conscious design" },
              { icon: Sparkles, text: "AI-powered matching" },
              { icon: Target, text: "Multi-source search" },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-2 text-sm text-gray-600">
                <Icon className="h-4 w-4 text-brand-500" strokeWidth={1.75} />
                {text}
              </div>
            ))}
          </motion.div>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 36 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.55, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto mt-20 max-w-3xl"
        >
          <div className="grid grid-cols-3 overflow-hidden rounded-2xl border border-white/10">
            {STATS.map(({ value, label }, i) => (
              <div
                key={label}
                className="bg-white/[0.04] py-9 text-center backdrop-blur-sm"
                style={{
                  borderRight: i < 2 ? "1px solid rgba(255,255,255,0.08)" : "none",
                }}
              >
                <p className="text-3xl font-extrabold text-white sm:text-4xl">{value}</p>
                <p className="mt-1.5 text-sm text-gray-500">{label}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section
        id="how-it-works"
        className="border-t border-white/[0.06] px-6 py-28 lg:px-8"
        style={{ background: "#020c07" }}
      >
        <div className="mx-auto max-w-[1100px]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.55 }}
            className="mb-16 text-center"
          >
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-500">
              How it works
            </p>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl lg:text-5xl">
              From diagnosis to matched trial
              <br className="hidden sm:block" /> in minutes
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base text-gray-500">
              What took oncology coordinators days of manual work, TrialFind does
              automatically — across every source that lists trials.
            </p>
          </motion.div>

          <div className="grid gap-4 sm:grid-cols-3">
            {HOW_IT_WORKS.map(({ step, icon: Icon, title, description }, i) => (
              <motion.div
                key={step}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ delay: i * 0.12, duration: 0.55 }}
                whileHover={{ y: -5, transition: { duration: 0.2 } }}
                className="group relative overflow-hidden rounded-2xl p-8"
                style={{
                  background: "rgba(255,255,255,0.035)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                {/* Card glow on hover */}
                <div
                  className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                  style={{
                    background:
                      "radial-gradient(ellipse at top left, rgba(29,158,117,0.12) 0%, transparent 60%)",
                  }}
                />
                <div className="relative">
                  <div className="mb-6 flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10 ring-1 ring-brand-500/20 transition-all duration-200 group-hover:bg-brand-500 group-hover:ring-brand-500 group-hover:shadow-glow-brand">
                      <Icon
                        className="h-5 w-5 text-brand-400 transition-colors group-hover:text-white"
                        strokeWidth={1.75}
                      />
                    </div>
                    <span className="text-xs font-bold tracking-[0.18em] text-white/20">
                      {step}
                    </span>
                  </div>
                  <h3 className="text-[17px] font-semibold text-white">{title}</h3>
                  <p className="mt-2.5 text-sm leading-relaxed text-gray-500">{description}</p>
                </div>
                {/* Bottom highlight line */}
                <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand-500/50 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Gradient bridge to white */}
      <div
        className="h-28"
        style={{ background: "linear-gradient(180deg, #020c07 0%, #f8fafb 100%)" }}
      />
    </>
  );
}
