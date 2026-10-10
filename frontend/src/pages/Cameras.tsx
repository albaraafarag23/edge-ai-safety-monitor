import { Download, Video } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { cameraFrameUrl, mediaUrl } from "../api/client";
import { useCameras, useIncidents } from "../api/queries";
import type { Camera } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, SeverityBadge, Spinner } from "../components/ui";
import { humanize, timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { eventTypeLabel, usePluginText } from "../lib/terms";

const TEXT = bilingual(
  {
    noIncidents: "No incidents on this camera yet",
    noLocation: "No location set",
    online: "Online",
    offline: "Offline",
    title: "Live cameras",
    countOnline: (online: number, total: number) => `${online} of ${total} camera${total === 1 ? "" : "s"} online`,
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
  },
  {
    noIncidents: "لا توجد حوادث على هذه الكاميرا بعد",
    noLocation: "لم يُحدد الموقع",
    online: "متصلة",
    offline: "غير متصلة",
    title: "الكاميرات المباشرة",
    countOnline: (online: number, total: number) => `الكاميرات المتصلة: ${online} من ${total}`,
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
                <span className="block truncate text-sm font-medium text-slate-900">{eventTypeLabel(i.event_type)}</span>
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
          <div className="space-y-4">
            <CameraFeed camera={selected} className="w-full shadow-lg shadow-slate-900/10" />
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
              <p>
                {t.boxesBefore}
                <span className="font-medium text-emerald-700">{t.green}</span>
                {t.worn}
                <span className="font-medium text-red-700">{t.red}</span>
                {t.missing}
              </p>
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
          </div>

          <div className="space-y-6">
            {list.length > 1 && (
              <div className="space-y-2">
                {list.map((c) => (
                  <CameraTile key={c.camera_id} camera={c} selected={c.camera_id === selected.camera_id}
                    onSelect={() => setParams({ camera: c.camera_id })} />
                ))}
              </div>
            )}
            <Card title={t.camera}>
              <dl className="-my-2 divide-y divide-slate-100">
                <Detail label={t.rows.status}>
                  <span className={selected.online ? "text-emerald-700" : "text-slate-500"}>
                    {selected.online ? t.online : t.offline}
                  </span>
                </Detail>
                <Detail label={t.rows.location}>{selected.location}</Detail>
                <Detail label={t.rows.speed}>{selected.fps !== null ? `${selected.fps.toFixed(1)} fps` : null}</Detail>
                <Detail label={t.rows.resolution}>{selected.width ? `${selected.width} × ${selected.height}` : null}</Detail>
                <Detail label={t.rows.model}>{selected.model}</Detail>
                <Detail label={t.rows.plugin}>{selected.plugin_id ? plugin.pluginName(humanize(selected.plugin_id.toUpperCase())) : null}</Detail>
                <Detail label={t.rows.mode}>{selected.mode === "test" ? t.modeTest : selected.mode === "live" ? t.modeLive : null}</Detail>
              </dl>
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
