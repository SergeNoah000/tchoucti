"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { PiggyBank, TrendingUp, Wallet, AlertTriangle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { caissesApi, type MyFinances } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { formatDate } from "@/lib/utils";

export function MyFinancesView({
  associationId,
  currency,
}: {
  associationId: string;
  currency?: string | null;
}) {
  const t = useTranslations("myFinances");
  const fmt = useFormatters(currency ?? undefined);

  const { data, isLoading } = useQuery<MyFinances>({
    queryKey: ["my-finances", associationId],
    queryFn: () => caissesApi.myFinances(associationId),
    enabled: !!associationId,
  });

  if (isLoading || !data) return <Skeleton className="h-64 w-full rounded-xl" />;

  return (
    <div className="space-y-6">
      {/* Cartes récap : une par caisse + montant investi + rendement cumulé */}
      <div className="flex flex-wrap gap-3">
        {data.cards.map((c) => (
          <SummaryBox key={c.caisse_id} label={c.caisse_name} value={fmt.currency(c.my_apport)} />
        ))}
        <SummaryBox icon={Wallet} label={t("totalInvested")} value={fmt.currency(data.total_invested)} accent />
        <SummaryBox icon={TrendingUp} label={t("totalRendement")} value={fmt.currency(data.total_rendement)} accent="emerald" />
      </div>

      {/* Mes Versements */}
      <section className="space-y-2">
        <h2 className="text-base font-semibold">{t("versementsTitle")}</h2>
        {data.versements.length === 0 ? (
          <EmptyState icon={PiggyBank} title={t("noVersements")} description={t("noVersementsDesc")} />
        ) : (
          <Card>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t("colCaisse")}</th>
                    <th className="px-4 py-3 font-medium">{t("colDate")}</th>
                    <th className="px-4 py-3 text-right font-medium">{t("colAmount")}</th>
                    <th className="px-4 py-3 text-right font-medium">{t("colRendement")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.versements.map((v, i) => (
                    <tr key={i}>
                      <td className="px-4 py-3 font-medium">{v.caisse_name}</td>
                      <td className="px-4 py-3 text-muted-foreground">{formatDate(v.date)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmt.currency(v.amount)}</td>
                      <td className="px-4 py-3 text-right tabular-nums font-medium text-emerald-700 dark:text-emerald-400">
                        {fmt.currency(v.rendement)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </section>

      {/* Notifications */}
      {data.notifications.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-base font-semibold">{t("notificationsTitle")}</h2>
          <div className="space-y-2">
            {data.notifications.map((n, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/15 dark:text-amber-300"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{n.message}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SummaryBox({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon?: typeof Wallet;
  label: string;
  value: string;
  accent?: boolean | "emerald";
}) {
  const cls =
    accent === "emerald"
      ? "text-emerald-600 dark:text-emerald-400"
      : accent
        ? "text-primary"
        : "text-muted-foreground";
  return (
    <div className="min-w-[150px] flex-1 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {Icon && <Icon className={`h-3.5 w-3.5 ${cls}`} />}
        <span className="truncate">{label}</span>
      </div>
      <p className={`mt-1 text-xl font-bold tabular-nums ${accent ? cls : ""}`}>{value}</p>
    </div>
  );
}
