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
          : "Can't reach the server. Check that the backend is running.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-white">
      {/* brand panel */}
      <div className="relative hidden w-[46%] overflow-hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col">
        <div className="hero-grid absolute inset-0 opacity-40" aria-hidden />
        <div className="absolute -top-40 -left-40 h-96 w-96 rounded-full bg-amber-400/20 blur-3xl" aria-hidden />
        <Link to="/" className="relative flex items-center gap-2.5">
          <LogoMark />
          <span className="text-[15px] font-semibold">{PRODUCT_NAME}</span>
        </Link>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl font-semibold tracking-tight">The safety console for your site.</h2>
          <p className="mt-3 text-slate-400">Sign in to watch your cameras live and respond to alerts as they happen.</p>
          <ul className="mt-8 space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-slate-300">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/5 ring-1 ring-white/10">
                  <Icon className="h-4 w-4 text-amber-400" />
                </span>
                <span className="pt-1.5">{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-12 text-xs text-slate-500">For authorized site personnel only.</p>
      </div>

      {/* form */}
      <div className="flex flex-1 flex-col px-6 py-8 sm:px-12">
        <Link to="/" className="inline-flex items-center gap-1.5 self-start text-sm text-slate-500 hover:text-slate-900">
          <ArrowLeft className="h-4 w-4" /> Back to site
        </Link>
        <div className="m-auto w-full max-w-sm py-12">
          <div className="lg:hidden">
            <LogoMark className="h-10 w-10" />
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight text-slate-900 lg:mt-0">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Use the account your site administrator gave you.</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Email</span>
              <input
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
                placeholder="you@company.com"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Password</span>
              <span className="relative mt-1.5 block">
                <input
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2.5 pr-10 text-sm text-slate-900 shadow-sm focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
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
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-50"
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
