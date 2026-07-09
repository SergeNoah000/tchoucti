"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, TrendingUp, Users, History } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { CaissePronostics } from "@/components/caisses/caisse-pronostics";
import { associationsApi, caissesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type {
  Association,
  Caisse,
  CaisseContributorBalance,
  CaisseDistribution,
} from "@/lib/types";

export default function CaisseGainsDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("caissesView");
  const tCommon = useTranslations("common");
  const { user } = useAuthStore();
  const isBureau = canDoBureauActions(user);

  const { data: association } = useQuery<Association>({
    queryKey: ["association"],
    queryFn: async () => (await associationsApi.list())[0],
  });
  const fmt = useFormatters(association?.currency);

  const { data: caisse } = useQuery<Caisse>({
    queryKey: ["caisse", id],
    queryFn: () => caissesApi.get(id),
    enabled: !!id,
  });

  const { data: contributors = [] } = useQuery<CaisseContributorBalance[]>({
    queryKey: ["caisse", id, "contributors"],
    queryFn: () => caissesApi.contributors(id),
    enabled: !!id && isBureau,
  });

  const { data: distributions = [] } = useQuery<CaisseDistribution[]>({
    queryKey: ["caisse", id, "distributions"],
    queryFn: () => caissesApi.distributions(id),
    enabled: !!id && isBureau,
  });

  const totalApport = useMemo(
    () => contributors.reduce((s, c) => s + c.apport_cum, 0),
    [contributors],
  );
  const totalInterest = useMemo(
    () => contributors.reduce((s, c) => s + c.interest_cum, 0),
    [contributors],
  );

  if (!caisse) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  const kept = caisse.interest_distribution === "kept";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/caisses">
          <ArrowLeft className="h-4 w-4" />
          {tCommon("back")}
        </Link>
      </Button>

      <PageHeader title={caisse.name} description={caisse.description || undefined} />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{t(`cat_${caisse.category}`)}</Badge>
        <Badge variant={kept ? "outline" : "secondary"}>
          {kept ? t("modeKept") : t("modeShared")}
        </Badge>
      </div>

      {isBureau ? (
        <Tabs defaultValue="gains">
          <TabsList>
            <TabsTrigger value="gains" className="gap-1.5">
              <Users className="h-3.5 w-3.5" />
              {t("tabGains")} ({contributors.length})
            </TabsTrigger>
            <TabsTrigger value="pronostics" className="gap-1.5">
              <TrendingUp className="h-3.5 w-3.5" />
              {t("tabPronostics")}
            </TabsTrigger>
            <TabsTrigger value="distributions" className="gap-1.5">
              <History className="h-3.5 w-3.5" />
              {t("tabDistributions")} ({distributions.length})
            </TabsTrigger>
          </TabsList>

          {/* Gains des cotisants : apport + intérêts gagnés + part */}
          <TabsContent value="gains" className="mt-4">
            {contributors.length === 0 ? (
              <EmptyState icon={Users} title={t("noContributors")} description={t("noContributorsDesc")} />
            ) : (
              <Card>
                <CardContent className="overflow-x-auto p-0">
                  <table className="w-full min-w-[520px] text-sm">
                    <thead className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="px-4 py-3 font-medium">{t("colMember")}</th>
                        <th className="px-4 py-3 text-right font-medium">{t("colApport")}</th>
                        <th className="px-4 py-3 text-right font-medium">{t("colGains")}</th>
                        <th className="px-4 py-3 text-right font-medium">{t("colShare")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {contributors.map((c) => {
                        const pct = totalApport > 0 ? Math.round((c.apport_cum / totalApport) * 1000) / 10 : 0;
                        return (
                          <tr key={c.membership_id}>
                            <td className="px-4 py-3 font-medium">{c.member_name ?? "—"}</td>
                            <td className="px-4 py-3 text-right tabular-nums">{fmt.currency(c.apport_cum)}</td>
                            <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700 dark:text-emerald-400">
                              {fmt.currency(c.interest_cum)}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{pct}%</td>
                          </tr>
                        );
                      })}
                      <tr className="bg-muted/20 font-semibold">
                        <td className="px-4 py-3">{t("total")}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{fmt.currency(totalApport)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-emerald-700 dark:text-emerald-400">
                          {fmt.currency(totalInterest)}
                        </td>
                        <td className="px-4 py-3" />
                      </tr>
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}
            {!kept && (
              <p className="mt-2 text-xs text-muted-foreground">{t("gainsHint")}</p>
            )}
          </TabsContent>

          {/* Pronostics : gains à venir projetés */}
          <TabsContent value="pronostics" className="mt-4">
            <CaissePronostics caisseId={id} currency={association?.currency} />
          </TabsContent>

          {/* Historique des distributions */}
          <TabsContent value="distributions" className="mt-4 space-y-3">
            {distributions.length === 0 ? (
              <EmptyState icon={History} title={t("noDistributions")} description={t("noDistributionsDesc")} />
            ) : (
              distributions.map((d) => (
                <Card key={d.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-sm">
                      <span>{d.period_label}</span>
                      <span className="tabular-nums text-emerald-700 dark:text-emerald-400">
                        {fmt.currency(d.interest_pool)}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <table className="w-full text-sm">
                      <tbody className="divide-y divide-border">
                        {d.shares.map((s, i) => (
                          <tr key={i}>
                            <td className="px-4 py-2">{s.member_name ?? "—"}</td>
                            <td className="px-4 py-2 text-right tabular-nums text-emerald-700 dark:text-emerald-400">
                              {fmt.currency(s.share_amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>
        </Tabs>
      ) : (
        // Membre : sa vue locale (part projetée) — les gains des autres restent
        // réservés au bureau/admin.
        <CaissePronostics caisseId={id} currency={association?.currency} />
      )}
    </div>
  );
}
