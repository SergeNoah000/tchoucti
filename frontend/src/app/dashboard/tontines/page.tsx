"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Repeat, Settings } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { CreateTontineDialog } from "@/components/tontines/create-cycle-dialog";
import { associationsApi, tontinesApi } from "@/lib/api";
import type { Association, Tontine, TontineCycleStatus } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";

const STATUS_VARIANT: Record<TontineCycleStatus, "success" | "secondary" | "info" | "destructive"> = {
  active: "success",
  draft: "secondary",
  completed: "info",
  cancelled: "destructive",
};

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

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

  const { data: tontines = [], isLoading } = useQuery<Tontine[]>({
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
          canManage && associationId ? <CreateTontineDialog association={association!} /> : undefined
        }
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : tontines.length === 0 ? (
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
          {tontines.map((tt) => {
            const cc = tt.current_cycle;
            return (
              <div
                key={tt.id}
                className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
              >
                <Link href={`/dashboard/tontines/${tt.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Repeat className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold leading-tight">{tt.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {t("cyclesCount", { count: tt.cycles_count })}
                      {cc && (
                        <>
                          {" · "}
                          {t("cycleProgress", {
                            current: cc.current_round_number,
                            total: cc.rounds_count,
                          })}
                          {" · "}
                          {t("roundAmount")}: {fmt.currency(tt.round_amount)}
                        </>
                      )}
                    </p>
                  </div>
                </Link>
                <div className="flex shrink-0 items-center gap-2">
                  {cc && (
                    <Badge variant={STATUS_VARIANT[cc.status]}>
                      {t(`status${capitalize(cc.status)}`)}
                    </Badge>
                  )}
                  <Link
                    href={`/dashboard/tontines/${tt.id}`}
                    title={t("configure")}
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    <Settings className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
