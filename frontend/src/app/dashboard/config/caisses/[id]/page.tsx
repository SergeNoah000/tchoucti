"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, PlayCircle, Settings, Users, History, AlertTriangle, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/common/page-header";
import {
  associationsApi,
  caissesApi,
} from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  Association,
  Caisse,
  CaisseContributorBalance,
  CaisseDistribution,
  MemberBalance,
} from "@/lib/types";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function CaisseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("configCaisses");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canConfigure = canConfigureAssociation(user);

  const { data: caisse, isLoading } = useQuery<Caisse>({
    queryKey: ["caisse", id],
    queryFn: () => caissesApi.get(id),
    enabled: !!id,
  });

  const { data: association } = useQuery<Association>({
    queryKey: ["association"],
    queryFn: async () => (await associationsApi.list())[0],
  });
  const fmt = useFormatters(association?.currency);

  const { data: contributors = [] } = useQuery<CaisseContributorBalance[]>({
    queryKey: ["caisse", id, "contributors"],
    queryFn: () => caissesApi.contributors(id),
    enabled: !!id,
  });

  const { data: distributions = [] } = useQuery<CaisseDistribution[]>({
    queryKey: ["caisse", id, "distributions"],
    queryFn: () => caissesApi.distributions(id),
    enabled: !!id,
  });

  const isPersonal = caisse?.category === "personal";
  // L'objectif min par membre vaut pour tous les types : on montre l'onglet
  // « Membres » dès qu'un minimum est défini, ou pour les caisses personnelles.
  const showMembers = isPersonal || (caisse?.member_min_balance ?? 0) > 0;
  const { data: memberBalances = [] } = useQuery<MemberBalance[]>({
    queryKey: ["caisse", id, "member-balances"],
    queryFn: () => caissesApi.memberBalances(id),
    enabled: !!id && showMembers,
  });
  const belowMinCount = memberBalances.filter((m) => m.below_min).length;

  const closeMutation = useMutation({
    mutationFn: () => caissesApi.closeDistribution(id),
    onSuccess: () => {
      toast.success(t("closeOk"));
      queryClient.invalidateQueries({ queryKey: ["caisse", id] });
      queryClient.invalidateQueries({ queryKey: ["caisse", id, "contributors"] });
      queryClient.invalidateQueries({ queryKey: ["caisse", id, "distributions"] });
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  if (isLoading || !caisse) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  const isShared = caisse.interest_distribution === "shared_pro_rata";
  const totalApport = contributors.reduce((s, c) => s + c.apport_cum, 0);

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/config/caisses">
          <ArrowLeft className="h-4 w-4" />
          {tCommon("back")}
        </Link>
      </Button>

      <PageHeader
        title={caisse.name}
        description={caisse.description ?? undefined}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{t(`cat_${caisse.category}`)}</Badge>
        {isShared && <Badge variant="secondary">{t("sharedBadge")}</Badge>}
        {!caisse.is_active && <Badge variant="outline">{t("inactive")}</Badge>}
        {caisse.last_distribution_at && (
          <span className="text-xs text-muted-foreground">
            {t("lastDistribution")}: {fmt.date(caisse.last_distribution_at)}
          </span>
        )}
      </div>

      <Tabs defaultValue="config">
        <TabsList>
          <TabsTrigger value="config" className="gap-1.5">
            <Settings className="h-3.5 w-3.5" />
            {t("tabConfig")}
          </TabsTrigger>
          {showMembers && (
            <TabsTrigger value="members" className="gap-1.5">
              <Wallet className="h-3.5 w-3.5" />
              {t("tabMembers")} ({memberBalances.length})
              {belowMinCount > 0 && (
                <Badge variant="destructive" className="ml-1 px-1.5 text-[10px]">{belowMinCount}</Badge>
              )}
            </TabsTrigger>
          )}
          <TabsTrigger value="contributors" className="gap-1.5">
            <Users className="h-3.5 w-3.5" />
            {t("tabContributors")} ({contributors.length})
          </TabsTrigger>
          <TabsTrigger value="distributions" className="gap-1.5">
            <History className="h-3.5 w-3.5" />
            {t("tabDistributions")} ({distributions.length})
          </TabsTrigger>
        </TabsList>

        {/* Onglet Config — vue lecture seule */}
        <TabsContent value="config" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label={t("category")} value={t(`cat_${caisse.category}`)} />
              {caisse.is_recurring && (
                <Row label={t("recurring")} value={`${fmt.currency(caisse.recurring_amount)}/séance`} />
              )}
              {caisse.is_member_required && (
                <Row label={t("required")} value={`${fmt.currency(caisse.member_required_amount)}/membre`} />
              )}
              {caisse.member_min_balance > 0 && (
                <Row label={t("memberMinBalance")} value={`${fmt.currency(caisse.member_min_balance)}/membre`} />
              )}
              {caisse.has_ceiling && <Row label={t("ceiling")} value={fmt.currency(caisse.ceiling_amount)} />}
              {caisse.has_objective && (
                <Row label={t("objective")} value={fmt.currency(caisse.objective_amount)} />
              )}
              {isShared && (
                <>
                  <Row label={t("sharedMode")} value={t("sharedActive")} />
                  <Row label={t("distributionPeriod")} value={t(`period_${caisse.distribution_period}`)} />
                  <Row label={t("withdrawalMode")} value={t(`withdraw_${caisse.withdrawal_mode}`)} />
                </>
              )}
              <p className="pt-2 text-xs text-muted-foreground">{t("editFromListHint")}</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Onglet Membres (caisses personnelles) — solde + zone rouge */}
        {showMembers && (
          <TabsContent value="members" className="mt-4">
            {caisse.member_min_balance > 0 && (
              <p className="mb-3 text-xs text-muted-foreground">
                {t("memberMinBalanceLegend", { amount: fmt.currency(caisse.member_min_balance) })}
              </p>
            )}
            {memberBalances.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-sm text-muted-foreground">
                  {t("noMembers")}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-0">
                  <ul className="divide-y divide-border">
                    {memberBalances.map((m) => (
                      <li
                        key={m.membership_id}
                        className={cn(
                          "flex items-center justify-between gap-3 px-4 py-2.5 text-sm",
                          m.below_min && "bg-destructive/5",
                        )}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          {m.below_min && <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />}
                          <span className="truncate font-medium">{m.member_name ?? "—"}</span>
                        </span>
                        <span
                          className={cn(
                            "shrink-0 font-semibold tabular-nums",
                            m.below_min ? "text-destructive" : "text-foreground",
                          )}
                        >
                          {fmt.currency(m.balance)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        )}

        {/* Onglet Cotisants */}
        <TabsContent value="contributors" className="mt-4">
          {contributors.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {t("noContributors")}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 font-medium">{t("colMember")}</th>
                      <th className="px-4 py-3 text-right font-medium">{t("colApport")}</th>
                      <th className="px-4 py-3 text-right font-medium">{t("colInterest")}</th>
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
                          <td className="px-4 py-3 text-right tabular-nums text-emerald-700 dark:text-emerald-400">
                            {fmt.currency(c.interest_cum)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{pct}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Onglet Distributions */}
        <TabsContent value="distributions" className="mt-4 space-y-3">
          {isShared && canConfigure && (
            <div className="flex justify-end">
              <Button
                onClick={() => closeMutation.mutate()}
                disabled={closeMutation.isPending}
                className="gap-2"
              >
                {closeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="h-4 w-4" />
                )}
                {t("closeNow")}
              </Button>
            </div>
          )}

          {distributions.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {t("noDistributions")}
              </CardContent>
            </Card>
          ) : (
            <ul className="space-y-2">
              {distributions.map((d) => (
                <li key={d.id} className="rounded-lg border border-border bg-card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold">{d.period_label}</p>
                      <p className="text-xs text-muted-foreground">
                        {fmt.date(d.period_start)} → {fmt.date(d.period_end)}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-right">
                      <div>
                        <p className="text-xs text-muted-foreground">{t("colPool")}</p>
                        <p className="text-base font-bold tabular-nums text-emerald-700 dark:text-emerald-400">
                          {fmt.currency(d.interest_pool)}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">{t("colBase")}</p>
                        <p className="text-base font-bold tabular-nums">{fmt.currency(d.total_base)}</p>
                      </div>
                    </div>
                  </div>
                  {d.shares.length > 0 && (
                    <ul className="mt-3 grid grid-cols-1 gap-1 sm:grid-cols-2">
                      {d.shares.map((s) => (
                        <li
                          key={s.membership_id}
                          className="flex items-center justify-between gap-2 rounded-md bg-muted/30 px-2.5 py-1.5 text-xs"
                        >
                          <span className="truncate">{s.member_name ?? "—"}</span>
                          <span className="shrink-0 tabular-nums">{fmt.currency(s.share_amount)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}
