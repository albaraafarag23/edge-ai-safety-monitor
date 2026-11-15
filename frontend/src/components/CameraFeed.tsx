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

type Picture = ImageBitmap | HTMLImageElement;

/** Decodes a JPEG off the main thread where the browser can (createImageBitmap), so drawing never waits on it. */
async function decodePicture(blob: Blob): Promise<Picture> {
  if (typeof createImageBitmap === "function") return createImageBitmap(blob);
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

const release = (p: Picture | null) => {
  if (p && "close" in p) p.close();
};

/**
 * The newest pictures of a camera, drawn on a canvas at the screen's own refresh. Normally over a WebSocket
 * (backend cameras.py `live`): the server pushes each new picture, up to ~20 a second, and this page answers
 * each one once it is painted (or skipped for a newer one); the server stops at a few unanswered, so nothing
 * piles up in the network's buffers and a slow link just gets fewer pictures. Pictures are decoded in the
 * background and painted straight onto the canvas: no React re-render per picture, no image swapping, so the
 * view doesn't stutter. In a background tab nothing is painted, so nothing is answered and the server pauses.
 * If WebSockets don't get through (an old browser, a strict proxy), it falls back to fetching the newest
 * picture again as soon as the last one is shown (at most 10 a second, one round trip old).
 */
function useLiveFrame(cameraId: string, active: boolean, onFail: () => void) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const failRef = useRef(onFail);
  failRef.current = onFail;

  useEffect(() => {
    if (!active) {
      setReady(false);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    let frame: number | undefined;
    let failures = 0;
    let socket: WebSocket | null = null;
    let waiting: { picture: Picture; done: () => void; n: number } | null = null;   // decoded, not yet painted
    let newest = 0;      // number of the newest picture painted or waiting: older ones that decode late are dropped
    let everGot = false; // the WebSocket has worked here: after a dropout, keep trying it rather than polling
    let owed = 0;        // pictures not answered while the tab was hidden (so the server pauses), answered on return
    let answerNow: (() => void) | null = null;
    let newestBase = 0;
    const onVisible = () => {
      if (document.hidden || !answerNow) return;
      for (; owed > 0; owed -= 1) answerNow();
    };
    document.addEventListener("visibilitychange", onVisible);
    const controller = new AbortController();

    const paint = () => {
      frame = undefined;
      const next = waiting;
      waiting = null;
      const canvas = canvasRef.current;
      if (!next) return;
      if (canvas && !stopped) {
        const w = next.picture.width, h = next.picture.height;
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
        }
        canvas.getContext("2d")?.drawImage(next.picture, 0, 0);
        failures = 0;
        setReady(true);   // re-renders only the first time
      }
      release(next.picture);
      next.done();
    };
    // the newest picture wins: one still waiting for the screen is skipped (and answered) for it, and one that
    // finished decoding after a newer one is dropped
    const show = (picture: Picture, done: () => void, n: number) => {
      if (stopped || n <= newest) {
        release(picture);
        if (!stopped) done();
        return;
      }
      newest = n;
      if (waiting) {
        release(waiting.picture);
        waiting.done();
      }
      waiting = { picture, done, n };
      if (frame === undefined) frame = requestAnimationFrame(paint);
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
        const picture = await decodePicture(await res.blob());
        await new Promise<void>((resolve) => show(picture, resolve, newest + 1));
      } catch {
        if (stopped || !failed()) return;
      }
      timer = window.setTimeout(pull, Math.max(0, LIVE_MIN_GAP_MS - (performance.now() - started)));
    };

    const connect = () => {
      if (stopped) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}${API_BASE}/cameras/${encodeURIComponent(cameraId)}/live`);
      socket = ws;
      ws.binaryType = "arraybuffer";
      let sent = 0;
      const send = () => {
        if (ws.readyState === WebSocket.OPEN) ws.send("1");
      };
      answerNow = send;
      // painted or skipped: send the next one. In a background tab, answer nothing, so the server stops after a
      // few pictures instead of streaming to a page nobody sees; the answers go out when the tab is shown again.
      const answer = () => {
        if (document.hidden) owed += 1;
        else send();
      };
      ws.onmessage = async (e) => {
        everGot = true;
        const n = ++sent + newestBase;
        try {
          show(await decodePicture(new Blob([(e.data as ArrayBuffer).slice(8)], { type: "image/jpeg" })), answer, n);
        } catch {
          answer();   // a bad picture: skip it
        }
      };
      ws.onclose = () => {
        if (stopped) return;
        newestBase = newest;   // the next connection's pictures count on from here
        owed = 0;              // those answers belonged to the closed connection
        if (!everGot) pull();                                    // never worked here: picture by picture
        else if (failed()) timer = window.setTimeout(connect, 1000);   // dropped (e.g. a restart): again
      };
    };
    connect();

    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisible);
      controller.abort();
      window.clearTimeout(timer);
      if (frame !== undefined) cancelAnimationFrame(frame);
      socket?.close();
      release(waiting?.picture ?? null);
      waiting = null;
    };
  }, [cameraId, active]);

  return { canvasRef, ready };
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
  const { canvasRef, ready } = useLiveFrame(camera.camera_id, live, () => setFailed(true));
  const ratio = camera.width && camera.height ? `${camera.width} / ${camera.height}` : "16 / 9";

  return (
    <div
      ref={box}
      className={`group relative overflow-hidden rounded-xl bg-slate-950 ring-1 ring-slate-900/10 ${className}`}
      style={{ aspectRatio: ratio }}
    >
      {live ? (
        <>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Live view of ${camera.camera_id}`}
            className={`h-full w-full object-contain ${ready ? "" : "invisible"}`}
          />
          {!ready && <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">{t.waiting}</div>}
        </>
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
