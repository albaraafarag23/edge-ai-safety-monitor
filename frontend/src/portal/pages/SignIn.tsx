/** Sign in with a passkey; ask to add a new device; set up the first device from an invite link. */
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Fingerprint } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { bilingual, LanguageSwitch, useText } from "../../lib/i18n";
import { acceptInvite, ApiError, cancelledByBrowser, get, requestDevice, signInWithPasskey, type Invite } from "../api";
import { BTN, FIELD, Logo, WORDS } from "../shell";

const TEXT = bilingual(
  {
    portal: "Portal",
    headline: "Every client, every box, one place.",
    sub: "Clients sign in here too, and go straight to their own site's console.",
    signIn: "Sign in",
    withPasskey: "Sign in with passkey",
    howItWorks: "Your fingerprint, face or screen lock confirms it's you. There's no password to steal.",
    newDevice: "New phone or laptop?",
    newDeviceLink: "Ask to add this device",
    newDeviceTitle: "Add this device",
    newDeviceLead: "Type your email. Your phone or laptop makes a passkey; it works once your manager (or for managers, SiteSentry) approves it.",
    email: "Your email",
    ask: "Make a passkey and ask",
    asked: "Asked. You'll be able to sign in from this device once it's approved. You can close this page.",
    backToSignIn: "Back to sign in",
    errors: {
      cancelled: "The passkey prompt was closed. Try again when you're ready.",
      device_pending: "This device is still waiting for approval.",
      device_refused: "This device was refused. Ask your manager.",
      device_revoked: "This device was removed. Ask to add it again.",
      account_off: "Your account or company is switched off. Ask your manager.",
      unknown: "That didn't work. Try again.",
    } as Record<string, string>,
    inviteTitle: (name: string) => `Welcome, ${name}`,
    inviteLead: (company: string | null, role: string) =>
      company ? `You're joining ${company} as ${role.toLowerCase()}.` : `You're setting up the ${role.toLowerCase()} account.`,
    inviteSteps: "Set up this phone or laptop: it makes a passkey that only this device holds. Next time, you sign in with your fingerprint, face or screen lock.",
    setUp: "Set up this device",
    inviteGone: "This link was already used or has expired. Ask whoever invited you for a new one.",
    inviteUnknown: "This link isn't valid. Check you copied all of it.",
    loading: "Checking the link…",
  },
  {
    portal: "البوابة",
    headline: "كل العملاء، كل الأجهزة، في مكان واحد.",
    sub: "يدخل العملاء من هنا أيضًا، ويصلون مباشرة إلى لوحة تحكم موقعهم.",
    signIn: "تسجيل الدخول",
    withPasskey: "الدخول بمفتاح المرور",
    howItWorks: "تؤكد بصمتك أو وجهك أو قفل الشاشة أنك أنت. لا توجد كلمة مرور يمكن سرقتها.",
    newDevice: "هاتف أو حاسوب جديد؟",
    newDeviceLink: "اطلب إضافة هذا الجهاز",
    newDeviceTitle: "إضافة هذا الجهاز",
    newDeviceLead: "اكتب بريدك. ينشئ هاتفك أو حاسوبك مفتاح مرور، ويعمل بعد أن يوافق مديرك (أو SiteSentry إن كنت مديرًا).",
    email: "بريدك الإلكتروني",
    ask: "أنشئ مفتاحًا واطلب الموافقة",
    asked: "تم الطلب. ستتمكن من الدخول من هذا الجهاز بعد الموافقة عليه. يمكنك إغلاق الصفحة.",
    backToSignIn: "العودة إلى تسجيل الدخول",
    errors: {
      cancelled: "أُغلقت نافذة مفتاح المرور. حاول مرة أخرى عندما تكون مستعدًا.",
      device_pending: "هذا الجهاز ما زال بانتظار الموافقة.",
      device_refused: "رُفض هذا الجهاز. تواصل مع مديرك.",
      device_revoked: "أُزيل هذا الجهاز. اطلب إضافته من جديد.",
      account_off: "حسابك أو شركتك متوقف. تواصل مع مديرك.",
      unknown: "لم ينجح ذلك. حاول مرة أخرى.",
    },
    inviteTitle: (name: string) => `أهلًا ${name}`,
    inviteLead: (company: string | null, role: string) =>
      company ? `تنضم إلى ${company} بصفة ${role}.` : `تُعدّ حساب ${role}.`,
    inviteSteps: "جهّز هذا الهاتف أو الحاسوب: ينشئ مفتاح مرور لا يحمله إلا هذا الجهاز. في المرة القادمة تدخل ببصمتك أو وجهك أو قفل الشاشة.",
    setUp: "جهّز هذا الجهاز",
    inviteGone: "استُخدم هذا الرابط من قبل أو انتهت صلاحيته. اطلب رابطًا جديدًا ممن دعاك.",
    inviteUnknown: "هذا الرابط غير صالح. تأكد أنك نسخته كاملًا.",
    loading: "جارٍ التحقق من الرابط…",
  },
);

function useErrorText() {
  const t = useText(TEXT);
  return (err: unknown) => {
    if (cancelledByBrowser(err)) return t.errors.cancelled;
    if (err instanceof ApiError && t.errors[err.code]) return t.errors[err.code];
    if (err instanceof ApiError && err.status === 429) return err.code;
    return t.errors.unknown;
  };
}

