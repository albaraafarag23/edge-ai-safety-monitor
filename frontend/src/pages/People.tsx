import { Check, CircleAlert, ImagePlus, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { usePeople, usePeopleMutations } from "../api/queries";
import type { People as PeopleData, Person } from "../api/types";
import { PageHeader } from "../components/Layout";
import { BUTTON_PRIMARY, BUTTON_SECONDARY, Card, EmptyState, ErrorState, INPUT, Modal, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { bilingual, useText } from "../lib/i18n";

// People the cameras recognise by face (backend/people.py). Photos are checked by the detector within seconds
// of being added; this page says how they did, in plain words. Photos already added are never shown (user's
// decision, 2026-11-17): the server has no way to send them, only to add and delete.

const ENOUGH = 5; // usable photos for reliable recognition (docs/faces.md)
const MAX_SIDE = 1600; // photos are shrunk to this before upload: plenty for a face, and quick to send

const TEXT = bilingual(
  {
    title: "People",
    subtitle: "Who the cameras recognise by face",
    add: "Add a person",
    addTitle: "Add a person",
    editTitle: "Change the name",
    name: "Full name",
    nameAr: "Name in Arabic (optional)",
    nameArHint: "Shown when the console and reports are in Arabic.",
    cancel: "Cancel",
    save: "Save",
    none: "Nobody is enrolled yet",
    noneHint: "Add a person, then their photos. The cameras start recognising them a few seconds later.",
    running: (engine?: string) => `Face recognition is on${engine ? ` (${engine})` : ""}. New photos are checked within a few seconds.`,
    notRunning:
      "Face recognition isn't running right now, so new photos wait unchecked. It needs the detector running and the face models installed (scripts/get-face-models.sh).",
    guideTitle: "Photos that work",
    guide: [
      "5 to 10 photos per person. More variety matters more than more photos.",
      "One person per photo, face clear and sharp, looking roughly at the camera.",
      "Mix them: straight on, turned a little left and right, indoors and outdoors.",
      "Include 2 or 3 wearing a hard hat, as on site. Glasses on if they usually wear them.",
      "No sunglasses, masks, filters or heavy shadows. Recent photos, not old ones.",
    ],
    ready: "Ready",
    almost: (n: number) => `Recognised, but add ${n} more photo${n === 1 ? "" : "s"} for reliable results`,
    notYet: "Not recognised yet: add photos",
    usable: (ok: number, all: number) => (all ? `${ok} of ${all} photo${all === 1 ? "" : "s"} usable` : "No photos yet"),
    addPhotos: "Add photos",
    uploading: (n: number) => `Uploading ${n}…`,
    problems: {
      no_face: "No face found",
      small_face: "Face too small: stand closer",
      several_faces: "More than one face",
      unclear_face: "Face not clear or turned away",
      different_person: "Looks like someone else",
      unreadable: "File can't be read",
    } as Record<string, string>,
    checkingSome: (n: number) => `${n} new photo${n === 1 ? " is" : "s are"} being checked…`,
    unusable: (n: number) => `${n} photo${n === 1 ? " can't" : "s can't"} be used:`,
    removeUnusable: (n: number) => `Remove ${n === 1 ? "it" : `these ${n}`}`,
    hidden: "Photos already added are not shown here, to protect people's privacy.",
    rename: "Change name",
    removePerson: "Remove",
    confirmRemove: (name: string) => `Remove ${name} and all their photos? The cameras stop recognising them.`,
    cantRead: (file: string) => `${file} can't be opened here. Save it as a JPEG and try again.`,
    failed: (msg: string) => `Couldn't add a photo: ${msg}`,
    tooMany: (max: number) => `A person can have up to ${max} photos.`,
    privacy: "Face photos stay on this system. Once added, nobody can view or download them from the console. Enrol people only with their agreement.",
  },
  {
    title: "الأشخاص",
    subtitle: "من تتعرف عليهم الكاميرات من وجوههم",
    add: "إضافة شخص",
    addTitle: "إضافة شخص",
    editTitle: "تغيير الاسم",
    name: "الاسم الكامل",
    nameAr: "الاسم بالعربية (اختياري)",
    nameArHint: "يظهر حين تكون لوحة التحكم والتقارير بالعربية.",
    cancel: "إلغاء",
    save: "حفظ",
    none: "لم يُسجَّل أحد بعد",
    noneHint: "أضف شخصًا ثم صوره. تبدأ الكاميرات بالتعرف عليه بعد ثوانٍ.",
    running: (engine?: string) => `التعرف على الوجوه يعمل${engine ? ` (${engine})` : ""}. تُفحص الصور الجديدة خلال ثوانٍ.`,
    notRunning:
      "التعرف على الوجوه لا يعمل الآن، فتبقى الصور الجديدة دون فحص. يحتاج إلى تشغيل النظام وتثبيت نماذج الوجوه (scripts/get-face-models.sh).",
    guideTitle: "الصور المناسبة",
    guide: [
      "من 5 إلى 10 صور لكل شخص. التنوع أهم من العدد.",
      "شخص واحد في الصورة، والوجه واضح وحاد وينظر نحو الكاميرا تقريبًا.",
      "نوّعها: من الأمام، وملتفتًا قليلًا يمينًا ويسارًا، في الداخل والخارج.",
      "اجعل صورتين أو ثلاثًا بالخوذة كما في الموقع. وبالنظارة إن كان يلبسها عادة.",
      "بلا نظارات شمسية أو كمامات أو فلاتر أو ظلال قوية. صور حديثة لا قديمة.",
    ],
    ready: "جاهز",
    almost: (n: number) => (n === 1 ? "يُتعرَّف عليه، وأضف صورة أخرى لنتائج موثوقة" : `يُتعرَّف عليه، وأضف ${n} صور أخرى لنتائج موثوقة`),
    notYet: "لا يُتعرَّف عليه بعد: أضف صورًا",
    usable: (ok: number, all: number) => (all ? `${ok} من ${all} صالحة للاستخدام` : "لا صور بعد"),
    addPhotos: "إضافة صور",
    uploading: (n: number) => `جارٍ رفع ${n}…`,
    problems: {
      no_face: "لم يُعثر على وجه",
      small_face: "الوجه صغير: اقترب أكثر",
      several_faces: "أكثر من وجه",
      unclear_face: "الوجه غير واضح أو ملتفت",
      different_person: "تبدو لشخص آخر",
      unreadable: "تعذّرت قراءة الملف",
    },
    checkingSome: (n: number) => (n === 1 ? "صورة جديدة قيد الفحص…" : `${n} صور جديدة قيد الفحص…`),
    unusable: (n: number) => (n === 1 ? "صورة لا يمكن استخدامها:" : `${n} صور لا يمكن استخدامها:`),
    removeUnusable: (n: number) => (n === 1 ? "إزالتها" : `إزالة هذه الصور (${n})`),
    hidden: "لا تُعرض هنا الصور المضافة سابقًا، حفاظًا على خصوصية الأشخاص.",
    rename: "تغيير الاسم",
    removePerson: "إزالة",
    confirmRemove: (name: string) => `إزالة ${name} وكل صوره؟ ستتوقف الكاميرات عن التعرف عليه.`,
    cantRead: (file: string) => `تعذّر فتح ${file} هنا. احفظه بصيغة JPEG وحاول مجددًا.`,
    failed: (msg: string) => `تعذّرت إضافة صورة: ${msg}`,
    tooMany: (max: number) => `يمكن أن يكون للشخص حتى ${max} صورة.`,
    privacy: "تبقى صور الوجوه على هذا النظام. بعد إضافتها لا يمكن لأحد عرضها أو تنزيلها من لوحة التحكم. لا تسجّل أحدًا إلا بموافقته.",
  },
);

/** The photo as a JPEG no larger than MAX_SIDE, turned upright. Also drops the camera's hidden data (place, time). */
async function prepare(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("encode"))), "image/jpeg", 0.92),
  );
}

