"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { PiggyBank, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, caissesApi } from "@/lib/api";
import type { Association, Caisse } from "@/lib/types";

export default function CaissesPage() {
  const t = useTranslations("caissesView");

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  const { data: caisses = [], isLoading } = useQuery<Caisse[]>({
    queryKey: ["caisses", association?.id],
    queryFn: () => caissesApi.list(association!.id),
    enabled: !!association?.id,
  });
  const visible = caisses.filter((c) => !c.is_system);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
        </div>
      ) : visible.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={PiggyBank} title={t("emptyTitle")} description={t("emptyDesc")} />
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {visible.map((c) => (
            <li key={c.id}>
              <Link
                href={`/dashboard/caisses/${c.id}`}
                className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <PiggyBank className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold leading-tight">{c.name}</p>
                      <Badge variant="outline" className="text-[10px]">{t(`cat_${c.category}`)}</Badge>
                      {c.interest_distribution === "shared_pro_rata" && (
                        <Badge variant="secondary" className="text-[10px]">{t("sharesInterest")}</Badge>
                      )}
                    </div>
                    {c.description && (
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{c.description}</p>
                    )}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
