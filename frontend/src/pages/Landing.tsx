import { ArrowRight, Check, Mail } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LogoMark, PRODUCT_NAME } from "../components/Brand";
import { CameraFrame } from "../components/CameraFrame";
import {
  AutoVideo,
  Chapter,
  ChapterIndex,
  DenseList,
  Flourish,
  Photo,
  PillLink,
  ROMAN,
  useScrollState,
  type ChapterInfo,
} from "../components/edition";
import { useAuth } from "../lib/auth";
import { CONSOLE_URL, IS_STATIC_SITE, useDemoStatus, type DemoStatus } from "../lib/site";

const CHAPTERS: ChapterInfo[] = [
  { id: "ppe", title: "PPE" },
  { id: "smoking", title: "Smoking" },
  { id: "zones", title: "Zones" },
  { id: "alerts", title: "Alerts" },
  { id: "rules", title: "Your rules" },
  { id: "console", title: "Console" },
  { id: "edge", title: "On the edge" },
];

function ConsoleButton({ className = "", children }: { className?: string; children?: ReactNode }) {
  const { user } = useAuth();
  const classes = `inline-flex items-center justify-center gap-2 rounded-full font-semibold transition ${className}`;
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
        dark ? "bg-black/30 text-paper ring-white/15 backdrop-blur" : "bg-white/60 text-ink/70 ring-ink/10"
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

function TopBar({ surface }: { surface: "dark" | "light" }) {
  const onDark = surface === "dark";
  return (
    <header data-overlay className="fixed inset-x-0 top-0 z-40">
      <div
        className={`flex h-16 items-center gap-6 px-5 transition-colors duration-300 sm:px-6 ${
          onDark ? "text-paper" : "bg-paper/80 text-ink backdrop-blur-md"
        }`}
      >
        <Link to="/" className="flex items-center gap-2.5">
          <LogoMark className="h-7 w-7" />
          <span className="font-display text-[15px] font-semibold tracking-tight">{PRODUCT_NAME}</span>
          <span className={`hidden font-display text-[15px] sm:inline ${onDark ? "text-paper/55" : "text-ink/45"}`}>
            Construction safety
          </span>
        </Link>
        <nav className="ml-auto hidden items-center gap-6 font-display text-sm md:flex">
          <a href="#faq" className="opacity-80 hover:opacity-100">
            FAQ
          </a>
          <a href="#team" className="opacity-80 hover:opacity-100">
            Team
          </a>
        </nav>
        <ConsoleButton
          className={`ml-auto px-4 py-2 text-sm md:ml-0 ${onDark ? "bg-paper text-ink hover:bg-white" : "bg-ink text-paper hover:bg-black"}`}
        />
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative h-[100svh] min-h-[640px] overflow-hidden bg-ink" data-surface="dark">
      <Photo name="hero" eager className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/50 via-black/10 to-black/60" aria-hidden />
      <div className="relative flex h-full items-center justify-center px-5 pt-16">
        {/* framed contents, like the title page of a printed edition */}
        <div className="w-full max-w-md border border-paper/50 bg-black/25 p-6 text-paper backdrop-blur-[2px] sm:p-8">
          <h1 className="font-display text-4xl leading-[0.95] font-semibold tracking-[-0.03em] sm:text-5xl">
            Every risk on site,
            <br />
            <span className="font-serif font-normal italic">caught</span> as it happens.
          </h1>
          <p className="mt-8 font-serif text-xl leading-snug text-paper/90">
            {PRODUCT_NAME} turns your site cameras into a safety officer that never looks away. Seven chapters, one safer site.
          </p>
          <ol className="mt-6 space-y-0.5">
            {CHAPTERS.map((c, i) => (
              <li key={c.id}>
                <a href={`#${c.id}`} className="group flex items-baseline gap-2 font-display text-lg leading-tight font-semibold">
                  <span className="group-hover:text-amber-300">{c.title}</span>
                  <span className="mb-1 flex-1 border-b border-dotted border-transparent group-hover:border-paper/60" />
                  <span className="font-serif text-sm font-normal text-paper/70">{ROMAN[i]}</span>
                </a>
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <ConsoleButton className="bg-amber-400 px-5 py-2.5 text-sm text-ink hover:bg-amber-300">
              Sign in to the console <ArrowRight className="h-4 w-4" />
            </ConsoleButton>
            <DemoBadge />
          </div>
        </div>
      </div>
    </section>
  );
}

/** Text block that opens a chapter's content: serif initial headline, then a lead paragraph. */
function Lead({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="reveal max-w-3xl">
      <Flourish text={title} />
      <p className="mt-6 max-w-2xl text-lg leading-8 text-ink/70">{children}</p>
    </div>
  );
}

/** A card: media on top, a bold name and a short muted description under it. */
function Card({ media, title, children, link, className = "", bare = false }: {
  media: ReactNode;
  title: string;
  children: ReactNode;
  link?: [string, string];
  className?: string;
  bare?: boolean; // media draws its own frame (and may overflow it)
}) {
  return (
    <figure className={`reveal ${className}`}>
      {bare ? media : <div className="overflow-hidden rounded-md bg-ink/5 ring-1 ring-ink/10">{media}</div>}
      <figcaption className="mt-3">
        <p className="font-display font-semibold">{title}</p>
        <p className="mt-0.5 max-w-md text-[15px] leading-6 text-ink/60">{children}</p>
        {link && <PillLink href={link[1]}>{link[0]}</PillLink>}
      </figcaption>
    </figure>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="reveal border-t border-ink/20 pt-4">
      <p className="font-display text-5xl font-semibold tracking-tight sm:text-6xl">{value}</p>
      <p className="mt-2 max-w-[16rem] text-sm leading-6 text-ink/60">{label}</p>
    </div>
  );
}

function PpeChapter() {
  return (
    <Chapter id="ppe" n={1} title="Hard hats & vests" kicker="The basics, checked on every frame, by every camera." photo="ppe">
      <Lead title="Nothing missed, nothing nagged">
        The detector finds every worker and checks for a hard hat and a high-visibility vest. An alert only fires once
        something has been missing for a few seconds, so a hat lifted to wipe a brow doesn't page the supervisor.
      </Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.4fr_1fr] xl:items-start">
        <Card media={<div className="px-4 pt-8 pb-10 sm:px-10"><CameraFrame /></div>} bare title="What the camera sees">
          A stylised frame: each person, hard hat, vest and machine is boxed, and a worker without a hard hat is flagged in red.
        </Card>
        <div className="grid gap-10 sm:grid-cols-2 xl:grid-cols-1">
          <Stat value="2 rules" label="Hard hat and vest are separate, so a site that doesn't need vests can switch just that one off." />
          <Stat value="~12 m" label="Hard hats are reliably seen up to about 12 metres from the reference camera." />
        </div>
      </div>
      <DenseList
        items={[
          ["Missing, not just absent", "A NO-Hardhat detection or no hard hat at all over the head both count, so it works in either case."],
          ["Grace for dropouts", "A detector blink shorter than a second doesn't restart the timer."],
          ["Zone-only PPE", "A PPE rule can apply to one zone only, such as the scaffold."],
          ["Who was missing what", "Each incident records which item was missing, and Analytics shows the most-missed item."],
        ]}
      />
    </Chapter>
  );
}

function SmokingChapter() {
  return (
    <Chapter id="smoking" n={2} title="Smoking" kicker="Clear air around the fuel store and the gate." photo="smoking">
      <Lead title="A second pair of eyes for one small thing">
        A cigarette is tiny next to a hard hat, so {PRODUCT_NAME} runs a second, dedicated model next to the PPE detector, on
        the same frames. Put it on a camera that covers a no-smoking area, such as a fuel store, gas cylinders or the site
        entrance.
      </Lead>
      <div className="mt-16 grid gap-10 sm:grid-cols-3">
        <Stat value="0.82" label="mAP50 on 111 held-out test images (CigDet dataset)." />
        <Stat value="4.4 ms" label="Per image for the smoking model on a laptop GPU." />
        <Stat value="2 models" label="The PPE detector and the smoking model look at the same frames, side by side." />
      </div>
      <DenseList
        items={[
          ["Separate switch", "Smoking is its own rule. Sites that allow it switch it off in one click."],
          ["Two seconds, not one frame", "A cigarette has to stay visible for two seconds before an alert fires."],
          ["Approved actions", "The report suggests putting it out, checking for nearby fuel, and a toolbox-talk reminder."],
          ["Vaping", "In development: it needs a model trained on vapes, and it will be a separate rule."],
        ]}
      />
    </Chapter>
  );
}

function ZonesChapter() {
  return (
    <Chapter id="zones" n={3} title="Zones & machinery" kicker="Keep out means keep out." photo="zones">
      <Lead title="Lines on the ground the camera can see">
        Draw zones around an excavation, under a crane or on a scaffold. {PRODUCT_NAME} knows where each person is standing
        and raises an alert on entry, on loitering, or when too many people are inside, and whenever someone gets too close to
        working machinery.
      </Lead>
      <div className="mt-16 grid gap-x-8 gap-y-12 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["Restricted entry", "Anyone stepping into the excavation edge, straight away.", "HIGH"],
          ["Loitering", "Staying under the crane swing area for 30 seconds.", "MEDIUM"],
          ["Over capacity", "More than three workers on scaffold level 1.", "MEDIUM"],
          ["Machinery proximity", "A worker within half a body-height of a machine.", "CRITICAL"],
        ].map(([title, text, severity]) => (
          <div key={title} className="reveal border-t border-ink/20 pt-4">
            <p className="font-display text-xs font-semibold tracking-widest text-amber-700">{severity}</p>
            <p className="mt-2 font-display text-2xl font-semibold tracking-tight">{title}</p>
            <p className="mt-2 text-[15px] leading-6 text-ink/60">{text}</p>
          </div>
        ))}
      </div>
      <DenseList
        items={[
          ["Feet, not boxes", "A person is inside a zone when their feet are, so leaning over a barrier isn't entry."],
          ["Distance that scales", "Proximity is measured against the person's size in the image, so it works near and far."],
          ["Per camera", "Each zone belongs to one camera's view."],
          ["Your numbers", "Durations, capacity and severity can be changed per site in the console."],
        ]}
      />
    </Chapter>
  );
}

function AlertsChapter() {
  return (
    <Chapter id="alerts" n={4} title="Alerts & reports" kicker="Seconds from the camera to the supervisor's phone." photo="alerts">
      <Lead title="The report writes itself">
        When a rule fires, the incident appears on the console straight away, the supervisor gets an email with a snapshot
        and a short clip, and a formal report is written from the recorded facts by Claude, ready for the safety record.
      </Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.35fr_1fr] xl:items-start">
        <Card
          media={<AutoVideo name="overview" label="The console overview as new incidents arrive" />}
          title="Live, with no refresh"
          link={["How alerts work", "#faq"]}
        >
          The control room tells you the site's state in one sentence; new incidents slide into the live feed and the numbers count up.
        </Card>
        <figure className="reveal">
          <article className="rounded-md bg-white p-6 shadow-sm ring-1 ring-ink/10">
            <div className="flex items-center justify-between border-b border-ink/10 pb-4">
              <div>
                <p className="text-xs font-semibold tracking-wide text-ink/40 uppercase">Incident report</p>
                <p className="mt-1 font-display font-semibold">Person near machinery</p>
              </div>
              <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700">CRITICAL</span>
            </div>
            <div className="space-y-3 pt-4 text-sm leading-6 text-ink/70">
              <p>
                <span className="font-semibold text-ink">Summary.</span> A person was detected within the exclusion distance
                of operating machinery for 2.1 seconds.
              </p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>Stop the machine and separate the worker from it immediately.</li>
                <li>Re-establish the exclusion zone around operating machinery.</li>
              </ol>
            </div>
            <p className="mt-5 flex items-center gap-2 rounded bg-paper px-3 py-2 text-xs text-ink/60">
              <Mail className="h-4 w-4" /> Emailed to the site supervisor · snapshot and clip attached
            </p>
          </article>
          <figcaption className="mt-3">
            <p className="font-display font-semibold">Factual by design</p>
            <ul className="mt-2 space-y-1.5 text-[15px] leading-6 text-ink/60">
              {[
                "Uses only the facts recorded for the incident",
                "Recommends actions from the site's approved list",
                "Falls back to a fixed template if the AI is unavailable",
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-amber-700" /> {t}
                </li>
              ))}
            </ul>
          </figcaption>
        </figure>
      </div>
      <DenseList
        items={[
          ["Evidence attached", "A snapshot of the moment the rule fired and a clip around it, saved with every incident."],
          ["No alert storms", "The same rule on the same camera isn't emailed again within a few minutes."],
          ["Desktop and sound", "High and critical incidents can pop up and chime on the supervisor's computer."],
          ["Acknowledge, resolve", "Each incident has a status and a note, so nothing is handled twice or forgotten."],
        ]}
      />
    </Chapter>
  );
}

