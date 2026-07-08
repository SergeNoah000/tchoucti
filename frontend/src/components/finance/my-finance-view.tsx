"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Wallet, HandCoins, HeartHandshake, PiggyBank, ArrowDownLeft, ArrowUpRight, TrendingUp } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { EmptyState } from "@/components/common/empty-state";
import { CaissePronostics } from "@/components/caisses/caisse-pronostics";
import { financeApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MyFinanceSummary } from "@/lib/types";

/** Vue « Mes cotisations » — historique financier propre au membre. */
export function MyFinanceView({ associationId, currency }: { associationId: string; currency?: string }) {
  const t = useTranslations("myFinance");
  const tPronostics = useTranslations("caissePronostics");
  const fmt = useFormatters(currency);
  const [pronosticCaisse, setPronosticCaisse] = useState<{ id: string; name: string } | null>(null);

  const { data, isLoading } = useQuery<MyFinanceSummary>({
    queryKey: ["my-finance", associationId],
    queryFn: () => financeApi.mySummary(associationId),
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label={t("totalContributed")} value={fmt.currency(data.total_contributed)} icon={Wallet} accent="brand" />
        <StatCard label={t("loansOutstanding")} value={fmt.currency(data.total_loans_outstanding)} icon={HandCoins} accent="amber" />
        <StatCard label={t("aidsReceived")} value={fmt.currency(data.total_aids_received)} icon={HeartHandshake} accent="emerald" />
      </div>

      {/* Mes caisses */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <PiggyBank className="h-4 w-4" /> {t("myCaisses")}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.caisses.length === 0 ? (
            <p className="px-6 py-8 text-center text-sm text-muted-foreground">{t("noCaisses")}</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t("caisse")}</th>
                  <th className="px-4 py-3 text-right font-medium">{t("contributed")}</th>
                  <th className="px-4 py-3 text-right font-medium">{t("balanceOrInterest")}</th>
                  <th className="px-2 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.caisses.map((c) => (
                  <tr key={c.caisse_id}>
                    <td className="px-4 py-3">
                      <span className="font-medium">{c.caisse_name}</span>{" "}
                      <Badge variant="outline" className="ml-1 text-[10px]">{t(`cat_${c.category}`)}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmt.currency(c.my_contributed)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {c.my_personal_balance != null
                        ? fmt.currency(c.my_personal_balance)
                        : c.my_interest
                          ? <span className="text-emerald-700 dark:text-emerald-400">+{fmt.currency(c.my_interest)}</span>
                          : "—"}
                    </td>
                    <td className="px-2 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setPronosticCaisse({ id: c.caisse_id, name: c.caisse_name })}
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        title={tPronostics("tab")}
                      >
                        <TrendingUp className="h-3.5 w-3.5" />
                        {tPronostics("tab")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Mes prêts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <HandCoins className="h-4 w-4" /> {t("myLoans")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.loans.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">{t("noLoans")}</p>
            ) : (
              data.loans.map((l) => (
                <div key={l.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-muted/20 px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{l.reference}</p>
                    <p className="text-xs text-muted-foreground">{fmt.currency(l.principal)} · {t(`loanStatus_${l.status}`)}</p>
                  </div>
                  <span className="shrink-0 text-right text-xs">
                    <span className="text-muted-foreground">{t("remaining")}</span>{" "}
                    <span className="font-semibold tabular-nums">{fmt.currency(l.remaining)}</span>
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Mes aides */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <HeartHandshake className="h-4 w-4" /> {t("myAids")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.aids.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">{t("noAids")}</p>
            ) : (
              data.aids.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-muted/20 px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{a.title}</p>
                    <p className="text-xs text-muted-foreground">{a.reference} · {t(`aidStatus_${a.status}`)}</p>
                  </div>
                  <span className="shrink-0 font-semibold tabular-nums">{fmt.currency(a.paid_amount || a.approved_amount)}</span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Mes mouvements */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("myMovements")}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.movements.length === 0 ? (
            <EmptyState icon={Wallet} title={t("noMovements")} />
          ) : (
            <ul className="divide-y divide-border">
              {data.movements.map((m, i) => {
                const isIn = m.direction === "in";
                return (
                  <li key={i} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <div className="flex min-w-0 items-center gap-2">
                      {isIn ? <ArrowDownLeft className="h-4 w-4 text-emerald-600" /> : <ArrowUpRight className="h-4 w-4 text-destructive" />}
                      <div className="min-w-0">
                        <p className="truncate font-medium">{m.label}</p>
                        <p className="text-xs text-muted-foreground">{fmt.date(m.occurred_on)}{m.fund_name ? ` · ${m.fund_name}` : ""}</p>
                      </div>
                    </div>
                    <span className={cn("shrink-0 font-semibold tabular-nums", isIn ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
                      {isIn ? "+" : "−"}{fmt.currency(m.amount)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Pronostics d'une caisse — vue LOCALE du membre (sa part projetée) */}
      <Dialog open={!!pronosticCaisse} onOpenChange={(o) => !o && setPronosticCaisse(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              {pronosticCaisse?.name} — {tPronostics("tab")}
            </DialogTitle>
          </DialogHeader>
          {pronosticCaisse && (
            <CaissePronostics caisseId={pronosticCaisse.id} currency={currency} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