function Frame({ children }: { children: ReactNode }) {
  const t = useText(TEXT);
  return (
    <div className="flex min-h-screen flex-col bg-ink text-paper md:flex-row">
      <section className="flex flex-1 flex-col justify-between gap-10 px-6 py-8 sm:px-12 sm:py-12">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Logo />
            <span className="font-display font-bold">SiteSentry</span>
          </div>
          <LanguageSwitch className="border border-[#3a352c] text-paper hover:bg-[#2a261f]" />
        </div>
        <div className="flex max-w-xl flex-col gap-3.5">
          <div className="font-serif text-2xl italic text-[#f2b705]">{t.portal}</div>
          <h1 className="font-display text-4xl font-extrabold leading-none tracking-tight sm:text-6xl">{t.headline}</h1>
          <p className="text-base leading-relaxed text-[#cfc8ba]">{t.sub}</p>
        </div>
        <div />
      </section>
      <section className="flex flex-1 items-center justify-center bg-paper px-6 py-10 text-ink sm:px-12">
        <div className="flex w-full max-w-sm flex-col gap-5">{children}</div>
      </section>
    </div>
  );
}

function Problem({ text }: { text: string | null }) {
  return text ? <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{text}</p> : null;
}

export function SignIn() {
  const t = useText(TEXT);
  const errorText = useErrorText();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await signInWithPasskey();
      await qc.invalidateQueries();
      navigate(from && from.startsWith("/") && !from.startsWith("//") ? from : "/", { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Frame>
      <h2 className="font-display text-3xl font-bold">{t.signIn}</h2>
      <button type="button" onClick={go} disabled={busy} className={`${BTN} min-h-12 w-full text-[15px]`}>
        <Fingerprint className="h-5 w-5" aria-hidden="true" /> {t.withPasskey}
      </button>
      <Problem text={error} />
      <p className="text-[13px] leading-relaxed text-[#4a4439]">{t.howItWorks}</p>
      <div className="border-t border-[#d9d2c4] pt-4 text-[13px] text-[#4a4439]">
        <strong className="font-semibold text-ink">{t.newDevice}</strong>{" "}
        <Link to="/new-device" className="font-semibold text-[#8a5a00] underline">{t.newDeviceLink}</Link>
      </div>
    </Frame>
  );
}

export function NewDevice() {
  const t = useText(TEXT);
  const errorText = useErrorText();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<{ busy?: boolean; error?: string; done?: boolean }>({});

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setState({ busy: true });
    try {
      await requestDevice(email.trim());
      setState({ done: true });
    } catch (err) {
      setState({ error: errorText(err) });
    }
  };

  return (
    <Frame>
      <h2 className="font-display text-3xl font-bold">{t.newDeviceTitle}</h2>
      {state.done ? (
        <p role="status" className="flex gap-2 rounded-xl bg-[#e8f5ec] px-3.5 py-3 text-sm text-[#166534]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> {t.asked}
        </p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-sm leading-relaxed text-[#4a4439]">{t.newDeviceLead}</p>
          <label className="text-sm font-medium">
            {t.email}
            <input type="email" required dir="ltr" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)} className={FIELD} />
          </label>
          <button type="submit" disabled={state.busy || !email} className={`${BTN} w-full`}>
            <Fingerprint className="h-5 w-5" aria-hidden="true" /> {t.ask}
          </button>
          <Problem text={state.error ?? null} />
        </form>
      )}
      <Link to="/signin" className="text-sm font-semibold text-[#8a5a00] underline">{t.backToSignIn}</Link>
    </Frame>
  );
}

export function AcceptInvite() {
  const { secret = "" } = useParams();
  const t = useText(TEXT);
  const words = useText(WORDS);
  const errorText = useErrorText();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [invite, setInvite] = useState<Invite | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Invite>(`/invites/${encodeURIComponent(secret)}`)
      .then(setInvite)
      .catch((err) => setGone(err instanceof ApiError && err.status === 410 ? t.inviteGone : t.inviteUnknown));
  }, [secret]); // eslint-disable-line react-hooks/exhaustive-deps

  const setUp = async () => {
    setBusy(true);
    setError(null);
    try {
      await acceptInvite(secret);
      await qc.invalidateQueries();
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) setGone(t.inviteGone);
      else setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Frame>
      {gone ? (
        <>
          <Problem text={gone} />
          <Link to="/signin" className="text-sm font-semibold text-[#8a5a00] underline">{t.backToSignIn}</Link>
        </>
      ) : !invite ? (
        <p aria-busy="true" className="text-sm text-[#4a4439]">{t.loading}</p>
      ) : (
        <>
          <h2 className="font-display text-3xl font-bold" dir="auto">{t.inviteTitle(invite.name)}</h2>
          <p className="font-serif text-xl leading-snug" dir="auto">{t.inviteLead(invite.company, words.role[invite.role])}</p>
          <p className="text-sm leading-relaxed text-[#4a4439]">{t.inviteSteps}</p>
          <button type="button" onClick={setUp} disabled={busy} className={`${BTN} min-h-12 w-full text-[15px]`}>
            <Fingerprint className="h-5 w-5" aria-hidden="true" /> {t.setUp}
          </button>
          <Problem text={error} />
          <p className="text-xs text-[#6b6355]" dir="ltr">{invite.email}</p>
        </>
      )}
    </Frame>
  );
}