function RulesChapter() {
  return (
    <Chapter id="rules" n={5} title="Your site, your rules" kicker="Every site is different. The rules should be too." photo="rules">
      <Lead title="Switch it off, or tune it">
        Admins and supervisors decide which rules apply. Switch off what doesn't matter on your site, change how serious a
        violation is and how long it must last, and limit a rule to your working hours. Changes apply within seconds, with no
        restart.
      </Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.35fr_1fr] xl:items-start">
        <Card
          media={<AutoVideo name="rules" label="Switching the smoking rule off and on, then setting its working hours" />}
          title="Safety rules page"
          link={["Can we turn off rules?", "#faq"]}
        >
          Switching smoking off and back on, then limiting it to Sunday to Thursday, 07:00 to 17:00. Changes apply within seconds.
        </Card>
        <div className="grid gap-10 sm:grid-cols-2 xl:grid-cols-1">
          <Stat value="6 controls" label="On or off, severity, alert delay, repeat interval, capacity for crowded zones and working hours." />
          <Stat value="Sun–Thu" label="Working hours in site time, including night shifts that run past midnight." />
        </div>
      </div>
      <DenseList
        items={[
          ["Who changed what", "Each rule shows who last changed it and when."],
          ["Back to defaults", "One click returns a rule to the plugin's values."],
          ["Coming soon, shown honestly", "Rules that aren't ready yet are listed separately and can't be switched on."],
          ["Read-only viewers", "Viewers see the rules but can't change them."],
        ]}
      />
    </Chapter>
  );
}

