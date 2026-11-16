/**
 * "Confirm it's you" before a risky change, on a box linked to the SiteSentry portal (backend/confirm.py).
 * The API client calls the handler registered here when a change answers 428; the change is repeated by itself
 * after a password confirmation. Portal accounts confirm in the portal (passkey) and come back with ?confirmed=1.
 */
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { setConfirmHandler, type ConfirmKind } from "../api/client";
import { bilingual, useText } from "../lib/i18n";
import { BUTTON_PRIMARY, BUTTON_SECONDARY, INPUT, Modal } from "./ui";

const TEXT = bilingual(
  {
    title: "Confirm it's you",
    lead: "This change affects safety on site, so the console checks it's really you (once every 5 minutes).",
    password: "Your password",
    confirm: "Confirm and save",
    cancel: "Cancel",
    wrong: "That password isn't right.",
    failed: "Couldn't confirm. Try again.",
    portal: "Your account comes from the SiteSentry portal: confirm there with your passkey, then do the change again.",
    toPortal: "Confirm in the portal",
    back: "Confirmed. Do the change again: it goes through for the next 5 minutes.",
  },
  {
    title: "تأكيد هويتك",
    lead: "يمس هذا التغيير السلامة في الموقع، لذا تتحقق لوحة التحكم من أنك أنت (مرة كل 5 دقائق).",
    password: "كلمة مرورك",
    confirm: "تأكيد وحفظ",
    cancel: "إلغاء",
    wrong: "كلمة المرور غير صحيحة.",
    failed: "تعذّر التأكيد. حاول مرة أخرى.",
    portal: "حسابك من بوابة SiteSentry: أكّد هناك بمفتاح المرور، ثم أعد التغيير.",
    toPortal: "التأكيد في البوابة",
    back: "تم التأكيد. أعد التغيير: يمر خلال الدقائق الخمس القادمة.",
  },
);

export function ConfirmChange() {
  const t = useText(TEXT);
  const location = useLocation();
  const navigate = useNavigate();
  const [ask, setAsk] = useState<ConfirmKind | null>(null);
  const [password, setPassword] = useState("");
  const [state, setState] = useState<{ busy?: boolean; error?: string }>({});
  const [backNote, setBackNote] = useState(false);
  const settle = useRef<((ok: boolean) => void) | null>(null);

  useEffect(() => {
    setConfirmHandler((kind) => new Promise<boolean>((resolve) => {
      settle.current = resolve;
      setPassword("");
      setState({});
      setAsk(kind);
    }));
    return () => setConfirmHandler(null);
  }, []);

  // back from the portal: say so once, and drop ?confirmed=1 from the address
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("confirmed") === "1") {
      setBackNote(true);
      params.delete("confirmed");
      navigate({ pathname: location.pathname, search: params.toString() }, { replace: true });
    }
  }, [location.search]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = (ok: boolean) => {
    settle.current?.(ok);
    settle.current = null;
    setAsk(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setState({ busy: true });
    const res = await fetch("/api/auth/confirm", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
    }).catch(() => null);
    if (res?.ok) return close(true);
    setState({ error: res?.status === 401 ? t.wrong : t.failed });
  };

  const toPortal = async () => {
    setState({ busy: true });
    const back = location.pathname + location.search;
    const res = await fetch(`/api/auth/confirm-url?back=${encodeURIComponent(back)}`).catch(() => null);
    const body = res?.ok ? await res.json() : null;
    if (body?.url) window.location.assign(body.url);
    else setState({ error: t.failed });
  };

  return (
    <>
      {backNote && (
        <p role="status" className="mb-6 flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ring-1 ring-emerald-200">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" /> {t.back}
          <button type="button" onClick={() => setBackNote(false)} className="ms-auto text-emerald-700 hover:underline">×</button>
        </p>
      )}
      {ask && (
        <Modal title={t.title} onClose={() => close(false)}>
          <div className="space-y-4 text-sm text-slate-700">
            <p className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />{t.lead}</p>
            {ask === "password" ? (
              <form onSubmit={submit} className="space-y-3">
                <label className="block font-medium">{t.password}
                  <input type="password" autoComplete="current-password" autoFocus required value={password}
                    onChange={(e) => setPassword(e.target.value)} className={INPUT} />
                </label>
                {state.error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{state.error}</p>}
                <div className="flex justify-end gap-2">
                  <button type="button" className={BUTTON_SECONDARY} onClick={() => close(false)}>{t.cancel}</button>
                  <button type="submit" className={BUTTON_PRIMARY} disabled={state.busy || !password}>{t.confirm}</button>
                </div>
              </form>
            ) : (
              <div className="space-y-3">
                <p>{t.portal}</p>
                {state.error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{state.error}</p>}
                <div className="flex justify-end gap-2">
                  <button type="button" className={BUTTON_SECONDARY} onClick={() => close(false)}>{t.cancel}</button>
                  <button type="button" className={BUTTON_PRIMARY} disabled={state.busy} onClick={toPortal}>{t.toPortal}</button>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
