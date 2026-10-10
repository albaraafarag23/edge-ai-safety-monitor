import { Link } from "react-router-dom";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  { title: "Page not found", back: "Back to overview" },
  { title: "الصفحة غير موجودة", back: "العودة إلى النظرة العامة" },
);

export function NotFound() {
  const t = useText(TEXT);
  return (
    <div className="py-24 text-center">
      <p className="text-sm font-semibold text-amber-600">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900">{t.title}</h1>
      <Link to="/app" className="mt-6 inline-block text-sm font-medium text-sky-700 hover:underline">
        {t.back}
      </Link>
    </div>
  );
}