const TOUR = [
  { key: "signin", label: "Sign in", text: "Each person signs in with their own account; roles decide what they can change." },
  { key: "overview", label: "Overview", text: "A control room: the site's state in one sentence, the live camera, and new incidents as they arrive." },
  { key: "cameras", label: "Live cameras", text: "Watch every camera live, with what the detector sees drawn on the video." },
  { key: "incident", label: "Incident", text: "Each incident opens on its own snapshot, with the clip, the emailed AI report and the acknowledge-and-resolve workflow." },
  { key: "analytics", label: "Analytics", text: "Spot patterns: the busiest hours, the riskiest zones and the PPE most often missing." },
  { key: "rules", label: "Safety rules", text: "Switch rules on and off, and set when each one applies and how serious it is." },
] as const;

function ConsoleChapter() {
  const [active, setActive] = useState<(typeof TOUR)[number]["key"]>("overview");
  const current = TOUR.find((t) => t.key === active)!;
  return (
    <Chapter id="console" n={6} title="The console" kicker="One place to see, act on and learn from every incident." photo="console">
      <Lead title="Open it from any browser">
        Supervisors sign in from the site office or their phone. Roles keep it simple: admins manage users, supervisors handle
        incidents, and viewers can look but not change anything.
      </Lead>
      <div className="reveal mt-14 flex flex-wrap gap-2" role="tablist" aria-label="Console screens">
        {TOUR.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={active === t.key}
            onClick={() => setActive(t.key)}
            className={`rounded-full px-4 py-2 font-display text-sm font-medium transition ${
              active === t.key ? "bg-ink text-paper" : "bg-ink/5 text-ink/70 hover:bg-ink/10"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <figure className="reveal mt-6">
        <div className="overflow-hidden rounded-md shadow-2xl ring-1 ring-ink/10">
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
        <figcaption className="mt-3 text-[15px] text-ink/60">
          {current.text} <span className="text-ink/40">Screens from the running system, with test-mode data.</span>
        </figcaption>
      </figure>
    </Chapter>
  );
}

function EdgeChapter() {
  const steps = [
    ["See", "A camera on site streams to an NVIDIA Jetson edge device, which analyses the video right there."],
    ["Detect", "YOLO models optimised with TensorRT find people, PPE, machinery and cigarettes in every frame."],
    ["Decide", "The rule engine checks zones, distances, durations and working hours, so glimpses don't raise alarms."],
    ["Respond", "The incident is stored, the report is written and the supervisor is alerted with the evidence."],
  ];
  return (
    <Chapter id="edge" n={7} title="On the edge" kicker="The video never has to leave the site." photo="how">
      <Lead title="Built where the cameras are">
        Detection, rules and the console all run on a small computer on site. Only the text facts of an incident go to the AI
        that writes the report, never images.
      </Lead>
      <ol className="mt-16 grid gap-x-8 gap-y-12 md:grid-cols-2 xl:grid-cols-4">
        {steps.map(([title, text], i) => (
          <li key={title} className="reveal border-t border-ink/20 pt-4">
            <p className="font-serif text-lg text-amber-700 italic">Step {ROMAN[i]}</p>
            <p className="mt-1 font-display text-2xl font-semibold tracking-tight">{title}</p>
            <p className="mt-2 text-[15px] leading-6 text-ink/60">{text}</p>
          </li>
        ))}
      </ol>
      <div className="mt-16 grid gap-4 md:grid-cols-2">
        {[
          ["Construction safety", "Available", "Hard hats, vests, restricted zones, scaffold capacity, crane swing areas, machinery proximity and smoking. Fall detection is next."],
          ["Healthcare", "In development", "The same platform with a plugin for hospital and care settings."],
        ].map(([title, status, text]) => (
          <div key={title} className="reveal rounded-md bg-ink p-6 text-paper">
            <div className="flex items-center justify-between gap-4">
              <p className="font-display text-xl font-semibold">{title}</p>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status === "Available" ? "bg-emerald-400/15 text-emerald-300" : "bg-white/10 text-paper/70"}`}>
                {status}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-paper/60">{text}</p>
          </div>
        ))}
      </div>
      <DenseList
        items={[
          ["Plugins", "Each site type is one config file: its models, classes, zones, rules and report style."],
          ["Works offline", "Detection, rules and the local console keep working without internet; email and AI wait."],
          ["Standard cameras", "Any USB camera works. The reference setup is a 12 MP Arducam with a 6 mm lens."],
          ["The stack", "Jetson Orin Nano, YOLO11 + TensorRT, Redis Streams, FastAPI + PostgreSQL, Claude, React."],
        ]}
      />
    </Chapter>
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
    <section id="faq" className="paper-grain relative z-10 scroll-mt-16 bg-paper text-ink" data-surface="light">
      <div className="grid gap-12 px-5 py-24 sm:px-8 sm:py-32 lg:grid-cols-[1fr_2fr] lg:pr-12 lg:pl-[17rem]">
        <div className="reveal">
          <Flourish text="Questions, answered" />
          <p className="mt-5 text-lg leading-8 text-ink/70">The things site managers and safety officers ask first.</p>
        </div>
        <div className="reveal divide-y divide-ink/15 border-y border-ink/15">
          {FAQS.map(({ q, a }) => (
            <details key={q} className="group py-5 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-display text-lg font-semibold">
                {q}
                <span className="font-serif text-2xl leading-none text-amber-700 transition group-open:rotate-45">+</span>
              </summary>
              <p className="mt-3 max-w-2xl leading-7 text-ink/65">{a}</p>
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

function Team() {
  return (
    <section id="team" className="relative z-10 scroll-mt-16 bg-ink text-paper" data-surface="dark">
      <div className="px-5 py-24 sm:px-8 sm:py-32 lg:pr-12 lg:pl-[17rem]">
        <div className="reveal max-w-3xl">
          <h2 className="font-serif text-[2.6rem] leading-[1.05] tracking-tight sm:text-6xl">
            <span className="mr-[0.02em] inline-block align-[-0.08em] text-[1.45em] leading-none text-amber-400 italic">A</span>
            graduation project, built like a product
          </h2>
          <p className="mt-6 text-lg leading-8 text-paper/70">
            {PRODUCT_NAME} is a fifth-year computer engineering capstone at {UNIVERSITY}: real-time edge AI safety monitoring with
            configurable plugin rules and generative incident reporting, built over two semesters.
          </p>
        </div>
        <div className="reveal mt-14 grid gap-x-12 gap-y-6 md:grid-cols-[16rem_1fr]">
          <div>
            <p className="font-serif text-lg text-amber-400 italic">Supervised by</p>
            <p className="mt-1 font-display text-xl font-semibold">{SUPERVISOR}</p>
          </div>
          <div>
            <p className="font-serif text-lg text-amber-400 italic">The team</p>
            <ul className="mt-1 grid gap-x-8 gap-y-1 sm:grid-cols-2">
              {TEAM.map((m) => (
                <li key={m.name} className="font-display text-xl font-semibold">
                  {m.name} {m.role && <span className="font-serif text-base font-normal text-paper/60 italic">{m.role}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Closing() {
  return (
    <section className="relative z-10 h-[80svh] min-h-[520px] overflow-hidden bg-ink" data-surface="dark">
      <Photo name="closing" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/20 to-black/30" aria-hidden />
      <div className="relative flex h-full flex-col justify-end px-5 pb-14 text-paper sm:px-8 lg:pr-12 lg:pl-[17rem]">
        <h2 className="max-w-4xl font-display text-[clamp(3rem,9vw,8rem)] leading-[0.88] font-semibold tracking-[-0.045em]">
          See your site <span className="font-serif font-normal italic">live.</span>
        </h2>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ConsoleButton className="bg-amber-400 px-6 py-3 text-sm text-ink hover:bg-amber-300">
            Sign in to the console <ArrowRight className="h-4 w-4" />
          </ConsoleButton>
          <DemoBadge />
        </div>
      </div>
    </section>
  );
}

const CREDITS = [
  "Nicolas Beuret",
  "Heri Susilo",
  "Michelle Ding",
  "Troy Mortier",
  "Tsuyoshi Kozu",
  "Glenov Brankovic",
  "Jerry Wei",
  "Centar MURID",
  "Tunahan Kuzgun",
];

function Footer() {
  return (
    <footer className="relative z-10 bg-ink text-paper/50" data-surface="dark">
      <div className="flex flex-col gap-4 border-t border-white/10 px-5 py-10 text-xs sm:px-8 lg:flex-row lg:items-center lg:justify-between lg:pr-12 lg:pl-[17rem]">
        <div className="flex items-center gap-2.5 text-paper">
          <LogoMark className="h-6 w-6" />
          <span className="font-display text-sm font-semibold">{PRODUCT_NAME}</span>
          <span className="text-paper/50">© {new Date().getFullYear()}</span>
        </div>
        <p className="max-w-2xl leading-5">
          Photos from Unsplash by {CREDITS.join(", ")}. Console screens and recordings are from the running system in test mode.
        </p>
      </div>
    </footer>
  );
}

export function Landing() {
  // what's under the top bar decides whether it's light or dark
  const probeTop = useCallback(() => ({ x: window.innerWidth / 2, y: 32 }), []);
  const { active, surface: topSurface } = useScrollState(CHAPTERS, probeTop);

  return (
    <div className="bg-paper font-display text-ink">
      <TopBar surface={topSurface} />
      <ChapterIndex chapters={CHAPTERS} active={active} />
      <main>
        <Hero />
        <PpeChapter />
        <SmokingChapter />
        <ZonesChapter />
        <AlertsChapter />
        <RulesChapter />
        <ConsoleChapter />
        <EdgeChapter />
        <Faq />
        <Team />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
