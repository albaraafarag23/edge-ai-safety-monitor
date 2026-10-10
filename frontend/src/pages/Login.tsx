import { ArrowLeft, BellRing, Camera, Eye, EyeOff, FileText, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { LogoMark, PRODUCT_NAME } from "../components/Brand";
import { splitInitial } from "../components/edition";
import { useAuth } from "../lib/auth";
import { bilingual, LanguageSwitch, useLang, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    points: [
      "Live view of every camera, with detections drawn in real time",
      "Instant alerts for missing PPE, restricted zones and machinery",
      "An AI-written incident report with evidence for every alert",
    ],
    panelTitle: "The safety console for your site.",
    panelLead: "Sign in to watch your cameras live and respond to alerts as they happen.",
    authorizedOnly: "For authorized site personnel only.",
    back: "Back to site",
    title: "Sign in",
    lead: "Use the account your site administrator gave you.",
    email: "Email",
    password: "Password",
    showPassword: "Show password",
    hidePassword: "Hide password",
    submit: "Sign in",
    forgot: "Forgot your password? Ask your site administrator to reset it.",
    wrong: "Incorrect email or password.",
    tooMany: null as string | null, // the server's own message
    unreachable: "Can't reach the server. Check that the backend is running.",
  },
  {
    points: [
      "بث مباشر من كل كاميرا، مع ما يُرصد مرسومًا لحظيًا",
      "تنبيهات فورية لنقص معدات الوقاية والمناطق المحظورة والآليات",
      "تقرير حادثة يكتبه الذكاء الاصطناعي مع الأدلة لكل تنبيه",
    ],
    panelTitle: "لوحة تحكم السلامة لموقعك.",
    panelLead: "سجّل الدخول لمشاهدة كاميراتك مباشرةً والاستجابة للتنبيهات لحظة حدوثها.",
    authorizedOnly: "للعاملين المصرح لهم في الموقع فقط.",
    back: "العودة إلى الموقع",
    title: "تسجيل الدخول",
    lead: "استخدم الحساب الذي أعطاك إياه مسؤول الموقع.",
    email: "البريد الإلكتروني",
    password: "كلمة المرور",
    showPassword: "إظهار كلمة المرور",
    hidePassword: "إخفاء كلمة المرور",
    submit: "دخول",
    forgot: "نسيت كلمة المرور؟ اطلب من مسؤول الموقع إعادة تعيينها.",
    wrong: "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    tooMany: "محاولات كثيرة لتسجيل الدخول. انتظر بضع دقائق ثم حاول مرة أخرى.",
    unreachable: "تعذّر الوصول إلى الخادم. تأكد من أن الخادم يعمل.",
  },
);
const POINT_ICONS = [Camera, BellRing, FileText];

/** Serif heading with a large amber initial (a whole first word in Arabic, see splitInitial). */
function InitialHeading({ text, color, className }: { text: string; color: string; className: string }) {
  const { lang } = useLang();
  const [initial, rest] = splitInitial(text, lang);
  return (
    <h1 className={className}>
      <span className={`leading-none italic ${color} ${lang === "ar" ? "text-[1.1em]" : "text-[1.3em]"}`}>{initial}</span>
      {rest}
    </h1>
  );
}

/** Only allow redirects within the console after sign-in (no open redirects). */
function safeNext(next: string | null) {
  return next && next.startsWith("/app") ? next : "/app";
}

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const t = useText(TEXT);

  if (user) return <Navigate to={next} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? t.wrong
          : err instanceof ApiError && err.status === 429
            ? (t.tooMany ?? err.message)
            : t.unreachable,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="paper-grain flex min-h-screen bg-paper font-display text-ink">
      {/* brand panel */}
      <div className="relative hidden w-[48%] overflow-hidden bg-ink p-12 text-paper lg:flex lg:flex-col">
        <img
          src="/edition/hero-1200.webp"
          srcSet="/edition/hero-1200.webp 1200w, /edition/hero-2400.webp 2400w"
          sizes="48vw"
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          aria-hidden
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-black/40" aria-hidden />
        <Link to="/" className="relative flex items-center gap-2.5">
          <LogoMark />
          <span className="text-[15px] font-semibold">{PRODUCT_NAME}</span>
        </Link>
        <div className="relative mt-auto max-w-md">
          <InitialHeading text={t.panelTitle} color="text-amber-400" className="font-serif text-5xl leading-[1.05] tracking-tight" />
          <p className="mt-4 text-paper/70">{t.panelLead}</p>
          <ul className="mt-8 space-y-4">
            {t.points.map((text, i) => ({ text, Icon: POINT_ICONS[i] })).map(({ Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-paper/80">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/30 ring-1 ring-white/15 backdrop-blur">
                  <Icon className="h-4 w-4 text-amber-400" />
                </span>
                <span className="pt-1.5">{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-12 text-xs text-paper/50">{t.authorizedOnly}</p>
      </div>

      {/* form */}
      <div className="flex flex-1 flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between">
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink/55 hover:text-ink">
            <ArrowLeft className="flip-rtl h-4 w-4" /> {t.back}
          </Link>
          <LanguageSwitch className="text-ink/70 ring-1 ring-ink/15 hover:bg-ink/5" />
        </div>
        <div className="m-auto w-full max-w-sm py-12">
          <div className="lg:hidden">
            <LogoMark className="h-10 w-10" />
          </div>
          <InitialHeading text={t.title} color="text-amber-600" className="mt-6 font-serif text-5xl tracking-tight lg:mt-0" />
          <p className="mt-2 text-sm text-ink/55">{t.lead}</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <label className="block">
              <span className="text-sm font-medium text-ink/75">{t.email}</span>
              <input
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 block w-full rounded-lg border border-ink/20 bg-white px-3 py-2.5 text-sm text-ink shadow-sm placeholder:text-ink/35 focus:border-ink focus:ring-1 focus:ring-ink focus:outline-none"
                placeholder="you@company.com"
                dir="ltr"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-ink/75">{t.password}</span>
              <span className="relative mt-1.5 block">
                <input
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full rounded-lg border border-ink/20 bg-white px-3 py-2.5 pe-10 text-sm text-ink shadow-sm focus:border-ink focus:ring-1 focus:ring-ink focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute inset-y-0 end-0 flex items-center px-3 text-slate-400 hover:text-slate-700"
                  aria-label={show ? t.hidePassword : t.showPassword}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </span>
            </label>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || !email || !password}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-ink px-4 py-3 text-sm font-semibold text-paper shadow-sm hover:bg-black disabled:opacity-50"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {t.submit}
            </button>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">
            {t.forgot}
          </p>
        </div>
      </div>
    </div>
  );
}
