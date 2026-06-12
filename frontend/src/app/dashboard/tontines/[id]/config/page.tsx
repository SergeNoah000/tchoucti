"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, AlertCircle, Repeat } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { DraftCycleManager } from "@/components/tontines/draft-cycle-manager";
import { associationsApi, tontinesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import type { Association, TontineDetail } from "@/lib/types";

export default function TontineConfigPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("tontine");
  const { user } = useAuthStore();
  const canConfigure = canConfigureAssociation(user);

  const { data: tontine, isLoading } = useQuery<TontineDetail>({
    queryKey: ["tontine", id],
    queryFn: () => tontinesApi.get(id),
    enabled: !!id,
  });

  const { data: association } = useQuery<Association>({
    queryKey: ["association", tontine?.association_id],
    queryFn: () => associationsApi.get(tontine!.association_id),
    enabled: !!tontine?.association_id,
  });

  if (!canConfigure) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("notAdmin")}</p>
      </div>
    );
  }

  if (isLoading || !tontine) {
    if (!isLoading) {
      return (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <AlertCircle className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-semibold">{t("notFound")}</p>
          <Button asChild variant="ghost" className="mt-4">
            <Link href="/dashboard/tontines">← {t("backToList")}</Link>
          </Button>
        </div>
      );
    }
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  const current = tontine.current_cycle ?? null;
  const started = current?.status !== "draft"; // séances déjà démarrées → pas d'ajout

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href={`/dashboard/tontines/${id}`}>
          <ArrowLeft className="h-4 w-4" />
          {t("backToDetail")}
        </Link>
      </Button>

      <PageHeader title={t("configTitle", { name: tontine.name })} description={t("configSubtitle")} />

      {current && current.status === "draft" && association ? (
        <DraftCycleManager tontineId={id} cycle={current} associationId={association.id} />
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Repeat className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">{started ? t("cycleStartedTitle") : t("noDraftCycle")}</p>
            <p className="max-w-md text-sm text-muted-foreground">
              {started ? t("cycleStartedHint") : t("noDraftCycleHint")}
            </p>
            <Button asChild variant="outline" className="mt-2">
              <Link href={`/dashboard/tontines/${id}`}>{t("backToDetail")}</Link>
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
