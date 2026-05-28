"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Repeat, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { CreateCycleDialog } from "@/components/tontines/create-cycle-dialog";
import { associationsApi, tontinesApi } from "@/lib/api";
import type { Association, TontineCycle, TontineCycleStatus } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";

const STATUS_VARIANT: Record<TontineCycleStatus, "success" | "secondary" | "info" | "destructive"> = {
  active: "success",
  draft: "secondary",
  completed: "info",
  cancelled: "destructive",
};

export default function TontinesPage() {
  const t = useTranslations("tontine");
  const { user } = useAuthStore();
  const canManage = canConfigureAssociation(user);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const associationId = association?.id;
  const fmt = useFormatters(association?.currency);

  const { data: cycles = [], isLoading } = useQuery<TontineCycle[]>({
    queryKey: ["tontines", associationId],
    queryFn: () => tontinesApi.list(associationId!),
    enabled: !!associationId,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canManage && associationId ? (
            <CreateCycleDialog association={association!} />
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : cycles.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Repeat}
              title={t("empty")}
              description={canManage ? t("emptyDesc") : undefined}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {cycles.map((c) => (
            <Link
              key={c.id}
              href={`/dashboard/tontines/${c.id}`}
              className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Repeat className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate font-semibold leading-tight">{c.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {t("cycleProgress", { current: c.current_round_number, total: c.rounds_count })}
                    {" · "}
                    {t("pot")}: {fmt.currency(c.round_amount * c.rounds_count)}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={STATUS_VARIANT[c.status]}>{t(`status${capitalize(c.status)}`)}</Badge>
                <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
