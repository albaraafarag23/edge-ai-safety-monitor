import { CameraOff, Maximize2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { API_BASE, cameraFrameUrl } from "../api/client";
import type { Camera } from "../api/types";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    live: "LIVE",
    offline: "OFFLINE",
    testMode: "TEST MODE",
    fullScreen: "Full screen",
    cameraOffline: "Camera offline",
    waiting: "Waiting for the detector to send frames…",
  },
  {
    live: "مباشر",
    offline: "غير متصل",
    testMode: "وضع الاختبار",
    fullScreen: "ملء الشاشة",
    cameraOffline: "الكاميرا غير متصلة",
    waiting: "في انتظار أن يرسل النظام الصور…",
  },
);

const LIVE_MIN_GAP_MS = 100;   // picture-by-picture fallback: at most 10 a second
const LIVE_FAILURES = 3;       // failures in a row before the view shows offline

/** Shows a JPEG once it is decoded, so the view never flickers to a half-drawn picture. */
async function decoded(blob: Blob): Promise<string> {
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.src = url;
  try {
    await img.decode();
  } catch (e) {
    URL.revokeObjectURL(url);
    throw e;
  }
  return url;
}

/**
 * The newest pictures of a camera, never seconds behind. Normally over a WebSocket (backend cameras.py `live`):
 * the server pushes each new picture, up to ~20 a second, and this page answers each one it has put on screen;
 * the server stops at two unanswered, so nothing piles up in the network's buffers and a slow link just gets
 * fewer pictures. If WebSockets don't get through (an old browser, a strict proxy), it falls back to fetching
 * the newest picture again as soon as the last one is shown (at most 10 a second, one round trip old).
 */
