"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, Banknote, PiggyBank, Percent, Info } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { caissesApi, type CaisseProjection } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CaissePronostics({
  caisseId,
  currency,
}: {
  caisseId: string;
  currency?: string | null;
}) {
  const t = useTranslations("caissePronostics");
  const fmt = useFormatters(currency ?? undefined);

  const { data, isLoading } = useQuery<CaisseProjection>({
    queryKey: ["caisse", caisseId, "projections"],
    queryFn: () => caissesApi.projections(caisseId),
    enabled: !!caisseId,
  });

  if (isLoading || !data) return <Skeleton className="h-48 w-full rounded-xl" />;

  const kept = data.interest_distribution === "kept";

  return (
    <div className="space-y-4">
      {/* Bandeau : mode de distribution des intérêts */}
      <div
        className={cn(
          "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
          kept
            ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/15 dark:text-amber-300"
            : "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-900/15 dark:text-emerald-300",
        )}
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{kept ? t("modeKept") : t("modeShared")}</span>
      </div>

      {/* Totaux */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Banknote} label={t("activePrincipal")} value={fmt.currency(data.total_principal_active)} />
        <StatCard icon={TrendingUp} label={t("upcomingInterest")} value={fmt.currency(data.total_upcoming_interest)} />
        <StatCard icon={PiggyBank} label={t("totalApport")} value={fmt.currency(data.total_apport)} />
      </div>

      {/* Ma part projetée (vue locale) */}
      {data.my && (
        <Card className="border-primary/30">
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4">
            <div className="flex items-center gap-2 font-medium">
              <Percent className="h-4 w-4 text-primary" />
              {t("myShare")}
            </div>
            <span className="text-sm text-muted-foreground">
              {t("myApport")}: <span className="font-medium text-foreground">{fmt.currency(data.my.apport_cum)}</span> ({data.my.weight_pct}%)
            </span>
            <span className="ml-auto text-sm">
              {t("myProjected")}:{" "}
              <span className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">
                {fmt.currency(data.my.projected_interest)}
              </span>
            </span>
          </CardContent>
        </Card>
      )}

      {/* Prêts financés par la caisse : rentabilité + intérêts à venir */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t("loansTitle")}</h3>
        {data.loans.length === 0 ? (
          <EmptyState icon={Banknote} title={t("noLoans")} description={t("noLoansDesc")} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">{t("colLoan")}</th>
                  <th className="py-2 pr-3 font-medium">{t("colBorrower")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colPrincipal")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colInterest")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colRentability")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colUpcoming")}</th>
                  <th className="py-2 text-right font-medium">{t("colRemaining")}</th>
                </tr>
              </thead>
              <tbody>
                {data.loans.map((l) => (
                  <tr key={l.loan_id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-mono text-xs">{l.reference}</td>
                    <td className="py-2 pr-3">{l.borrower_name || "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmt.currency(l.principal)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmt.currency(l.total_interest)}</td>
                    <td className="py-2 pr-3 text-right">
                      <Badge variant="secondary" className="tabular-nums">{l.rentability_pct}%</Badge>
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                      {fmt.currency(l.upcoming_interest)}
                    </td>
                    <td className="py-2 text-right tabular-nums">{l.remaining_installments}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Vue globale : répartition projetée par contributeur (admin) */}
      {data.is_admin_view && data.contributors.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t("contributorsTitle")}</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">{t("colMember")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colApport")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colWeight")}</th>
                  <th className="py-2 text-right font-medium">{t("colProjected")}</th>
                </tr>
              </thead>
              <tbody>
                {data.contributors.map((c) => (
                  <tr key={c.membership_id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{c.member_name || "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmt.currency(c.apport_cum)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{c.weight_pct}%</td>
                    <td className="py-2 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                      {fmt.currency(c.projected_interest)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Banknote;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className="h-6 w-6 shrink-0 text-primary" />
        <div className="min-w-0">
          <p className="truncate text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
