"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, PiggyBank, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, caissesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";
import type {
  Association,
  Caisse,
  CaisseDistribution,
  MyShareItem,
} from "@/lib/types";

export default function MyShareDetailPage() {
  const { caisseId } = useParams<{ caisseId: string }>();
  const t = useTranslations("myShare");
  const tCommon = useTranslations("common");
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const { data: caisse } = useQuery<Caisse>({
    queryKey: ["caisse", caisseId],
    queryFn: () => caissesApi.get(caisseId),
    enabled: !!caisseId,
  });

  const { data: myShares = [] } = useQuery<MyShareItem[]>({
    queryKey: ["my-shares", association?.id],
    queryFn: () => caissesApi.myShares(association!.id),
    enabled: !!association,
  });
  const mine = useMemo(
    () => myShares.find((m) => m.caisse_id === caisseId),
    [myShares, caisseId],
  );

  const { data: distributions = [], isLoading } = useQuery<CaisseDistribution[]>({
    queryKey: ["caisse", caisseId, "distributions"],
    queryFn: () => caissesApi.distributions(caisseId),
    enabled: !!caisseId,
  });

  // Filtrage des shares qui me concernent (matching par nom — fragile mais OK).
  const myRows = useMemo(() => {
    const myName = user?.full_name;
    if (!myName) return [];
    const out: { period_label: string; period_end: string; base: number; share_amount: number }[] = [];
    for (const d of distributions) {
      const s = d.shares.find((x) => x.member_name === myName);
      if (s) {
        out.push({
          period_label: d.period_label,
          period_end: d.period_end,
          base: s.base,
          share_amount: s.share_amount,
        });
      }
    }
    return out;
  }, [distributions, user?.full_name]);

  const pct = mine && mine.total_apport > 0
    ? Math.round((mine.apport_cum / mine.total_apport) * 1000) / 10
    : 0;

  if (!caisse || !mine) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-32 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/my-share">
          <ArrowLeft className="h-4 w-4" />
          {tCommon("back")}
        </Link>
      </Button>

      <PageHeader title={t("detailTitle", { name: caisse.name })} description={t("detailSubtitle")} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <PiggyBank className="h-4 w-4" />
              {t("apport")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums">{fmt.currency(mine.apport_cum)}</p>
            <p className="text-xs text-muted-foreground">{t("share")}: {pct}% {t("ofPool")}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <TrendingUp className="h-4 w-4" />
              {t("interest")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums text-emerald-700 dark:text-emerald-400">
              {fmt.currency(mine.interest_cum)}
            </p>
            <p className="text-xs text-muted-foreground">
              {mine.last_distribution_at
                ? `${t("lastClose")}: ${fmt.date(mine.last_distribution_at)}`
                : t("noCloseYet")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t("mode")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <Badge variant={caisse.interest_distribution === "shared_pro_rata" ? "secondary" : "outline"}>
              {caisse.interest_distribution === "shared_pro_rata" ? t("modeShared") : t("modeKept")}
            </Badge>
            {caisse.interest_distribution === "shared_pro_rata" && (
              <p className="text-xs text-muted-foreground">
                {t("period")}: {t(`period_${caisse.distribution_period}`)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("historyTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6"><Skeleton className="h-20 w-full rounded" /></div>
          ) : myRows.length === 0 ? (
            <p className="px-6 py-10 text-center text-sm text-muted-foreground">{t("historyEmpty")}</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t("colPeriod")}</th>
                  <th className="px-4 py-3 text-right font-medium">{t("colBaseMine")}</th>
                  <th className="px-4 py-3 text-right font-medium">{t("colReceived")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {myRows.map((r, i) => (
                  <tr key={i}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{r.period_label}</p>
                      <p className="text-xs text-muted-foreground">{fmt.date(r.period_end)}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmt.currency(r.base)}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700 dark:text-emerald-400">
                      {fmt.currency(r.share_amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// re-export translation keys used: period_per_meeting, period_monthly, period_quarterly, period_annually
// (déjà déclarés dans configCaisses ; ici on les redéfinit dans myShare i18n).
