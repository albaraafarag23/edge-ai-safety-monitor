import { Link } from "react-router-dom";
import { Flourish } from "../components/edition";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    title: "This page isn't here",
    text: "The link may be old or mistyped. Everything is still where it was.",
    start: "Product page",
    console: "Back to the console",
  },
  {
    title: "هذه الصفحة غير موجودة",
    text: "ربما الرابط قديم أو فيه خطأ. كل شيء آخر في مكانه.",
    start: "صفحة المنتج",
    console: "العودة إلى لوحة التحكم",
  },
);

export function NotFound() {
  const t = useText(TEXT);
  return (
    // shown inside the console (unknown public addresses go to the start instead, see App.tsx)
    <div className="flex flex-col items-center py-24 text-center text-ink">
      <Flourish text={t.title} as="h2" />
      <p className="mt-5 max-w-md text-lg text-ink/70">{t.text}</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link to="/app" className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper hover:bg-ink/85">
          {t.console}
        </Link>
        <Link to="/" className="rounded-full px-5 py-2.5 text-sm font-semibold ring-1 ring-ink/20 hover:bg-white">
          {t.start}
        </Link>
      </div>
    </div>
  );
}
