import {
  ArrowRight,
  BellRing,
  Camera,
  Check,
  Cigarette,
  Clock,
  Cpu,
  FileText,
  HardHat,
  HeartPulse,
  LayoutDashboard,
  Lock,
  Mail,
  Puzzle,
  ShieldAlert,
  SlidersHorizontal,
  Truck,
  Workflow,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LogoMark, PRODUCT_NAME } from "../components/Brand";
import { useAuth } from "../lib/auth";
import { CONSOLE_URL, IS_STATIC_SITE, useDemoStatus, type DemoStatus } from "../lib/site";

const NAV_LINKS = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#console", label: "Console" },
  { href: "#reports", label: "AI reports" },
  { href: "#faq", label: "FAQ" },
];

function ConsoleButton({ className = "", children }: { className?: string; children?: ReactNode }) {
  const { user } = useAuth();
  const classes = `inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition ${className}`;
  // the static product page links out to the console's own address
  if (IS_STATIC_SITE) {
    return (
      <a href={`${CONSOLE_URL}/login`} className={classes}>
        {children ?? "Sign in"}
      </a>
    );
  }
  return (
    <Link to={user ? "/app" : "/login"} className={classes}>
      {children ?? (user ? "Open console" : "Sign in")}
    </Link>
  );
}

const DEMO_TEXT: Record<DemoStatus, [string, string]> = {
  checking: ["bg-slate-400", "Checking live demo…"],
  online: ["bg-emerald-400", "Live demo online"],
  offline: ["bg-slate-500", "Live demo offline right now"],
};

