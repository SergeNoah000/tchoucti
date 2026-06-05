"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, PiggyBank } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, caissesApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import type { Association, MyShareItem } from "@/lib/types";

export default function MySharePage() {
  const t = useTranslations("myShare");
  const tCommon = useTranslations("common");

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const { data: items = [], isLoading } = useQuery<MyShareItem[]>({
    queryKey: ["my-shares", association?.id],
    queryFn: () => caissesApi.myShares(association!.id),
    enabled: !!association,
  });

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard">
          <ArrowLeft className="h-4 w-4" />
          {tCommon("back")}
        </Link>
      </Button>

      <PageHeader title={t("title")} description={t("subtitle")} />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={PiggyBank}
              title={t("emptyTitle")}
              description={t("emptyDesc")}
            />
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {items.map((it) => {
            const pct = it.total_apport > 0
              ? Math.round((it.apport_cum / it.total_apport) * 1000) / 10
              : 0;
            return (
              <li key={it.caisse_id}>
                <Link
                  href={`/dashboard/my-share/${it.caisse_id}`}
                  className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <PiggyBank className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-semibold leading-tight">{it.caisse_name}</p>
                        {it.interest_distribution === "shared_pro_rata" && (
                          <Badge variant="secondary" className="text-[10px]">
                            {t("badge")}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {t("apport")}: <span className="font-medium tabular-nums">{fmt.currency(it.apport_cum)}</span>
                        {" · "}
                        {t("interest")}: <span className="font-medium tabular-nums text-emerald-700 dark:text-emerald-400">{fmt.currency(it.interest_cum)}</span>
                        {" · "}
                        {t("share")}: <span className="font-medium tabular-nums">{pct}%</span>
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
