"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownCircle,
  ArrowUpCircle,
  FileText,
  Repeat,
  PiggyBank,
  HeartHandshake,
  Banknote,
  CalendarRange,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/common/empty-state";
import { membersApi, type MemberActivity, type MemberActivityItem } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

type Family = "contribution" | "request" | "income";

const KIND_ICON: Record<string, typeof Repeat> = {
  tontine: Repeat,
  caisse: PiggyBank,
  aid: HeartHandshake,
  loan: Banknote,
  tontine_payout: Repeat,
  loan_disbursement: Banknote,
  aid_payout: HeartHandshake,
};

export function MemberActivityView({
  membershipId,
  currency,
}: {
  membershipId: string;
  currency?: string | null;
}) {
  const t = useTranslations("memberActivity");
  const fmt = useFormatters(currency ?? undefined);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [view, setView] = useState<"chrono" | "grouped">("grouped");

  const { data, isLoading } = useQuery<MemberActivity>({
    queryKey: ["member-activity", membershipId, since, until],
    queryFn: () =>
      membersApi.activity(membershipId, {
        since: since || undefined,
        until: until || undefined,
      }),
    enabled: !!membershipId,
  });

  const kindLabel = (kind: string) => {
    const map: Record<string, string> = {
      tontine: t("tontine"),
      caisse: t("caisse"),
      aid: t("aid"),
      loan: t("loan"),
      tontine_payout: t("tontinePayout"),
      loan_disbursement: t("loanDisbursement"),
      aid_payout: t("aidPayout"),
    };
    return map[kind] ?? kind;
  };

  // Timeline fusionnée (vue chronologique).
  const timeline = useMemo(() => {
    if (!data) return [];
    const tag = (items: MemberActivityItem[], family: Family) =>
      items.map((i) => ({ ...i, family }));
    return [
      ...tag(data.contributions, "contribution"),
      ...tag(data.requests, "request"),
      ...tag(data.incomes, "income"),
    ].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  }, [data]);

  const familyMeta: Record<Family, { label: string; cls: string }> = {
    contribution: { label: t("contributionTag"), cls: "text-sky-600 dark:text-sky-400" },
    request: { label: t("requestTag"), cls: "text-amber-600 dark:text-amber-400" },
    income: { label: t("incomeTag"), cls: "text-emerald-600 dark:text-emerald-400" },
  };

  return (
    <div className="space-y-4">
      {/* Filtres période + bascule de vue */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t("from")}
          <Input type="date" value={since} onChange={(e) => setSince(e.target.value)} className="h-9 w-40" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t("to")}
          <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="h-9 w-40" />
        </label>
        <div className="ml-auto inline-flex rounded-lg border p-0.5">
          <button
            onClick={() => setView("grouped")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              view === "grouped" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {t("byActivity")}
          </button>
          <button
            onClick={() => setView("chrono")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              view === "chrono" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {t("chronological")}
          </button>
        </div>
      </div>

      {/* Totaux */}
      <div className="grid gap-3 sm:grid-cols-3">
        <TotalCard icon={ArrowUpCircle} label={t("totalContributed")} value={fmt.currency(data?.totals?.contributed ?? 0)} cls="text-sky-600 dark:text-sky-400" />
        <TotalCard icon={FileText} label={t("totalRequested")} value={fmt.currency(data?.totals?.requested ?? 0)} cls="text-amber-600 dark:text-amber-400" />
        <TotalCard icon={ArrowDownCircle} label={t("totalReceived")} value={fmt.currency(data?.totals?.received ?? 0)} cls="text-emerald-600 dark:text-emerald-400" />
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : !data ||
        (timeline.length === 0) ? (
        <EmptyState icon={CalendarRange} title={t("empty")} description={t("emptyDesc")} />
      ) : view === "chrono" ? (
        <Card>
          <CardContent className="divide-y p-0">
            {timeline.map((it, idx) => {
              const Icon = KIND_ICON[it.kind] ?? FileText;
              const fam = familyMeta[it.family as Family];
              return (
                <div key={idx} className="flex items-center gap-3 px-4 py-2.5">
                  <Icon className={cn("h-4 w-4 shrink-0", fam.cls)} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn("text-[10px] font-semibold uppercase", fam.cls)}>{fam.label}</span>
                      <span className="truncate text-sm">{it.label || kindLabel(it.kind)}</span>
                      {it.reference && (
                        <span className="font-mono text-[10px] text-muted-foreground">{it.reference}</span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {it.date ? fmt.date(it.date) : "—"}
                      {it.meeting_title ? ` · ${it.meeting_title}` : ""}
                      {it.status ? ` · ${it.status}` : ""}
                    </span>
                  </div>
                  <span className="shrink-0 text-sm font-medium">{fmt.currency(it.amount)}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <ActivityGroup
            title={t("contributionsTitle")}
            items={data.contributions}
            byKind={data.contributions_by_kind}
            kindLabel={kindLabel}
            fmt={fmt}
          />
          <ActivityGroup
            title={t("requestsTitle")}
            items={data.requests}
            kindLabel={kindLabel}
            fmt={fmt}
          />
          <ActivityGroup
            title={t("incomesTitle")}
            items={data.incomes}
            byKind={data.incomes_by_kind}
            kindLabel={kindLabel}
            fmt={fmt}
          />
        </div>
      )}
    </div>
  );
}

function TotalCard({
  icon: Icon,
  label,
  value,
  cls,
}: {
  icon: typeof ArrowUpCircle;
  label: string;
  value: string;
  cls: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className={cn("h-6 w-6 shrink-0", cls)} />
        <div className="min-w-0">
          <p className="truncate text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ActivityGroup({
  title,
  items,
  byKind,
  kindLabel,
  fmt,
}: {
  title: string;
  items: MemberActivityItem[];
  byKind?: Record<string, number>;
  kindLabel: (k: string) => string;
  fmt: ReturnType<typeof useFormatters>;
}) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        {byKind && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(byKind).map(([k, v]) => (
              <Badge key={k} variant="secondary" className="text-[10px]">
                {kindLabel(k)}: {fmt.currency(v)}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <Card>
        <CardContent className="divide-y p-0">
          {items.map((it, idx) => {
            const Icon = KIND_ICON[it.kind] ?? FileText;
            return (
              <div key={idx} className="flex items-center gap-3 px-4 py-2.5">
                <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm">{it.label || kindLabel(it.kind)}</span>
                    {it.reference && (
                      <span className="font-mono text-[10px] text-muted-foreground">{it.reference}</span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {it.date ? fmt.date(it.date) : "—"}
                    {it.meeting_title ? ` · ${it.meeting_title}` : ""}
                    {it.status ? ` · ${it.status}` : ""}
                  </span>
                </div>
                <span className="shrink-0 text-sm font-medium">{fmt.currency(it.amount)}</span>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
