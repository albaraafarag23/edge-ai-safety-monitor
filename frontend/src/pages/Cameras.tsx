import { Download, Shapes, Video } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { cameraFrameUrl, mediaUrl } from "../api/client";
import { useCameras, useIncidents } from "../api/queries";
import type { Camera } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { ZoneEditor, ZoneOverlay } from "../components/ZoneEditor";
import { useAuth } from "../lib/auth";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, SeverityBadge, Spinner } from "../components/ui";
import { humanize, timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { incidentTitle, usePluginText } from "../lib/terms";

const TEXT = bilingual(
  {
    noIncidents: "No incidents on this camera yet",
    noLocation: "No location set",
    online: "Online",
    offline: "Offline",
    title: "Live cameras",
    countOnline: (online: number, total: number): string =>
      total === 1 ? (online ? "The camera is live." : "The camera is offline.") : online === total ? "All cameras are live." : online ? "Some cameras are offline." : "All cameras are offline.",
    noneYet: "No cameras have connected yet",
    noneHintBefore: "Start the detector (",
    noneHintAfter: "). Its camera appears here within a few seconds.",
    boxesBefore: "Boxes are drawn by the detector: ",
    green: "green",
    worn: " PPE worn, ",
    red: "red",
    missing: " PPE missing.",
    saveFrame: "Save frame",
    camera: "Camera",
    rows: { status: "Status", location: "Location", speed: "Detector speed", resolution: "Stream resolution", model: "Model", plugin: "Plugin", mode: "Mode" },
    modeTest: "Test (synthetic frames)",
    modeLive: "Live camera",
    recent: "Recent incidents",
    viewAll: "View all",
    watching: (where: string | null) => (where ? `Watching ${where} right now.` : "Watching right now."),
    notWatching: "Not watching: the camera is switched off or not connected.",
    lastSeen: (when: string) => `Last seen ${when}.`,
    technical: "Technical details",
    editZones: "Edit zones",
    map: {
      title: "Where incidents happen",
      hint: "The last 7 days on this camera. The brighter the glow, the more often something happened there.",
      none: "No incidents with a position in the last 7 days.",
      mostly: (where: string) => `Most incidents happen ${where} of the picture.`,
      parts: { left: "on the left", centre: "in the middle", right: "on the right" } as Record<string, string>,
    },
  },
  {
    noIncidents: "لا توجد حوادث على هذه الكاميرا بعد",
    noLocation: "لم يُحدد الموقع",
    online: "متصلة",
    offline: "غير متصلة",
    title: "الكاميرات المباشرة",
    countOnline: (online: number, total: number) =>
      total === 1 ? (online ? "الكاميرا تعمل." : "الكاميرا غير متصلة.") : online === total ? "كل الكاميرات تعمل." : online ? "بعض الكاميرات غير متصلة." : "كل الكاميرات غير متصلة.",
    noneYet: "لم تتصل أي كاميرا بعد",
    noneHintBefore: "شغّل النظام (",
    noneHintAfter: "). تظهر الكاميرا هنا خلال ثوانٍ.",
    boxesBefore: "يرسم النظام المربعات: ",
    green: "الأخضر",
    worn: " معدات الوقاية موجودة، و",
    red: "الأحمر",
    missing: " معدات الوقاية ناقصة.",
    saveFrame: "حفظ الإطار",
    camera: "الكاميرا",
    rows: { status: "الحالة", location: "الموقع", speed: "سرعة الرصد", resolution: "دقة البث", model: "النموذج", plugin: "الإضافة", mode: "الوضع" },
    modeTest: "اختبار (إطارات اصطناعية)",
    modeLive: "كاميرا مباشرة",
    recent: "أحدث الحوادث",
    viewAll: "عرض الكل",
    watching: (where: string | null) => (where ? `تراقب ${where} الآن.` : "تراقب الآن."),
    notWatching: "لا تراقب: الكاميرا مطفأة أو غير متصلة.",
    lastSeen: (when: string) => `آخر ظهور ${when}.`,
    technical: "التفاصيل التقنية",
    editZones: "تعديل المناطق",
    map: {
      title: "أين تقع الحوادث",
      hint: "آخر 7 أيام على هذه الكاميرا. كلما اشتد التوهج، تكررت الحوادث في ذلك المكان أكثر.",
      none: "لا حوادث بموضع محدد خلال آخر 7 أيام.",
      mostly: (where: string) => `تقع أغلب الحوادث ${where} من الصورة.`,
      parts: { left: "في الجهة اليسرى", centre: "في الوسط", right: "في الجهة اليمنى" },
    },
  },
);

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-end font-medium text-slate-900">{children ?? "—"}</dd>
    </div>
  );
}

