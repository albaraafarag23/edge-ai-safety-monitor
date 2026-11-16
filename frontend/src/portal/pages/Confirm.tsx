/** Confirm a risky change on a site's console with the passkey (the console sends people here: backend/confirm.py). */
import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { bilingual, useText } from "../../lib/i18n";
import { cancelledByBrowser, send } from "../api";
import { BTN, Header, Panel, problem } from "../shell";

const TEXT = bilingual(
  {
    title: "Confirm it's you",
    lead: "Your site's console asks before a change that affects safety: switching a rule off, timings, zones, accounts or face photos.",
    button: "Confirm with passkey",
    after: "You'll go straight back to the console. Then do the change again; it works for the next 5 minutes.",
    failed: "That didn't work. Try again.",
    cancelled: "The passkey prompt was closed. Try again when you're ready.",
    missing: "This link is incomplete. Go back to the console and try the change again.",
  },
  {
    title: "تأكيد هويتك",
    lead: "تسأل لوحة تحكم موقعك قبل أي تغيير يمس السلامة: إيقاف قاعدة، أو المدد، أو المناطق، أو الحسابات، أو صور الوجوه.",
    button: "التأكيد بمفتاح المرور",
    after: "ستعود مباشرة إلى لوحة التحكم. ثم أعد التغيير؛ يسري التأكيد لمدة 5 دقائق.",
    failed: "لم ينجح ذلك. حاول مرة أخرى.",
    cancelled: "أُغلقت نافذة مفتاح المرور. حاول مرة أخرى عندما تكون مستعدًا.",
    missing: "هذا الرابط ناقص. عد إلى لوحة التحكم وأعد التغيير.",
  },
);

export function Confirm() {
  const t = useText(TEXT);
  const [params] = useSearchParams();
  const box = params.get("box") ?? "";
  const back = params.get("back") ?? "/app";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await send<{ url: string }>(`/boxes/by-serial/${encodeURIComponent(box)}/confirm`, { back });
      window.location.assign(url);
    } catch (err) {
      setError(cancelledByBrowser(err) ? t.cancelled : problem(err, t.failed));
      setBusy(false);
    }
  };

  return (
    <>
      <Header title={t.title} lead={t.lead} />
      <Panel>
        {!box ? <p className="text-sm text-[#9a3412]">{t.missing}</p> : (
          <div className="flex max-w-md flex-col gap-4">
            <button type="button" onClick={go} disabled={busy} className={`${BTN} min-h-12 text-[15px]`}>
              <ShieldCheck className="h-5 w-5" aria-hidden="true" /> {t.button}
            </button>
            <p className="text-sm text-[#4a4439]">{t.after}</p>
            {error && <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{error}</p>}
          </div>
        )}
      </Panel>
    </>
  );
}
