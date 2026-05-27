"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, HeartHandshake, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, socialAidApi, type AidContribution } from "@/lib/api";
import type { Association } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";

export default function AidHistoryPage() {
  const t = useTranslations("aidHistory");
  const tCommon = useTranslations("common");
  const { user } = useAuthStore();
  const isBureau = canDoBureauActions(user);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const { data: contributions = [], isLoading } = useQuery<AidContribution[]>({
    queryKey: ["aid-contributions", association?.id, since, until],
    queryFn: () =>
      socialAidApi.listContributions(association!.id, {
        since: since || undefined,
        until: until || undefined,
      }),
    enabled: !!association?.id,
  });

  // Per-member totals (bureau view only ; the list is already auto-scoped
  // for plain members, so the totals end up being theirs).
  const perMemberTotals = useMemo(() => {
    const map = new Map<string, { name: string; total: number }>();
    for (const c of contributions) {
      const key = c.membership_id;
      const cur = map.get(key);
      const name = c.member_name ?? "—";
      if (cur) cur.total += c.amount;
      else map.set(key, { name, total: c.amount });
    }
    return Array.from(map.entries())
      .map(([id, v]) => ({ id, ...v }))
      .sort((a, b) => b.total - a.total);
  }, [contributions]);

  const overallTotal = useMemo(
    () => contributions.reduce((s, c) => s + c.amount, 0),
    [contributions],
  );

  if (!association) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={isBureau ? t("titleBureau") : t("titleMember")}
        description={isBureau ? t("subtitleBureau") : t("subtitleMember")}
        actions={
          <Button asChild variant="ghost" className="gap-1.5">
            <Link href="/dashboard/social-aid">
              <ArrowLeft className="h-4 w-4" />
              {tCommon("back")}
            </Link>
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("since")}
            </label>
            <Input type="date" value={since} onChange={(e) => setSince(e.target.value)} className="h-9" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("until")}
            </label>
            <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="h-9" />
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-muted-foreground">{t("total")}</span>
            <span className="text-2xl font-bold tabular-nums">{fmt.currency(overallTotal)}</span>
          </div>
        </CardContent>
      </Card>

      {isBureau && contributions.length > 0 && (
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Users className="h-3.5 w-3.5" />
            {t("perMember")}
          </h3>
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-border">
                {perMemberTotals.map((m) => (
                  <li key={m.id} className="flex items-center justify-between px-4 py-2 text-sm">
                    <span className="truncate">{m.name}</span>
                    <span className="font-semibold tabular-nums">{fmt.currency(m.total)}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("entries")}
        </h3>
        {isLoading ? (
          <Skeleton className="h-32 w-full rounded-xl" />
        ) : contributions.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
              <HeartHandshake className="h-10 w-10" />
              <p>{t("empty")}</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-border">
                {contributions.map((c) => (
                  <li key={c.entry_id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate font-medium">
                        {c.aid_type_name ?? t("aidTypeUnknown")}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {fmt.date(c.meeting_date)} · {c.meeting_title}
                        {isBureau && c.member_name && <> · {c.member_name}</>}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {c.status === "draft" && (
                        <Badge variant="outline" className="text-[10px]">
                          {t("statusDraft")}
                        </Badge>
                      )}
                      <span className="font-semibold tabular-nums">{fmt.currency(c.amount)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
