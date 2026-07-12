"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { PiggyBank, ChevronRight, Wallet } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { MyFinancesView } from "@/components/caisses/my-finances";
import { associationsApi, caissesApi, type MyFinances } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import type { Association } from "@/lib/types";

export default function CaissesPage() {
  const t = useTranslations("caissesView");

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const { data: finances, isLoading } = useQuery<MyFinances>({
    queryKey: ["my-finances", association?.id],
    queryFn: () => caissesApi.myFinances(association!.id),
    enabled: !!association?.id,
  });
  // Caisses prêtables (source de prêt / ayant des prêts).
  const loanable = (finances?.cards ?? []).filter((c) => c.is_loanable);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      <Tabs defaultValue="finances">
        <TabsList>
          <TabsTrigger value="finances" className="gap-1.5">
            <Wallet className="h-3.5 w-3.5" />
            {t("tabMyFinances")}
          </TabsTrigger>
          <TabsTrigger value="caisses" className="gap-1.5">
            <PiggyBank className="h-3.5 w-3.5" />
            {t("tabCaisses")}
          </TabsTrigger>
        </TabsList>

        {/* Onglet principal : Mes Finances */}
        <TabsContent value="finances" className="mt-4">
          {association ? (
            <MyFinancesView associationId={association.id} currency={association.currency} />
          ) : (
            <Skeleton className="h-64 w-full rounded-xl" />
          )}
        </TabsContent>

        {/* Onglet : caisses prêtables (montant investi + attendu à la cassation) */}
        <TabsContent value="caisses" className="mt-4">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
            </div>
          ) : loanable.length === 0 ? (
            <Card>
              <CardContent className="p-0">
                <EmptyState icon={PiggyBank} title={t("emptyTitle")} description={t("emptyDesc")} />
              </CardContent>
            </Card>
          ) : (
            <ul className="space-y-2">
              {loanable.map((c) => (
                <li key={c.caisse_id}>
                  <Link
                    href={`/dashboard/caisses/${c.caisse_id}`}
                    className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <PiggyBank className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-semibold leading-tight">{c.caisse_name}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {t("invested")}: <span className="font-medium tabular-nums text-foreground">{fmt.currency(c.my_apport)}</span>
                          {" · "}
                          {t("atCassation")}: <span className="font-medium tabular-nums text-emerald-700 dark:text-emerald-400">{fmt.currency(c.expected_at_cassation)}</span>
                        </p>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
