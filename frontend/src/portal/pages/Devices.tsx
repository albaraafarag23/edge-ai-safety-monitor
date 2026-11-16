/** Devices waiting for approval (overseer: managers' and their own; managers: their staff's), and My devices. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { bilingual, useText } from "../../lib/i18n";
import { cancelledByBrowser, get, send, type Approval, type Device } from "../api";
import { BTN, BTN_LINE, Dot, Header, Panel, problem, useLocale, useMe, when, WORDS } from "../shell";

const TEXT = bilingual(
  {
    newDevice: "New device",
    asks: (label: string, at: string) => `Wants to sign in from ${label} (asked ${at}). Only approve it if you know about it.`,
    approve: "Approve",
    refuse: "Refuse",
    title: "Approvals",
    lead: "New phones and laptops wait here until someone approves them. You approve managers' devices; managers approve their own staff.",
    leadManager: "Your staff's new phones and laptops wait here until you approve them.",
    none: "Nothing is waiting.",
    failed: "That didn't work. Try again.",
    cancelled: "The passkey prompt was closed, so nothing was changed.",
    myTitle: "My devices",
    myLead: "The phones and laptops that can sign in as you. Remove any you've lost or no longer use.",
    thisOne: "This device",
    lastUsed: (at: string) => `Last used ${at}`,
    addedAt: (at: string) => `Added ${at}`,
    remove: "Remove",
    addAnother: "To add another device, open the portal on it and choose “Ask to add this device”.",
  },
  {
    newDevice: "جهاز جديد",
    asks: (label: string, at: string) => `يريد الدخول من ${label} (طلب ${at}). لا توافق إلا إذا كنت تعلم بذلك.`,
    approve: "موافقة",
    refuse: "رفض",
    title: "الموافقات",
    lead: "تنتظر الهواتف والحواسيب الجديدة هنا حتى يوافق عليها أحد. توافق أنت على أجهزة المديرين، ويوافق المديرون على أجهزة موظفيهم.",
    leadManager: "تنتظر هواتف وحواسيب موظفيك الجديدة هنا حتى توافق عليها.",
    none: "لا شيء ينتظر.",
    failed: "لم ينجح ذلك. حاول مرة أخرى.",
    cancelled: "أُغلقت نافذة مفتاح المرور، فلم يتغير شيء.",
    myTitle: "أجهزتي",
    myLead: "الهواتف والحواسيب التي يمكنها الدخول باسمك. أزل أي جهاز فقدته أو لم تعد تستخدمه.",
    thisOne: "هذا الجهاز",
    lastUsed: (at: string) => `آخر استخدام ${at}`,
    addedAt: (at: string) => `أُضيف ${at}`,
    remove: "إزالة",
    addAnother: "لإضافة جهاز آخر، افتح البوابة عليه واختر «اطلب إضافة هذا الجهاز».",
  },
);

function useDecide() {
  const qc = useQueryClient();
  const t = useText(TEXT);
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: "approve" | "refuse" | "revoke" }) =>
      send<Device>(`/devices/${id}/decision`, { decision }),
    onMutate: () => setError(null),
    onError: (err) => setError(cancelledByBrowser(err) ? t.cancelled : problem(err, t.failed)),
    onSettled: () => qc.invalidateQueries(),
  });
  return { mutation, error };
}

export function ApprovalCards({ items }: { items: Approval[] }) {
  const t = useText(TEXT);
  const words = useText(WORDS);
  const locale = useLocale();
  const { mutation, error } = useDecide();
  return (
    <div className="flex flex-col gap-3">
      {error && <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{error}</p>}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
        {items.map((a) => (
          <article key={a.id} className="flex flex-col gap-2.5 rounded-2xl border border-[#d9d2c4] bg-white p-5">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[#7c4a03]">
              <Dot tone="warn" /> {t.newDevice} · {words.role[a.person.role]}
            </div>
            <h3 className="text-lg font-semibold"><bdi>{a.person.name}</bdi>{a.company ? <> · <bdi>{a.company}</bdi></> : null}</h3>
            <p className="text-sm leading-relaxed text-[#4a4439]">{t.asks(a.label, when(a.created_at, locale))}</p>
            <div className="mt-1 flex flex-wrap gap-2.5">
              <button type="button" className={BTN} disabled={mutation.isPending}
                onClick={() => mutation.mutate({ id: a.id, decision: "approve" })}>{t.approve}</button>
              <button type="button" className={BTN_LINE} disabled={mutation.isPending}
                onClick={() => mutation.mutate({ id: a.id, decision: "refuse" })}>{t.refuse}</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export function Approvals() {
  const t = useText(TEXT);
  const me = useMe();
  const items = useQuery({ queryKey: ["approvals"], queryFn: () => get<Approval[]>("/approvals"), refetchInterval: 30_000 });
  return (
    <>
      <Header title={t.title} lead={me.data?.role === "overseer" ? t.lead : t.leadManager} />
      {items.data?.length === 0 ? <Panel><p className="text-sm text-[#4a4439]">{t.none}</p></Panel>
        : items.data && <ApprovalCards items={items.data} />}
    </>
  );
}

export function MyDevices() {
  const t = useText(TEXT);
  const words = useText(WORDS);
  const locale = useLocale();
  const devices = useQuery({ queryKey: ["my-devices"], queryFn: () => get<Device[]>("/me/devices") });
  const { mutation, error } = useDecide();
  const tone = { approved: "good", pending: "warn", refused: "off", revoked: "off" } as const;
  return (
    <>
      <Header title={t.myTitle} lead={t.myLead} />
      {error && <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{error}</p>}
      <Panel>
        <ul className="flex flex-col divide-y divide-[#ece8df]">
          {devices.data?.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-3 py-3.5">
              <div className="flex flex-col gap-0.5">
                <span className="flex items-center gap-2 font-semibold">
                  <Dot tone={tone[d.status]} /> {d.label}
                  {d.this && <span className="rounded-full bg-ink px-2 py-0.5 text-xs text-paper">{t.thisOne}</span>}
                </span>
                <span className="text-[13px] text-[#4a4439]">
                  {words.device[d.status]} · {d.last_used ? t.lastUsed(when(d.last_used, locale)) : t.addedAt(when(d.created_at, locale))}
                </span>
              </div>
              {!d.this && (d.status === "approved" || d.status === "pending") && (
                <button type="button" className={BTN_LINE} disabled={mutation.isPending}
                  onClick={() => mutation.mutate({ id: d.id, decision: "revoke" })}>{t.remove}</button>
              )}
            </li>
          ))}
        </ul>
      </Panel>
      <p className="text-[13px] text-[#6b6355]">{t.addAnother}</p>
    </>
  );
}
