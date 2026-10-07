import { Download, Video } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { cameraFrameUrl, mediaUrl } from "../api/client";
import { useCameras, useIncidents } from "../api/queries";
import type { Camera } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, SeverityBadge, Spinner } from "../components/ui";
import { humanize, timeAgo } from "../lib/format";

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children ?? "—"}</dd>
    </div>
  );
}

function CameraIncidents({ cameraId }: { cameraId: string }) {
  const incidents = useIncidents({ camera_id: cameraId, limit: 6 });
  if (incidents.isPending) return <Spinner />;
  if (incidents.isError) return <ErrorState error={incidents.error} />;
  if (!incidents.data.items.length) return <EmptyState title="No incidents on this camera yet" />;
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
                <span className="block truncate text-sm font-medium text-slate-900">{humanize(i.event_type)}</span>
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
  return (
    <button
      onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${
        selected ? "border-slate-900 bg-white shadow-sm ring-1 ring-slate-900" : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
        <Video className="h-4 w-4 text-slate-600" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-slate-900">{camera.camera_id}</span>
        <span className="block truncate text-xs text-slate-500">{camera.location ?? "No location set"}</span>
      </span>
      <span className={`h-2.5 w-2.5 rounded-full ${camera.online ? "bg-emerald-500" : "bg-slate-300"}`} title={camera.online ? "Online" : "Offline"} />
    </button>
  );
}

export function Cameras() {
  const cameras = useCameras();
  const [params, setParams] = useSearchParams();

  if (cameras.isPending) return <Spinner />;
  if (cameras.isError) return <ErrorState error={cameras.error} onRetry={() => cameras.refetch()} />;

  const list = cameras.data;
  const online = list.filter((c) => c.online).length;
  const selected = list.find((c) => c.camera_id === params.get("camera")) ?? list[0];

  return (
    <>
      <PageHeader
        title="Live cameras"
        subtitle={list.length ? `${online} of ${list.length} camera${list.length === 1 ? "" : "s"} online` : undefined}
      />
      {!selected ? (
        <Card>
          <EmptyState title="No cameras have connected yet">
            Start the detector (<code className="text-xs">cv_pipeline</code>). Its camera appears here within a few seconds.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
          <div className="space-y-4">
            <CameraFeed camera={selected} className="w-full shadow-lg shadow-slate-900/10" />
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
              <p>
                Boxes are drawn by the detector: <span className="font-medium text-emerald-700">green</span> PPE worn,{" "}
                <span className="font-medium text-red-700">red</span> PPE missing.
              </p>
              {selected.online && (
                <a
                  href={cameraFrameUrl(selected.camera_id)}
                  download={`${selected.camera_id}-${new Date().toISOString().slice(0, 19)}.jpg`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                >
                  <Download className="h-4 w-4" /> Save frame
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
            <Card title="Camera">
              <dl className="-my-2 divide-y divide-slate-100">
                <Detail label="Status">
                  <span className={selected.online ? "text-emerald-700" : "text-slate-500"}>
                    {selected.online ? "Online" : "Offline"}
                  </span>
                </Detail>
                <Detail label="Location">{selected.location}</Detail>
                <Detail label="Detector speed">{selected.fps !== null ? `${selected.fps.toFixed(1)} fps` : null}</Detail>
                <Detail label="Stream resolution">{selected.width ? `${selected.width} × ${selected.height}` : null}</Detail>
                <Detail label="Model">{selected.model}</Detail>
                <Detail label="Plugin">{selected.plugin_id ? humanize(selected.plugin_id.toUpperCase()) : null}</Detail>
                <Detail label="Mode">{selected.mode === "test" ? "Test (synthetic frames)" : selected.mode === "live" ? "Live camera" : null}</Detail>
              </dl>
            </Card>
            <Card
              title="Recent incidents"
              action={
                <Link to={`/app/incidents?camera_id=${encodeURIComponent(selected.camera_id)}`} className="text-sm font-medium text-sky-700 hover:underline">
                  View all
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