function NameDialog({ person, onClose }: { person?: Person; onClose: () => void }) {
  const t = useText(TEXT);
  const { add, rename } = usePeopleMutations();
  const [name, setName] = useState(person?.name ?? "");
  const [nameAr, setNameAr] = useState(person?.name_ar ?? "");
  const busy = add.isPending || rename.isPending;
  const error = add.error ?? rename.error;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const names = { name: name.trim(), name_ar: nameAr.trim() || null };
    if (person) rename.mutate({ id: person.person_id, ...names }, { onSuccess: onClose });
    else add.mutate(names, { onSuccess: onClose });
  };

  return (
    <Modal title={person ? t.editTitle : t.addTitle} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          {t.name}
          <input value={name} onChange={(e) => setName(e.target.value)} className={INPUT} maxLength={100} required autoFocus />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          {t.nameAr}
          <input value={nameAr} onChange={(e) => setNameAr(e.target.value)} className={INPUT} maxLength={100} dir="rtl" />
          <span className="mt-1.5 block text-xs font-normal text-slate-500">{t.nameArHint}</span>
        </label>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error.message}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
            {t.cancel}
          </button>
          <button type="submit" disabled={busy || !name.trim()} className={BUTTON_PRIMARY}>
            {person ? t.save : t.add}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function PersonCard({ person, limits, onRename }: { person: Person; limits: PeopleData["limits"]; onRename: () => void }) {
  const t = useText(TEXT);
  const { addPhoto, removePhoto, remove } = usePeopleMutations();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [removing, setRemoving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // what the detector made of the photos, as words: no picture is ever shown
  const checking = person.photos.filter((p) => !p.checked).length;
  const bad = person.photos.filter((p) => p.checked && !p.ok);
  const problemCounts = bad.reduce<Record<string, number>>((acc, p) => {
    const key = p.problem ?? "unreadable";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const removeUnusable = async () => {
    setRemoving(true);
    for (const p of bad) {
      try {
        await removePhoto.mutateAsync({ id: person.person_id, file: p.file });
      } catch {
        /* already gone */
      }
    }
    setRemoving(false);
  };

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setMessage(null);
    const room = limits.photos_per_person - person.photos.length;
    const chosen = [...files].slice(0, Math.max(room, 0));
    if (chosen.length < files.length) setMessage(t.tooMany(limits.photos_per_person));
    setUploading(chosen.length);
    for (const file of chosen) {
      try {
        const photo = await prepare(file).catch(() => {
          throw new Error(t.cantRead(file.name));
        });
        await addPhoto.mutateAsync({ id: person.person_id, photo });
      } catch (e) {
        const text = e instanceof Error ? e.message : String(e);
        setMessage(text.includes(file.name) ? text : t.failed(text));
      }
      setUploading((n) => n - 1);
    }
    if (input.current) input.current.value = "";
  };

  const status =
    person.usable >= ENOUGH
      ? { text: t.ready, style: "bg-emerald-50 text-emerald-800 ring-emerald-600/20" }
      : person.usable > 0
        ? { text: t.almost(ENOUGH - person.usable), style: "bg-amber-50 text-amber-900 ring-amber-600/20" }
        : { text: t.notYet, style: "bg-slate-50 text-slate-700 ring-slate-500/20" };

  return (
    <section className="rounded-2xl bg-white p-5 ring-1 ring-ink/[0.08]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-display text-xl font-semibold text-ink">{person.name}</h2>
          {person.name_ar && <p className="text-sm text-ink/60">{person.name_ar}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink/65">
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${status.style}`}>{status.text}</span>
            {t.usable(person.usable, person.photos.length)}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onRename} className="rounded-full p-2 text-ink/55 hover:bg-paper hover:text-ink" aria-label={t.rename} title={t.rename}>
            <Pencil className="h-4 w-4" />
          </button>
          <button
            onClick={() => window.confirm(t.confirmRemove(person.name)) && remove.mutate(person.person_id)}
            className="rounded-full p-2 text-ink/55 hover:bg-red-50 hover:text-red-700"
            aria-label={`${t.removePerson} ${person.name}`}
            title={t.removePerson}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {checking > 0 && (
        <p className="mt-4 flex items-center gap-2 text-sm text-ink/65">
          <Loader2 className="h-4 w-4 animate-spin" /> {t.checkingSome(checking)}
        </p>
      )}
      {bad.length > 0 && (
        <div className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="flex items-center gap-2 font-medium">
            <CircleAlert className="h-4 w-4 shrink-0" /> {t.unusable(bad.length)}
          </p>
          <ul className="mt-1.5 list-disc space-y-0.5 ps-9">
            {Object.entries(problemCounts).map(([problem, n]) => (
              <li key={problem}>
                {t.problems[problem] ?? problem}
                {n > 1 ? ` (${n})` : ""}
              </li>
            ))}
          </ul>
          <button
            onClick={removeUnusable}
            disabled={removing}
            className="mt-2.5 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-red-800 ring-1 ring-red-700/30 hover:bg-red-100 disabled:opacity-50"
          >
            {removing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} {t.removeUnusable(bad.length)}
          </button>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => input.current?.click()}
          disabled={uploading > 0 || person.photos.length >= limits.photos_per_person}
          className="inline-flex items-center gap-2 rounded-xl border-2 border-dashed border-ink/20 px-4 py-3 text-sm font-medium text-ink/70 hover:border-ink/40 hover:text-ink disabled:opacity-50"
        >
          {uploading > 0 ? <Loader2 className="h-5 w-5 animate-spin" /> : <ImagePlus className="h-5 w-5" />}
          {uploading > 0 ? t.uploading(uploading) : t.addPhotos}
        </button>
        <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
        <p className="text-xs text-ink/55">{t.hidden}</p>
      </div>
      {message && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{message}</p>}
    </section>
  );
}

export function People() {
  const t = useText(TEXT);
  const { user } = useAuth();
  const people = usePeople();
  const [dialog, setDialog] = useState<{ person?: Person } | null>(null);

  if (user?.role !== "manager") return <Navigate to="/app" replace />;
  if (people.isPending) return <Spinner />;
  if (people.isError) return <ErrorState error={people.error} onRetry={() => people.refetch()} />;
  const { recognition, people: list, limits } = people.data;

  return (
    <>
      <PageHeader
        title={t.title}
        subtitle={t.subtitle}
        actions={
          <button onClick={() => setDialog({})} className={BUTTON_PRIMARY}>
            <Plus className="h-4 w-4" /> {t.add}
          </button>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-5">
          <p
            className={`flex items-start gap-2 rounded-xl px-4 py-3 text-sm ${
              recognition.running ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900"
            }`}
          >
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${recognition.running ? "bg-emerald-500" : "bg-amber-500"}`} />
            {recognition.running ? t.running(recognition.engine) : t.notRunning}
          </p>
          {list.length ? (
            list.map((person) => <PersonCard key={person.person_id} person={person} limits={limits} onRename={() => setDialog({ person })} />)
          ) : (
            <Card>
              <EmptyState title={t.none}>{t.noneHint}</EmptyState>
            </Card>
          )}
        </div>
        <aside className="min-w-0 space-y-4">
          <Card title={t.guideTitle}>
            <ul className="space-y-2.5 text-sm leading-relaxed text-ink/75">
              {t.guide.map((line) => (
                <li key={line} className="flex gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> {line}
                </li>
              ))}
            </ul>
          </Card>
          <p className="px-1 text-xs leading-relaxed text-ink/55">{t.privacy}</p>
        </aside>
      </div>
      {dialog && <NameDialog person={dialog.person} onClose={() => setDialog(null)} />}
    </>
  );
}
