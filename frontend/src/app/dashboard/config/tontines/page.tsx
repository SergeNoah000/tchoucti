"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Repeat } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { ConfigPreview } from "@/components/onboarding/help-field";
import { OnboardingBanner } from "@/components/onboarding/onboarding-banner";
import { CreateTontineDialog } from "@/components/tontines/create-cycle-dialog";

import { associationsApi, tontinesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type { Association, Tontine, TontineCycleStatus } from "@/lib/types";

const STATUS_VARIANT: Record<TontineCycleStatus, "success" | "secondary" | "info" | "destructive"> = {
  active: "success",
  draft: "secondary",
  completed: "info",
  cancelled: "destructive",
};

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ConfigTontinesPage() {
  const t = useTranslations("configTontines");
  const tCommon = useTranslations("common");
  const tTontine = useTranslations("tontine");
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const { data: tontines = [], isLoading } = useQuery<Tontine[]>({
    queryKey: ["tontines", association?.id],
    queryFn: () => tontinesApi.list(association!.id),
    enabled: !!association?.id,
  });

  if (!canConfigureAssociation(user)) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("notAdmin")}</p>
      </div>
    );
  }
  if (!association) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <OnboardingBanner />
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" className="gap-1.5">
              <Link href="/dashboard">
                <ArrowLeft className="h-4 w-4" />
                {tCommon("back")}
              </Link>
            </Button>
            <CreateTontineDialog association={association} />
          </div>
        }
      />

      <ConfigPreview intent="info">{t("intro")}</ConfigPreview>

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : tontines.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <Repeat className="h-12 w-12 text-muted-foreground" />
            <p className="font-medium">{t("empty")}</p>
            <p className="text-sm text-muted-foreground">{t("emptyDesc")}</p>
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {tontines.map((tt) => (
            <li key={tt.id}>
              <Link
                href={`/dashboard/tontines/${tt.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-4 hover:border-primary/40"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Repeat className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold">{tt.name}</p>
                      {tt.current_cycle && (
                        <Badge variant={STATUS_VARIANT[tt.current_cycle.status]} className="text-[10px]">
                          {tTontine(`status${cap(tt.current_cycle.status)}`)}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t("cyclesLabel", { count: tt.cycles_count })} · {tTontine("roundAmount")}:{" "}
                      {fmt.currency(tt.round_amount)} · {tTontine(`freq_${tt.frequency}`)}
                    </p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
