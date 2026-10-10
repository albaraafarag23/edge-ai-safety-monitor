import { Check, FileText, HardHat } from "lucide-react";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    camera: "North gate · cam_01",
    live: "LIVE",
    frameLabel: "Example camera frame with detections",
    alertTitle: "PPE missing",
    alertWhere: "North gate · just now",
    high: "HIGH",
    alertText: "Worker without a hard hat for 3.4 s. Supervisor emailed with snapshot and clip.",
    report: "AI incident report",
    ready: "Ready for review",
  },
  {
    camera: "البوابة الشمالية · cam_01",
    live: "مباشر",
    frameLabel: "مثال لإطار كاميرا مع ما رُصد فيه",
    alertTitle: "معدات وقاية ناقصة",
    alertWhere: "البوابة الشمالية · الآن",
    high: "مرتفع",
    alertText: "عامل بلا خوذة لمدة 3.4 ثانية. أُرسل بريد إلى المشرف مع اللقطة والمقطع.",
    report: "تقرير الحادثة بالذكاء الاصطناعي",
    ready: "جاهز للمراجعة",
  },
);

/** A stylised camera frame: what the detector sees and flags. Pure SVG, no real footage.
 * The boxes keep the model's English class names, as the real detector draws them. */
export function CameraFrame() {
  const t = useText(TEXT);
  return (
    <div className="relative">
      <div className="absolute -inset-8 rounded-[2rem] bg-amber-400/10 blur-3xl" aria-hidden />
      <div className="relative overflow-hidden rounded-2xl bg-slate-900 shadow-2xl ring-1 ring-white/10">
        {/* window bar */}
        <div className="flex items-center gap-2 border-b border-white/10 bg-slate-900/80 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="ms-3 text-xs text-slate-400">{t.camera}</span>
          <span className="ms-auto inline-flex items-center gap-1.5 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-white">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> {t.live}
          </span>
        </div>

        <svg viewBox="0 0 640 380" className="block w-full" style={{ direction: "ltr" }} role="img" aria-label={t.frameLabel}>
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
      <div className="float-slow absolute -bottom-8 -start-4 w-64 rounded-xl bg-white p-4 shadow-2xl ring-1 ring-slate-900/5 sm:-start-10">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-100">
            <HardHat className="h-4 w-4 text-orange-600" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">{t.alertTitle}</p>
            <p className="text-xs text-slate-500">{t.alertWhere}</p>
          </div>
          <span className="ms-auto rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-bold text-orange-700">{t.high}</span>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-600">{t.alertText}</p>
      </div>

      {/* report card */}
      <div className="float-slower absolute -top-6 -end-3 hidden w-56 rounded-xl bg-white/95 p-3.5 shadow-2xl ring-1 ring-slate-900/5 backdrop-blur sm:block lg:-end-8">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
          <FileText className="h-3.5 w-3.5" /> {t.report}
        </p>
        <div className="mt-2 space-y-1.5">
          <div className="h-1.5 w-full rounded bg-slate-200" />
          <div className="h-1.5 w-11/12 rounded bg-slate-200" />
          <div className="h-1.5 w-4/6 rounded bg-slate-200" />
        </div>
        <p className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-emerald-700">
          <Check className="h-3.5 w-3.5" /> {t.ready}
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
