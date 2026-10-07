import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="py-24 text-center">
      <p className="text-sm font-semibold text-amber-600">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900">Page not found</h1>
      <Link to="/app" className="mt-6 inline-block text-sm font-medium text-sky-700 hover:underline">
        Back to overview
      </Link>
    </div>
  );
}
