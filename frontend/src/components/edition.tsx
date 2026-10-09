/**
 * Building blocks for the product page's "edition" layout: numbered chapters that open with a full-screen
 * photo (pinned while the chapter's content slides over it), a chapter index that follows the scroll,
 * and editorial type (a grotesk display face with a serif italic initial).
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

export const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

export interface ChapterInfo {
  id: string;
  title: string;
}

/** A photo in public/edition/<name>-{1200,2400}.webp; phones load the small one. */
export function Photo({ name, className = "", alt = "", eager = false }: {
  name: string;
  className?: string;
  alt?: string;
  eager?: boolean;
}) {
  return (
    <img
      src={`/edition/${name}-1200.webp`}
      srcSet={`/edition/${name}-1200.webp 1200w, /edition/${name}-2400.webp 2400w`}
      sizes="100vw"
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      className={className}
    />
  );
}

/** A heading whose first letter is a large serif italic initial, the way magazines open a story. */
export function Flourish({ text, className = "" }: { text: string; className?: string }) {
  return (
    <h3 className={`font-serif text-[2.6rem] leading-[1.05] tracking-tight text-balance sm:text-6xl ${className}`}>
      <span className="mr-[0.02em] inline-block align-[-0.08em] text-[1.45em] leading-none text-amber-600 italic">{text[0]}</span>
      {text.slice(1)}
    </h3>
  );
}

/** Small "Read more ↗" style link, like a footnote under a card. */
export function PillLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="mt-3 inline-flex items-center gap-1 rounded-sm bg-white/80 px-1.5 py-0.5 text-xs font-semibold text-ink ring-1 ring-ink/10 transition hover:bg-white"
    >
      {children} <span aria-hidden>↗</span>
    </a>
  );
}

/** Muted looping screen recording. Plays only while on screen, and not at all with reduced motion. */
export function AutoVideo({ name, label, className = "" }: { name: string; label: string; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [reduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const video = ref.current;
    if (!video || reduced) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) video.play().catch(() => {});
      else video.pause();
    });
    observer.observe(video);
    return () => observer.disconnect();
  }, [reduced]);
  return (
    <video
      ref={ref}
      src={`/edition/clip-${name}.mp4`}
      poster={`/edition/clip-${name}.webp`}
      muted
      loop
      playsInline
      preload="metadata"
      controls={reduced}
      aria-label={label}
      className={`block w-full ${className}`}
    />
  );
}

/**
 * A numbered chapter: a full-screen photo with a huge title stays pinned while the chapter's
 * content (on paper) slides up over it.
 */
export function Chapter({ id, n, title, kicker, photo, children }: {
  id: string;
  n: number;
  title: string;
  kicker: string;
  photo: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="chapter relative scroll-mt-0">
      <div className="sticky top-0 -mb-[100svh] h-[100svh] overflow-hidden bg-ink" data-surface="dark">
        <Photo name={photo} className="opener-photo absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/15 to-black/70" aria-hidden />
        <div className="opener-title relative flex h-full flex-col justify-between px-5 pt-24 pb-14 sm:px-8 lg:pl-[17rem]">
          <h2
            id={`${id}-title`}
            className="font-display text-[clamp(3.5rem,13vw,13rem)] leading-[0.86] font-semibold tracking-[-0.045em] text-balance text-paper"
          >
            {title}
          </h2>
          <p className="flex max-w-2xl items-baseline gap-4 font-serif text-2xl leading-snug text-paper sm:text-4xl">
            <span className="font-display text-sm font-semibold tracking-widest text-amber-300">{ROMAN[n - 1]}</span>
            <span className="text-balance">{kicker}</span>
          </p>
        </div>
      </div>
      {/* empty space so the opener can be seen whole before the content covers it */}
      <div className="chapter-spacer h-[100svh]" aria-hidden />
      <div className="paper-grain relative z-10 rounded-t-[2rem] bg-paper text-ink shadow-[0_-30px_60px_-20px_rgb(0_0_0/0.45)]" data-surface="light">
        <div className="px-5 py-20 sm:px-8 sm:py-28 lg:pr-12 lg:pl-[17rem]">{children}</div>
      </div>
    </section>
  );
}

/** Two-column list of smaller items at the end of a chapter: bold name, muted description. */
export function DenseList({ items }: { items: [string, string][] }) {
  return (
    <dl className="reveal mt-20 grid gap-x-12 gap-y-7 border-t border-ink/15 pt-10 md:grid-cols-2">
      {items.map(([name, text]) => (
        <div key={name} className="grid gap-1 sm:grid-cols-[11rem_1fr] sm:gap-6">
          <dt className="text-sm font-semibold text-ink">{name}</dt>
          <dd className="text-sm leading-6 text-ink/55">{text}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Which chapter is in view, and whether a dark or light surface is under a given point of the screen. */
export function useScrollState(chapters: ChapterInfo[], probe: () => { x: number; y: number }) {
  const [active, setActive] = useState<string | null>(null);
  const [surface, setSurface] = useState<"dark" | "light">("dark");
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const line = window.innerHeight * 0.45;
      let current: string | null = null;
      for (const c of chapters) {
        const el = document.getElementById(c.id);
        if (el && el.getBoundingClientRect().top <= line) current = c.id;
      }
      setActive(current);
      const { x, y } = probe();
      const under = document
        .elementsFromPoint(x, y)
        .map((e) => e.closest<HTMLElement>("[data-surface]"))
        .find((e) => e && !e.closest("[data-overlay]"));
      setSurface(under?.dataset.surface === "light" ? "light" : "dark");
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [chapters, probe]);
  return { active, surface };
}

/**
 * Fixed chapter list at the bottom left (wide screens): the current chapter is bold with a dotted leader.
 * It inverts against whatever is behind it (mix-blend-difference), so it stays readable while a chapter's
 * paper slides over a dark photo.
 */
export function ChapterIndex({ chapters, active }: { chapters: ChapterInfo[]; active: string | null }) {
  return (
    <nav
      data-overlay
      aria-label="Chapters"
      className={`fixed bottom-8 left-6 z-30 hidden w-52 text-paper mix-blend-difference transition-opacity duration-300 lg:block ${
        active ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
    >
      <ol className="space-y-0.5">
        {chapters.map((c, i) => {
          const isActive = c.id === active;
          return (
            <li key={c.id}>
              <a
                href={`#${c.id}`}
                aria-current={isActive ? "true" : undefined}
                className={`flex items-baseline gap-2 font-display text-[15px] leading-tight font-semibold tracking-tight transition-opacity hover:opacity-100 ${
                  isActive ? "opacity-100" : "opacity-50"
                }`}
              >
                <span className="whitespace-nowrap">{c.title}</span>
                <span className={`mb-1 h-px flex-1 border-b border-dotted ${isActive ? "border-current" : "border-transparent"}`} />
                <span className="font-serif text-xs font-normal">{ROMAN[i]}</span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
