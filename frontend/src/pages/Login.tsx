import { ArrowLeft, BellRing, Camera, Eye, EyeOff, FileText, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { LogoMark, PRODUCT_NAME } from "../components/Brand";
import { useAuth } from "../lib/auth";

const POINTS = [
  { icon: Camera, text: "Live view of every camera, with detections drawn in real time" },
  { icon: BellRing, text: "Instant alerts for missing PPE, restricted zones and machinery" },
  { icon: FileText, text: "An AI-written incident report with evidence for every alert" },
];

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
          ? "Incorrect email or password."
          : err instanceof ApiError && err.status === 429
            ? err.message
            : "Can't reach the server. Check that the backend is running.",
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
          <h2 className="font-serif text-5xl leading-[1.05] tracking-tight">
            <span className="text-[1.3em] leading-none text-amber-400 italic">T</span>he safety console for your site.
          </h2>
          <p className="mt-4 text-paper/70">Sign in to watch your cameras live and respond to alerts as they happen.</p>
          <ul className="mt-8 space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-paper/80">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/30 ring-1 ring-white/15 backdrop-blur">
                  <Icon className="h-4 w-4 text-amber-400" />
                </span>
                <span className="pt-1.5">{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-12 text-xs text-paper/50">For authorized site personnel only.</p>
      </div>

      {/* form */}
      <div className="flex flex-1 flex-col px-6 py-8 sm:px-12">
        <Link to="/" className="inline-flex items-center gap-1.5 self-start text-sm text-ink/55 hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Back to site
        </Link>
        <div className="m-auto w-full max-w-sm py-12">
          <div className="lg:hidden">
            <LogoMark className="h-10 w-10" />
          </div>
          <h1 className="mt-6 font-serif text-5xl tracking-tight lg:mt-0">
            <span className="text-[1.3em] leading-none text-amber-600 italic">S</span>ign in
          </h1>
          <p className="mt-2 text-sm text-ink/55">Use the account your site administrator gave you.</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <label className="block">
              <span className="text-sm font-medium text-ink/75">Email</span>
              <input
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 block w-full rounded-lg border border-ink/20 bg-white px-3 py-2.5 text-sm text-ink shadow-sm placeholder:text-ink/35 focus:border-ink focus:ring-1 focus:ring-ink focus:outline-none"
                placeholder="you@company.com"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-ink/75">Password</span>
              <span className="relative mt-1.5 block">
                <input
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full rounded-lg border border-ink/20 bg-white px-3 py-2.5 pr-10 text-sm text-ink shadow-sm focus:border-ink focus:ring-1 focus:ring-ink focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-700"
                  aria-label={show ? "Hide password" : "Show password"}
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
              Sign in
            </button>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">
            Forgot your password? Ask your site administrator to reset it.
          </p>
        </div>
      </div>
    </div>
  );
}