function CameraIncidents({ cameraId }: { cameraId: string }) {
  const incidents = useIncidents({ camera_id: cameraId, limit: 6 });
  const t = useText(TEXT);
  if (incidents.isPending) return <Spinner />;
  if (incidents.isError) return <ErrorState error={incidents.error} />;
  if (!incidents.data.items.length) return <EmptyState title={t.noIncidents} />;
  return (
    <ul className="-my-2 divide-y divide-slate-100">
      {incidents.data.items.map((i) => {
        const thumb = mediaUrl(i.snapshot_url);
        return (
          <li key={i.event_id}>
            <Link to={`/app/incidents/${i.event_id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-50">
              <span className="h-11 w-16 shrink-0 overflow-hidden rounded-md bg-slate-100">
                {thumb && <img src={thumb} alt="" loading="lazy" className="h-full w-full object-cover" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-900">{incidentTitle(i)}</span>
                <span className="block text-xs text-slate-500">{timeAgo(i.received_at)}</span>
              </span>
              <SeverityBadge severity={i.severity} />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

const GLOW: Record<string, string> = { CRITICAL: "239 68 68", HIGH: "249 115 22", MEDIUM: "245 158 11", LOW: "16 185 129" };

/** The camera picture with a soft glow where each incident's people (or objects) were, over the last 7 days. */
function DangerMap({ camera }: { camera: Camera }) {
  const t = useText(TEXT).map;
  const incidents = useIncidents({ camera_id: camera.camera_id, hours: 168, limit: 200 });
  const items = incidents.data?.items ?? [];
  const W = camera.width, H = camera.height;
  // the feet of each person/object involved: where on site it happened
  const points = W && H
    ? items.flatMap((i) =>
        (i.metadata.objects_involved ?? []).map((o) => ({
          x: (o.bbox[0] + o.bbox[2]) / 2 / W,
          y: o.bbox[3] / H,
          color: GLOW[i.severity] ?? GLOW.MEDIUM,
        })),
      ).filter((p) => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)
    : [];
  // repeats in the same spot add up in a grid cell; brightness grows with the log of the count, so one busy spot
  // doesn't blow out and a single incident still shows
  const grid = new Map<string, { key: string; x: number; y: number; n: number; color: string }>();
  for (const p of points) {
    const key = `${Math.floor(p.x * 16)}-${Math.floor(p.y * 12)}`;
    const cell = grid.get(key) ?? { key, x: 0, y: 0, n: 0, color: p.color };
    cell.x += p.x; cell.y += p.y; cell.n += 1;
    grid.set(key, cell);
  }
  const maxN = Math.max(1, ...[...grid.values()].map((c) => c.n));
  const cells = [...grid.values()].map((c) => ({ ...c, x: c.x / c.n, y: c.y / c.n, strength: Math.log1p(c.n) / Math.log1p(maxN) }));
  const background = mediaUrl(items.find((i) => i.snapshot_url)?.snapshot_url);
  const meanX = points.reduce((sum, p) => sum + p.x, 0) / (points.length || 1);
  const part = meanX < 0.38 ? "left" : meanX > 0.62 ? "right" : "centre";

  if (incidents.isPending) return <Spinner />;
  return (
    <Card title={t.title}>
      {points.length ? (
        <>
          <div className="relative overflow-hidden rounded-xl bg-ink" style={{ aspectRatio: `${W} / ${H}` }} dir="ltr">
            {background && <img src={background} alt="" className="absolute inset-0 h-full w-full object-cover opacity-60 grayscale" />}
            {cells.map((c) => (
              <span
                key={c.key}
                className="absolute h-[26%] w-[18%] -translate-x-1/2 -translate-y-1/2 rounded-full mix-blend-screen"
                style={{
                  left: `${c.x * 100}%`,
                  top: `${c.y * 100}%`,
                  background: `radial-gradient(closest-side, rgb(${c.color} / ${0.18 + 0.5 * c.strength}), transparent)`,
                }}
              />
            ))}
          </div>
          <p className="mt-3 text-[15px] font-semibold text-ink">{t.mostly(t.parts[part])}</p>
          <p className="mt-1 text-sm text-ink/65">{t.hint}</p>
        </>
      ) : (
        <EmptyState title={t.none} />
      )}
    </Card>
  );
}

function CameraTile({ camera, selected, onSelect }: { camera: Camera; selected: boolean; onSelect: () => void }) {
  const t = useText(TEXT);
  return (
    <button
      onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-xl border p-3 text-start transition ${
        selected ? "border-slate-900 bg-white shadow-sm ring-1 ring-slate-900" : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
        <Video className="h-4 w-4 text-slate-600" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-slate-900">{camera.camera_id}</span>
        <span className="block truncate text-xs text-slate-500">{camera.location ?? t.noLocation}</span>
      </span>
      <span className={`h-2.5 w-2.5 rounded-full ${camera.online ? "bg-emerald-500" : "bg-slate-300"}`} title={camera.online ? t.online : t.offline} />
    </button>
  );
}

export function Cameras() {
  const cameras = useCameras();
  const [params, setParams] = useSearchParams();
  const t = useText(TEXT);
  const plugin = usePluginText();
  const canEdit = useAuth().user?.role !== "viewer";
  const [editing, setEditing] = useState(false);

  if (cameras.isPending) return <Spinner />;
  if (cameras.isError) return <ErrorState error={cameras.error} onRetry={() => cameras.refetch()} />;

  const list = cameras.data;
  const online = list.filter((c) => c.online).length;
  const selected = list.find((c) => c.camera_id === params.get("camera")) ?? list[0];

  return (
    <>
      <PageHeader
        title={t.title}
        subtitle={list.length ? t.countOnline(online, list.length) : undefined}
      />
      {!selected ? (
        <Card>
          <EmptyState title={t.noneYet}>
            {t.noneHintBefore}
            <code className="text-xs">cv_pipeline</code>
            {t.noneHintAfter}
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
          <div className="min-w-0 space-y-4">
            <CameraFeed camera={selected} showFps={false} className="w-full shadow-lg shadow-slate-900/10"
              overlay={editing ? null : <ZoneOverlay camera={selected} />} />
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
              <p>
                {t.boxesBefore}
                <span className="font-medium text-emerald-700">{t.green}</span>
                {t.worn}
                <span className="font-medium text-red-700">{t.red}</span>
                {t.missing}
              </p>
              {canEdit && !editing && (
                <button
                  onClick={() => setEditing(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                >
                  <Shapes className="h-4 w-4" /> {t.editZones}
                </button>
              )}
              {selected.online && (
                <a
                  href={cameraFrameUrl(selected.camera_id)}
                  download={`${selected.camera_id}-${new Date().toISOString().slice(0, 19)}.jpg`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                >
                  <Download className="h-4 w-4" /> {t.saveFrame}
                </a>
              )}
            </div>
            {editing ? <ZoneEditor camera={selected} onClose={() => setEditing(false)} /> : <DangerMap camera={selected} />}
          </div>

          <div className="min-w-0 space-y-6">
            {list.length > 1 && (
              <div className="space-y-2">
                {list.map((c) => (
                  <CameraTile key={c.camera_id} camera={c} selected={c.camera_id === selected.camera_id}
                    onSelect={() => setParams({ camera: c.camera_id })} />
                ))}
              </div>
            )}
            <Card title={t.camera}>
              <p className="flex items-start gap-2 text-[15px] leading-snug text-ink">
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${selected.online ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span>
                  {selected.online ? t.watching(selected.location) : t.notWatching}
                  {!selected.online && selected.updated_at && <span className="block text-sm text-ink/65">{t.lastSeen(timeAgo(selected.updated_at))}</span>}
                </span>
              </p>
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-medium text-ink/65 hover:text-ink">{t.technical}</summary>
              <dl className="mt-2 divide-y divide-slate-100">
                <Detail label={t.rows.speed}>{selected.fps !== null ? `${selected.fps.toFixed(1)} fps` : null}</Detail>
                <Detail label={t.rows.resolution}>{selected.width ? `${selected.width} × ${selected.height}` : null}</Detail>
                <Detail label={t.rows.model}>{selected.model}</Detail>
                <Detail label={t.rows.plugin}>{selected.plugin_id ? plugin.pluginName(humanize(selected.plugin_id.toUpperCase())) : null}</Detail>
                <Detail label={t.rows.mode}>{selected.mode === "test" ? t.modeTest : selected.mode === "live" ? t.modeLive : null}</Detail>
              </dl>
              </details>
            </Card>
            <Card
              title={t.recent}
              action={
                <Link to={`/app/incidents?camera_id=${encodeURIComponent(selected.camera_id)}`} className="text-sm font-medium text-sky-700 hover:underline">
                  {t.viewAll}
                </Link>
              }
            >
              <CameraIncidents cameraId={selected.camera_id} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