function DemoBadge({ dark = true }: { dark?: boolean }) {
  const status = useDemoStatus();
  const [dot, text] = DEMO_TEXT[status];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ${
        dark ? "bg-white/5 text-slate-300 ring-white/10" : "bg-slate-50 text-slate-600 ring-slate-200"
      }`}
      title={status === "offline" ? "The console runs on the on-site device, which is switched off at the moment" : undefined}
    >
      <span className="relative flex h-2 w-2">
        {status === "online" && <span className={`absolute h-2 w-2 animate-ping rounded-full ${dot} opacity-60`} />}
        <span className={`relative h-2 w-2 rounded-full ${dot}`} />
      </span>
      {text}
    </span>
  );
}

function Header() {
  return (
    <header className="absolute inset-x-0 top-0 z-30">
      <div className="mx-auto flex h-20 max-w-7xl items-center gap-8 px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2.5">
          <LogoMark />
          <span className="text-[15px] font-semibold tracking-tight text-white">{PRODUCT_NAME}</span>
        </Link>
        <nav className="hidden gap-7 md:flex">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className="text-sm text-slate-300 transition hover:text-white">
              {l.label}
            </a>
          ))}
        </nav>
        <ConsoleButton className="ml-auto bg-white/10 px-4 py-2 text-sm text-white ring-1 ring-white/20 backdrop-blur hover:bg-white/15" />
      </div>
    </header>
  );
}

/** A stylised camera frame: what the detector sees and flags. Pure SVG, no real footage. */
function HeroFeed() {
  return (
    <div className="relative">
      <div className="absolute -inset-8 rounded-[2rem] bg-amber-400/10 blur-3xl" aria-hidden />
      <div className="relative overflow-hidden rounded-2xl bg-slate-900 shadow-2xl ring-1 ring-white/10">
        {/* window bar */}
        <div className="flex items-center gap-2 border-b border-white/10 bg-slate-900/80 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="ml-3 text-xs text-slate-400">North gate · cam_01</span>
          <span className="ml-auto inline-flex items-center gap-1.5 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-white">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> LIVE
          </span>
        </div>

        <svg viewBox="0 0 640 380" className="block w-full" role="img" aria-label="Example camera frame with detections">
          <defs>
            <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#1e293b" />
              <stop offset="1" stopColor="#334155" />
            </linearGradient>
            <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#3f3a33" />
              <stop offset="1" stopColor="#27241f" />
            </linearGradient>
            <pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="10" height="10" fill="#ef4444" fillOpacity="0.06" />
              <line x1="0" y1="0" x2="0" y2="10" stroke="#ef4444" strokeOpacity="0.25" strokeWidth="2" />
            </pattern>
          </defs>
          <rect width="640" height="380" fill="url(#sky)" />
          {/* building frame in the background */}
          <g stroke="#475569" strokeWidth="3" fill="none" opacity="0.7">
            <path d="M380 205V70h200v135M380 115h200M380 160h200M447 70v135M513 70v135" />
          </g>
          {/* crane */}
          <g stroke="#f59e0b" strokeWidth="3" fill="none" opacity="0.55">
            <path d="M110 205V40M110 40h170M110 60l30-20M280 40v40" />
            <path d="M110 70l12-12M110 100l12-12M110 130l12-12M110 160l12-12" strokeWidth="2" />
          </g>
          <rect y="205" width="640" height="175" fill="url(#ground)" />

          {/* restricted excavation zone */}
          <polygon points="20,300 210,268 250,372 20,372" fill="url(#hatch)" stroke="#ef4444" strokeWidth="2" strokeDasharray="8 6" />
          <rect x="28" y="340" width="150" height="22" rx="4" fill="#7f1d1d" fillOpacity="0.85" />
          <text x="36" y="355" fill="#fecaca" fontSize="11" fontFamily="ui-sans-serif, system-ui" fontWeight="600">
            RESTRICTED · Excavation
          </text>

          {/* excavator */}
          <g transform="translate(470 228)">
            <rect x="0" y="40" width="120" height="50" rx="6" fill="#ca8a04" />
            <rect x="60" y="10" width="50" height="40" rx="4" fill="#eab308" />
            <rect x="68" y="16" width="30" height="20" rx="2" fill="#1e293b" />
            <path d="M10 45 -40 0 -70 40" stroke="#a16207" strokeWidth="10" fill="none" strokeLinecap="round" />
            <rect x="-6" y="88" width="132" height="20" rx="10" fill="#1f2937" />
          </g>

          {/* worker 1: compliant */}
          <Worker x={300} y={210} helmet vest />
          {/* worker 2: no hard hat */}
          <Worker x={395} y={222} vest />

          {/* detections */}
          <Box x={286} y={196} w={58} h={128} color="#22c55e" label="Person 0.93" />
          <Box x={381} y={208} w={58} h={128} color="#ef4444" label="NO-Hardhat 0.87" />
          <Box x={430} y={232} w={192} h={140} color="#38bdf8" label="Machinery 0.91" />

          {/* scan line */}
          <rect x="0" y="0" width="640" height="2" fill="#fbbf24" opacity="0.35" className="scan-line" />
          <text x="14" y="24" fill="#cbd5e1" fontSize="11" fontFamily="ui-monospace, monospace">
            2026-10-07 14:32:08 · 30 fps
          </text>
        </svg>
      </div>

      {/* alert card */}
      <div className="float-slow absolute -bottom-8 -left-4 w-64 rounded-xl bg-white p-4 shadow-2xl ring-1 ring-slate-900/5 sm:-left-10">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-100">
            <HardHat className="h-4 w-4 text-orange-600" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">PPE missing</p>
            <p className="text-xs text-slate-500">North gate · just now</p>
          </div>
          <span className="ml-auto rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-bold text-orange-700">HIGH</span>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-600">Worker without a hard hat for 3.4 s. Supervisor emailed with snapshot and clip.</p>
      </div>

      {/* report card */}
      <div className="float-slower absolute -top-6 -right-3 hidden w-56 rounded-xl bg-white/95 p-3.5 shadow-2xl ring-1 ring-slate-900/5 backdrop-blur sm:block lg:-right-8">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
          <FileText className="h-3.5 w-3.5" /> AI incident report
        </p>
        <div className="mt-2 space-y-1.5">
          <div className="h-1.5 w-full rounded bg-slate-200" />
          <div className="h-1.5 w-11/12 rounded bg-slate-200" />
          <div className="h-1.5 w-4/6 rounded bg-slate-200" />
        </div>
        <p className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-emerald-700">
          <Check className="h-3.5 w-3.5" /> Ready for review
        </p>
      </div>
    </div>
  );
}

function Worker({ x, y, helmet = false, vest = false }: { x: number; y: number; helmet?: boolean; vest?: boolean }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle cx="15" cy="14" r="10" fill="#d6a77a" />
      {helmet && <path d="M3 13a12 12 0 0 1 24 0z" fill="#facc15" />}
      <rect x="2" y="26" width="26" height="46" rx="8" fill={vest ? "#f97316" : "#475569"} />
      {vest && <rect x="2" y="44" width="26" height="4" fill="#e5e7eb" opacity="0.9" />}
      <rect x="5" y="70" width="8" height="40" rx="3" fill="#1e3a5f" />
      <rect x="17" y="70" width="8" height="40" rx="3" fill="#1e3a5f" />
    </g>
  );
}

function Box({ x, y, w, h, color, label }: { x: number; y: number; w: number; h: number; color: string; label: string }) {
  const tw = label.length * 6.2 + 10;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} fill="none" stroke={color} strokeWidth="2.5" rx="2" />
      <rect x={x - 1.25} y={y - 18} width={tw} height="18" fill={color} rx="2" />
      <text x={x + 4} y={y - 5} fill="#fff" fontSize="11" fontFamily="ui-sans-serif, system-ui" fontWeight="600">
        {label}
      </text>
    </g>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-slate-950 pt-32 pb-24 lg:pt-40 lg:pb-32">
      <div className="hero-grid absolute inset-0" aria-hidden />
      <div className="absolute top-0 left-1/2 h-[40rem] w-[60rem] -translate-x-1/2 rounded-full bg-amber-500/10 blur-3xl" aria-hidden />
      <div className="relative mx-auto grid max-w-7xl items-center gap-16 px-6 lg:grid-cols-[1.05fr_1fr] lg:px-8">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-xs font-medium text-amber-300 ring-1 ring-white/10">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> Edge AI for construction safety
          </p>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance text-white sm:text-5xl lg:text-6xl">
            Every safety risk on site, <span className="text-amber-400">caught as it happens.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
            {PRODUCT_NAME} turns your site cameras into a safety officer that never looks away. It spots missing PPE, people in
            restricted zones, workers too close to machinery and smoking on site, alerts your supervisor in seconds and writes the incident report for you.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <ConsoleButton className="bg-amber-400 px-5 py-3 text-sm text-slate-950 shadow-lg shadow-amber-500/20 hover:bg-amber-300">
              Sign in to the console <ArrowRight className="h-4 w-4" />
            </ConsoleButton>
            <a href="#how-it-works" className="inline-flex items-center gap-2 px-2 py-3 text-sm font-semibold text-white hover:text-amber-300">
              See how it works
            </a>
          </div>
          <div className="mt-6">
            <DemoBadge />
          </div>
          <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-400">
            {["Runs on site, on the edge", "Works with standard cameras", "Report written by AI in seconds"].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <Check className="h-4 w-4 text-amber-400" /> {t}
              </li>
            ))}
          </ul>
        </div>
        <HeroFeed />
      </div>
    </section>
  );
}

const METRICS = [
  { value: "30 fps", label: "Real-time detection target per camera" },
  { value: "< 100 ms", label: "Target from detection to alert" },
  { value: "On device", label: "Video analysed on site by an NVIDIA Jetson" },
  { value: "24 / 7", label: "Monitoring that doesn't get tired" },
];

function Metrics() {
  return (
    <section className="border-b border-slate-200 bg-white">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-px bg-slate-200 lg:grid-cols-4">
        {METRICS.map((m) => (
          <div key={m.value} className="bg-white px-6 py-10 lg:px-8">
            <p className="text-3xl font-semibold tracking-tight text-slate-900">{m.value}</p>
            <p className="mt-2 text-sm text-slate-500">{m.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function SectionHeading({ eyebrow, title, children, center = false }: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  center?: boolean;
}) {
  return (
    <div className={center ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}>
      <p className="text-sm font-semibold text-amber-600">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-balance text-slate-900 sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-lg leading-8 text-slate-600">{children}</p>}
    </div>
  );
}

const FEATURES = [
  {
    icon: HardHat,
    title: "PPE compliance",
    text: "Detects workers without a hard hat or high-visibility vest, and only alerts once it's been missing long enough to matter.",
  },
  {
    icon: Cigarette,
    title: "Smoking detection",
    text: "Spots a cigarette near the camera, for no-smoking areas such as fuel stores and site entrances. A second model runs alongside the PPE detector.",
  },
  {
    icon: ShieldAlert,
    title: "Restricted zones",
    text: "Draw zones around excavations, crane swing areas or scaffolds. Get alerted on entry, loitering or too many people at once.",
  },
  {
    icon: Truck,
    title: "Machinery proximity",
    text: "Flags people working too close to excavators, vehicles and other operating machinery: the near misses that become accidents.",
  },
  {
    icon: BellRing,
    title: "Instant alerts",
    text: "Every incident is emailed to the supervisor within seconds, and high and critical ones pop up on the console. Repeats are held back.",
  },
  {
    icon: FileText,
    title: "AI incident reports",
    text: "Each incident comes with a formal, ready-to-file report, written from the facts the system recorded.",
  },
  {
    icon: Camera,
    title: "Evidence attached",
    text: "A snapshot of the moment the rule fired and a short video clip around it, saved with every incident.",
  },
  {
    icon: SlidersHorizontal,
    title: "Your rules, your site",
    text: "Switch any rule off if it doesn't apply to your site, or change how long a violation lasts before it alerts and how serious it is.",
  },
  {
    icon: Clock,
    title: "Working hours",
    text: "Limit a rule to your shifts, for example Sunday to Thursday, 07:00 to 17:00. Night shifts that run past midnight work too.",
  },
];

function Features() {
  return (
    <section id="features" className="scroll-mt-16 bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <SectionHeading eyebrow="Features" title="Everything a site supervisor needs to act fast">
          Built around the hazards that cause the most harm on construction sites, and the paperwork that follows them.
        </SectionHeading>
        <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="group rounded-2xl border border-slate-200 p-7 transition hover:border-slate-300 hover:shadow-lg hover:shadow-slate-900/5">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-950 text-amber-400 transition group-hover:bg-amber-400 group-hover:text-slate-950">
                <Icon className="h-5 w-5" />
              </span>
              <h3 className="mt-5 text-base font-semibold text-slate-900">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  { icon: Camera, title: "See", text: "A camera on site streams to an NVIDIA Jetson edge device, which analyses the video right there." },
  { icon: Cpu, title: "Detect", text: "A YOLO model optimised with TensorRT finds people, PPE and machinery in every frame." },
  { icon: Workflow, title: "Decide", text: "The rule engine checks zones, distances and durations, so brief glimpses don't raise false alarms." },
  { icon: BellRing, title: "Respond", text: "The incident is stored, the report is written and the supervisor is alerted with the evidence." },
];

function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-16 bg-slate-50 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <SectionHeading eyebrow="How it works" title="From camera frame to supervisor alert" center>
          Four stages, each its own service, connected by a fast message stream.
        </SectionHeading>
        <ol className="relative mt-16 grid gap-8 md:grid-cols-4">
          <div className="absolute top-6 right-[12.5%] left-[12.5%] hidden h-px bg-gradient-to-r from-amber-400/0 via-amber-400 to-amber-400/0 md:block" aria-hidden />
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="relative text-center">
              <span className="relative mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-950 text-amber-400 ring-8 ring-slate-50">
                <Icon className="h-5 w-5" />
              </span>
              <p className="mt-5 text-xs font-semibold tracking-wider text-slate-400 uppercase">Step {i + 1}</p>
              <h3 className="mt-1 text-lg font-semibold text-slate-900">{title}</h3>
              <p className="mx-auto mt-2 max-w-xs text-sm leading-6 text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function ReportShowcase() {
  const points = [
    "Uses only the facts recorded for the incident: never invents causes or names",
    "Recommends actions from your site's own approved list",
    "Formal, compliance-ready tone, set per site type",
    "Emailed to supervisors with the snapshot inline and the clip attached",
  ];
  return (
    <section id="reports" className="scroll-mt-16 bg-white py-24 sm:py-32">
      <div className="mx-auto grid max-w-7xl items-center gap-16 px-6 lg:grid-cols-2 lg:px-8">
        <div>
          <SectionHeading eyebrow="Generative AI reporting" title="The incident report writes itself">
            Seconds after an alert, a report is ready for the safety record. It's written by Claude from the structured
            incident data, so it stays factual.
          </SectionHeading>
          <ul className="mt-8 space-y-4">
            {points.map((p) => (
              <li key={p} className="flex gap-3 text-sm leading-6 text-slate-700">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100">
                  <Check className="h-3.5 w-3.5 text-amber-700" />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative">
          <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-amber-100 to-slate-100" aria-hidden />
          <article className="relative rounded-2xl bg-white p-7 shadow-xl ring-1 ring-slate-900/5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">Incident report</p>
                <p className="mt-1 font-semibold text-slate-900">Person near machinery</p>
              </div>
              <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700">CRITICAL</span>
            </div>
            <dl className="grid grid-cols-3 gap-4 border-b border-slate-100 py-4 text-xs">
              <div>
                <dt className="text-slate-400">Camera</dt>
                <dd className="mt-0.5 font-medium text-slate-800">cam_01</dd>
              </div>
              <div>
                <dt className="text-slate-400">Zone</dt>
                <dd className="mt-0.5 font-medium text-slate-800">North gate</dd>
              </div>
              <div>
                <dt className="text-slate-400">Duration</dt>
                <dd className="mt-0.5 font-medium text-slate-800">2.1 s</dd>
              </div>
            </dl>
            <div className="space-y-3 pt-4 text-sm leading-6 text-slate-600">
              <p>
                <span className="font-semibold text-slate-900">Summary.</span> A person was detected within the exclusion
                distance of operating machinery for 2.1 seconds.
              </p>
              <div>
                <p className="font-semibold text-slate-900">Recommended actions</p>
                <ol className="mt-1 list-decimal space-y-1 pl-5">
                  <li>Stop the machine and separate the worker from it immediately.</li>
                  <li>Re-establish the exclusion zone around operating machinery.</li>
                </ol>
              </div>
            </div>
            <div className="mt-5 flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <Mail className="h-4 w-4 text-slate-400" /> Emailed to the site supervisor · snapshot and clip attached
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}

function Technology() {
  const items = [
    { icon: Lock, title: "Private by design", text: "Video is analysed on the edge device, not in the cloud. The AI that writes reports only receives the text facts of an incident." },
    { icon: Puzzle, title: "Plugin architecture", text: "Each site type is a plugin: its model, classes, zones, rules and report style live in one config file." },
    { icon: LayoutDashboard, title: "Live console", text: "A web console with live camera view, real-time alerts and an acknowledge-and-resolve workflow." },
  ];
  return (
    <section id="technology" className="scroll-mt-16 bg-slate-950 py-24 text-white sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold text-amber-400">Technology</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Built on the edge, ready for more than one industry</h2>
        </div>
        <div className="mt-16 grid gap-10 md:grid-cols-3">
          {items.map(({ icon: Icon, title, text }) => (
            <div key={title}>
              <Icon className="h-6 w-6 text-amber-400" />
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
            </div>
          ))}
        </div>

        <div className="mt-16 grid gap-4 sm:grid-cols-2">
          <div className="rounded-2xl bg-white/5 p-6 ring-1 ring-white/10">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-3 font-semibold">
                <HardHat className="h-5 w-5 text-amber-400" /> Construction safety
              </span>
              <span className="rounded-full bg-emerald-400/10 px-2.5 py-0.5 text-xs font-medium text-emerald-300 ring-1 ring-emerald-400/30">
                Available
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-400">
              Hard hats, vests, restricted zones, scaffold capacity, crane swing areas, machinery proximity and smoking. Fall
              detection is next.
            </p>
          </div>
          <div className="rounded-2xl bg-white/5 p-6 ring-1 ring-white/10">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-3 font-semibold">
                <HeartPulse className="h-5 w-5 text-amber-400" /> Healthcare
              </span>
              <span className="rounded-full bg-white/5 px-2.5 py-0.5 text-xs font-medium text-slate-300 ring-1 ring-white/15">
                In development
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-400">The same platform with a plugin for hospital and care settings.</p>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap gap-x-8 gap-y-3 border-t border-white/10 pt-8 text-sm text-slate-500">
          {["NVIDIA Jetson Orin Nano", "YOLO11 + TensorRT", "Redis Streams", "FastAPI + PostgreSQL", "Claude by Anthropic", "React"].map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

const TOUR = [
  { key: "overview", label: "Overview", text: "Today's incidents, what's still open and a live view of the site, on one screen." },
  { key: "cameras", label: "Live cameras", text: "Watch every camera live, with what the detector sees drawn on the video." },
  { key: "incident", label: "Incident", text: "Evidence, the AI report and the acknowledge-and-resolve workflow for each incident." },
  { key: "analytics", label: "Analytics", text: "Spot patterns: the busiest hours, the riskiest zones and the PPE most often missing." },
  { key: "rules", label: "Safety rules", text: "Switch rules on and off, and set when each one applies and how serious it is." },
] as const;

/** Real screenshots of the console (public/screenshots, captured from the running system in test mode). */
function ConsoleTour() {
  const [active, setActive] = useState<(typeof TOUR)[number]["key"]>("overview");
  const current = TOUR.find((t) => t.key === active)!;
  return (
    <section id="console" className="scroll-mt-16 overflow-hidden bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <SectionHeading eyebrow="The console" title="One place to see, act on and learn from every incident" center>
          Supervisors sign in from any browser. New incidents appear the moment they're detected, no refresh needed.
        </SectionHeading>
        <div className="mt-12 flex flex-wrap justify-center gap-2" role="tablist" aria-label="Console screens">
          {TOUR.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={active === t.key}
              onClick={() => setActive(t.key)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                active === t.key ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="mt-4 text-center text-sm text-slate-500">{current.text}</p>
        <div className="relative mx-auto mt-10 max-w-6xl">
          <div className="absolute -inset-x-10 -top-10 -bottom-20 rounded-[3rem] bg-gradient-to-b from-amber-100/70 to-transparent" aria-hidden />
          <div className="relative overflow-hidden rounded-xl bg-slate-900 shadow-2xl ring-1 ring-slate-900/10">
            <div className="flex items-center gap-2 bg-slate-800 px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
              <span className="mx-auto rounded-md bg-slate-900/60 px-16 py-1 text-xs text-slate-400">{PRODUCT_NAME.toLowerCase()} console</span>
            </div>
            {TOUR.map((t) => (
              <img
                key={t.key}
                src={`/screenshots/${t.key}.jpg`}
                alt={`${PRODUCT_NAME} console: ${t.label}`}
                width={1440}
                height={900}
                loading="lazy"
                hidden={active !== t.key}
                className="block w-full"
              />
            ))}
          </div>
        </div>
        <p className="mt-6 text-center text-xs text-slate-400">Screens from the running system, with test-mode data.</p>
      </div>
    </section>
  );
}

const FAQS = [
  {
    q: "Do I need special cameras?",
    a: "No. Any standard USB camera works, and the detector can also read a video file. The reference setup uses a 12 MP Arducam with a 6 mm lens, which reliably sees hard hats up to about 12 m away.",
  },
  {
    q: "Does video leave the site?",
    a: "Video is analysed on the edge device on site. For each incident, a snapshot and a short clip are stored on site and attached to the supervisor's email. The AI that writes the report only receives the text facts of the incident, never images.",
  },
  {
    q: "How do you avoid false alarms?",
    a: "Rules have minimum durations and grace periods: a hard hat has to be missing for several seconds, not one frame, before an alert fires. Repeats of the same rule on the same camera are held back for a few minutes.",
  },
  {
    q: "Can we turn off rules we don't need?",
    a: "Yes. Admins and supervisors can switch any rule off or back on from the console, with no restart, for example if smoking is allowed on your site. Each rule can also be limited to working hours, given a different severity, or set to wait longer before alerting. The console shows who changed what and when.",
  },
  {
    q: "How far away can it spot smoking?",
    a: "A cigarette is much smaller than a hard hat, so smoking detection works at close range, within a few metres of the camera. It's best on a camera covering a no-smoking area, such as a fuel store or a site entrance. Vaping detection is in development.",
  },
  {
    q: "Can the AI report make things up?",
    a: "It's instructed to use only the fields recorded for the incident, never to invent causes or names, and to write NOT SPECIFIED when something is missing. Recommended actions come from the site's own approved list. If the AI is unavailable, a fixed template is used instead.",
  },
  {
    q: "What happens if the internet goes down?",
    a: "Detection, the rules and the local console keep working, because they all run on site. Email and AI reports need the internet; without the AI, reports fall back to the template.",
  },
  {
    q: "Is it only for construction?",
    a: "No. Each type of site is a plugin with its own model, zones, rules and report style. Construction is the first plugin; healthcare is in development.",
  },
  {
    q: "Who can see the console?",
    a: "Only people with an account. Admins add users and choose their role: admin, supervisor (handles incidents) or viewer (read-only).",
  },
];

function Faq() {
  return (
    <section id="faq" className="scroll-mt-16 bg-slate-50 py-24 sm:py-32">
      <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[1fr_2fr] lg:px-8">
        <SectionHeading eyebrow="FAQ" title="Questions, answered">
          The things site managers and safety officers ask first.
        </SectionHeading>
        <div className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
          {FAQS.map(({ q, a }) => (
            <details key={q} className="group px-6 py-5 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium text-slate-900">
                {q}
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm leading-6 text-slate-600">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

const TEAM: { name: string; role?: string }[] = [
  { name: "Albaraa Waheed Farag", role: "Team lead" },
  { name: "Youssef Hazem Mohammed" },
  { name: "Youssef Mohammed Nofal" },
  { name: "Omar Ahmed Abdelnabi" },
  { name: "Abdullah Mohammed Attia" },
  { name: "Ebtsam Mohamed Hassan" },
  { name: "Hassan Salah Eldien Hassan" },
];
const SUPERVISOR = "Dr. Mahmoud Sayed Kamel Hassan";
const UNIVERSITY = "Misr University for Science & Technology";

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, "")
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("");

function Team() {
  return (
    <section id="team" className="scroll-mt-16 bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <SectionHeading eyebrow="About" title="A graduation project, built like a product">
          {PRODUCT_NAME} is a year-4 computer engineering capstone{UNIVERSITY ? ` at ${UNIVERSITY}` : ""}: real-time edge AI
          safety monitoring with configurable plugin rules and generative incident reporting, built over two semesters.
        </SectionHeading>

        <div className="mt-12 flex items-center gap-4 rounded-2xl bg-slate-950 p-6 text-white sm:max-w-md">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-amber-400 text-base font-semibold text-slate-950">
            {initials(SUPERVISOR)}
          </span>
          <div>
            <p className="text-xs font-semibold tracking-wider text-amber-400 uppercase">Supervised by</p>
            <p className="mt-1 text-lg font-semibold">{SUPERVISOR}</p>
          </div>
        </div>

        <p className="mt-12 text-sm font-semibold tracking-wider text-slate-400 uppercase">The team</p>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TEAM.map((m) => (
            <li key={m.name} className="flex items-center gap-3 rounded-2xl border border-slate-200 p-4">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-950 text-sm font-semibold text-amber-400">
                {initials(m.name)}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{m.name}</p>
                {m.role && <p className="text-sm text-amber-700">{m.role}</p>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function CallToAction() {
  return (
    <section className="bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-5xl px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-amber-400 px-8 py-16 text-center sm:px-16">
          <div className="hero-grid-dark absolute inset-0 opacity-30" aria-hidden />
          <h2 className="relative text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">See your site live</h2>
          <p className="relative mx-auto mt-4 max-w-xl text-slate-900/80">
            Sign in to watch your cameras, review today's incidents and read their reports.
          </p>
          <ConsoleButton className="relative mt-8 bg-slate-950 px-6 py-3 text-sm text-white hover:bg-slate-800">
            Sign in to the console <ArrowRight className="h-4 w-4" />
          </ConsoleButton>
          <div className="relative mt-5">
            <DemoBadge dark={false} />
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 py-10 text-sm text-slate-500 sm:flex-row lg:px-8">
        <div className="flex items-center gap-2.5">
          <LogoMark className="h-7 w-7" />
          <span className="font-semibold text-slate-900">{PRODUCT_NAME}</span>
        </div>
        <p>Real-time edge AI safety monitoring with generative incident reporting.</p>
        <p>© {new Date().getFullYear()} {PRODUCT_NAME}</p>
      </div>
    </footer>
  );
}

export function Landing() {
  return (
    <div className="bg-white">
      <Header />
      <main>
        <Hero />
        <Metrics />
        <Features />
        <HowItWorks />
        <ConsoleTour />
        <ReportShowcase />
        <Technology />
        <Faq />
        <Team />
        <CallToAction />
      </main>
      <Footer />
    </div>
  );
}