function useLiveFrame(cameraId: string, active: boolean, onFail: () => void) {
  const [src, setSrc] = useState<string | null>(null);
  const failRef = useRef(onFail);
  failRef.current = onFail;

  useEffect(() => {
    if (!active) {
      setSrc(null);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    let shown: string | null = null;
    let failures = 0;
    let socket: WebSocket | null = null;
    const controller = new AbortController();

    const show = (url: string) => {
      if (stopped) {
        URL.revokeObjectURL(url);
        return;
      }
      if (shown) URL.revokeObjectURL(shown);
      shown = url;
      setSrc(url);
      failures = 0;
    };
    const failed = () => {
      failures += 1;
      if (failures >= LIVE_FAILURES) failRef.current();
      return failures < LIVE_FAILURES;
    };

    // fallback: picture by picture
    const pull = async () => {
      if (stopped) return;
      if (document.hidden) {
        timer = window.setTimeout(pull, 500);
        return;
      }
      const started = performance.now();
      try {
        const res = await fetch(`${cameraFrameUrl(cameraId)}?t=${Date.now()}`, { cache: "no-store", signal: controller.signal });
        if (!res.ok) throw new Error(String(res.status));
        show(await decoded(await res.blob()));
      } catch {
        if (stopped || !failed()) return;
      }
      timer = window.setTimeout(pull, Math.max(0, LIVE_MIN_GAP_MS - (performance.now() - started)));
    };

    const connect = () => {
      if (stopped) return;
      let got = false;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}${API_BASE}/cameras/${encodeURIComponent(cameraId)}/live`);
      socket.binaryType = "arraybuffer";
      socket.onmessage = async (e) => {
        got = true;
        const ws = e.target as WebSocket;
        try {
          show(await decoded(new Blob([(e.data as ArrayBuffer).slice(8)], { type: "image/jpeg" })));
        } catch {
          /* a bad picture: skip it */
        }
        if (ws.readyState === WebSocket.OPEN) ws.send("1");   // on screen: send the next one
      };
      socket.onclose = () => {
        if (stopped) return;
        if (!got) pull();                                       // never worked here: picture by picture
        else if (failed()) timer = window.setTimeout(connect, 1000);   // dropped (e.g. a restart): again
      };
    };
    connect();

    return () => {
      stopped = true;
      controller.abort();
      window.clearTimeout(timer);
      socket?.close();
      if (shown) URL.revokeObjectURL(shown);
    };
  }, [cameraId, active]);

  return src;
}

/**
 * Live view of one camera, with a status overlay. Pictures come from useLiveFrame (always the newest one);
 * after a failure it tries again when the camera reports online again.
 */
export function CameraFeed({ camera, className = "", showFullscreen = true, showFps = true, overlay }: {
  camera: Camera;
  overlay?: ReactNode;   // drawn over the live picture, e.g. the zones
  className?: string;
  showFullscreen?: boolean;
  showFps?: boolean;
}) {
  const t = useText(TEXT);
  const box = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  // try again when the camera reports online again, and a few seconds after a failure (e.g. a server restart)
  useEffect(() => {
    if (camera.online) setFailed(false);
  }, [camera.online]);
  useEffect(() => {
    if (!failed) return;
    const timer = window.setTimeout(() => setFailed(false), 3000);
    return () => window.clearTimeout(timer);
  }, [failed]);

  const live = camera.online && !failed;
  const src = useLiveFrame(camera.camera_id, live, () => setFailed(true));
  const ratio = camera.width && camera.height ? `${camera.width} / ${camera.height}` : "16 / 9";

  return (
    <div
      ref={box}
      className={`group relative overflow-hidden rounded-xl bg-slate-950 ring-1 ring-slate-900/10 ${className}`}
      style={{ aspectRatio: ratio }}
    >
      {live && src ? (
        <img src={src} alt={`Live view of ${camera.camera_id}`} className="h-full w-full object-contain" />
      ) : live ? (
        <div className="flex h-full w-full items-center justify-center text-xs text-slate-500">{t.waiting}</div>
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-slate-500">
          <CameraOff className="h-8 w-8" aria-hidden />
          <p className="text-sm font-medium text-slate-400">{t.cameraOffline}</p>
          <p className="text-xs">{t.waiting}</p>
        </div>
      )}

      {live && overlay}

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between bg-gradient-to-b from-black/60 to-transparent p-3 text-white">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${
              live ? "bg-red-600" : "bg-slate-600"
            }`}
          >
            {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />}
            {live ? t.live : t.offline}
          </span>
          <span className="text-xs font-medium drop-shadow">{camera.camera_id}</span>
          {camera.location && <span className="hidden text-xs text-white/70 sm:inline">· {camera.location}</span>}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-white/80">
          {camera.mode === "test" && <span className="rounded bg-amber-400/90 px-1.5 py-0.5 font-semibold text-slate-950">{t.testMode}</span>}
          {live && showFps && camera.fps !== null && <span className="tabular-nums">{camera.fps.toFixed(1)} fps</span>}
        </div>
      </div>

      {showFullscreen && live && (
        <button
          onClick={() => box.current?.requestFullscreen?.()}
          className="absolute end-3 bottom-3 rounded-md bg-black/50 p-1.5 text-white opacity-0 transition group-hover:opacity-100 focus:opacity-100"
          aria-label={t.fullScreen}
          title={t.fullScreen}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

const STILL_EVERY_MS = 1000;

/**
 * A camera as a picture that refreshes every second, for showing many cameras at once. A live stream each would
 * hold a connection open per camera, and browsers allow only a few per site; stills don't. The next picture is
 * loaded before it replaces the current one, so the tile never flickers, and nothing is fetched while the tab
 * is in the background.
 */
export function CameraStill({ camera, className = "" }: { camera: Camera; className?: string }) {
  const t = useText(TEXT);
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!camera.online) {
      setSrc(null);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    const load = () => {
      if (document.hidden) {
        timer = window.setTimeout(load, STILL_EVERY_MS);
        return;
      }
      const next = new Image();
      const url = `${cameraFrameUrl(camera.camera_id)}?t=${Date.now()}`;
      const done = (ok: boolean) => {
        if (stopped) return;
        if (ok) setSrc(url);
        timer = window.setTimeout(load, STILL_EVERY_MS);
      };
      next.onload = () => done(true);
      next.onerror = () => done(false);
      next.src = url;
    };
    load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [camera.camera_id, camera.online]);

  const ratio = camera.width && camera.height ? `${camera.width} / ${camera.height}` : "16 / 9";
  return (
    <div className={`relative overflow-hidden rounded-xl bg-slate-950 ring-1 ring-slate-900/10 ${className}`} style={{ aspectRatio: ratio }}>
      {src ? (
        <img src={src} alt={`Live view of ${camera.camera_id}`} className="h-full w-full object-contain" />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-slate-500">
          <CameraOff className="h-7 w-7" aria-hidden />
          <p className="text-sm font-medium text-slate-400">{camera.online ? t.waiting : t.cameraOffline}</p>
        </div>
      )}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center gap-2 bg-gradient-to-b from-black/60 to-transparent p-3 text-white">
        <span className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${camera.online ? "bg-red-600" : "bg-slate-600"}`}>
          {camera.online && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />}
          {camera.online ? t.live : t.offline}
        </span>
        <span className="truncate text-xs font-medium drop-shadow">{camera.location ?? camera.camera_id}</span>
        {camera.mode === "test" && <span className="ms-auto rounded bg-amber-400/90 px-1.5 py-0.5 text-[10px] font-semibold text-slate-950">{t.testMode}</span>}
      </div>
    </div>
  );
}
