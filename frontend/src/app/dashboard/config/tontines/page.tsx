"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronRight,
  Loader2,
  Repeat,
  ShieldOff,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { PageHeader } from "@/components/common/page-header";
import { ConfigPreview } from "@/components/onboarding/help-field";
import { OnboardingBanner } from "@/components/onboarding/onboarding-banner";

import { associationsApi, tontinesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type {
  Association,
  TontineCycle,
  TontineCycleStatus,
} from "@/lib/types";

const STATUS_VARIANT: Record<
  TontineCycleStatus,
  "success" | "secondary" | "info" | "destructive"
> = {
  active: "success",
  draft: "secondary",
  completed: "info",
  cancelled: "destructive",
};

export default function ConfigTontinesPage() {
  const t = useTranslations("configTontines");
  const tCommon = useTranslations("common");
  const tTontine = useTranslations("tontine");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);

  const { data: cycles = [], isLoading } = useQuery<TontineCycle[]>({
    queryKey: ["tontines", association?.id],
    queryFn: () => tontinesApi.list(association!.id),
    enabled: !!association?.id,
  });

  const cancelMutation = useMutation({
    mutationFn: (cycleId: string) => tontinesApi.cancel(cycleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tontines", association?.id] });
      toast.success(t("cancelled"));
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? tCommon("error"));
    },
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

  const active = cycles.filter((c) => c.status === "active");
  const completed = cycles.filter((c) => c.status === "completed");
  const cancelled = cycles.filter((c) => c.status === "cancelled");

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
            <Button asChild>
              <Link href="/dashboard/tontines" className="gap-1.5">
                <Repeat className="h-4 w-4" />
                {t("openCreate")}
              </Link>
            </Button>
          </div>
        }
      />

      <ConfigPreview intent="info">{t("intro")}</ConfigPreview>

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : cycles.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <Repeat className="h-12 w-12 text-muted-foreground" />
            <p className="font-medium">{t("empty")}</p>
            <p className="text-sm text-muted-foreground">{t("emptyDesc")}</p>
            <Button asChild className="mt-2 gap-1.5">
              <Link href="/dashboard/tontines">
                <Repeat className="h-4 w-4" />
                {t("openCreate")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {active.length > 0 && (
            <Section
              title={t("groupActive", { count: active.length })}
              cycles={active}
              fmt={fmt}
              tTontine={tTontine}
              tCommon={tCommon}
              t={t}
              onCancel={(id) => cancelMutation.mutate(id)}
              cancelDisabled={cancelMutation.isPending}
            />
          )}
          {completed.length > 0 && (
            <Section
              title={t("groupCompleted", { count: completed.length })}
              cycles={completed}
              fmt={fmt}
              tTontine={tTontine}
              tCommon={tCommon}
              t={t}
            />
          )}
          {cancelled.length > 0 && (
            <Section
              title={t("groupCancelled", { count: cancelled.length })}
              cycles={cancelled}
              fmt={fmt}
              tTontine={tTontine}
              tCommon={tCommon}
              t={t}
            />
          )}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  cycles,
  fmt,
  tTontine,
  tCommon,
  t,
  onCancel,
  cancelDisabled,
}: {
  title: string;
  cycles: TontineCycle[];
  fmt: ReturnType<typeof useFormatters>;
  tTontine: ReturnType<typeof useTranslations>;
  tCommon: ReturnType<typeof useTranslations>;
  t: ReturnType<typeof useTranslations>;
  onCancel?: (id: string) => void;
  cancelDisabled?: boolean;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <ul className="space-y-2">
        {cycles.map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-4"
          >
            <Link
              href={`/dashboard/tontines/${c.id}`}
              className="flex min-w-0 flex-1 items-center gap-3 hover:underline"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Repeat className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold">{c.name}</p>
                  <Badge variant={STATUS_VARIANT[c.status]} className="text-[10px]">
                    {tTontine(`status${capitalize(c.status)}`)}
                  </Badge>
                  {!c.is_mandatory && (
                    <Badge variant="outline" className="text-[10px]">
                      {t("optional")}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {tTontine("cycleProgress", {
                    current: c.current_round_number,
                    total: c.rounds_count,
                  })}
                  {" · "}
                  {tTontine("roundAmount")}: {fmt.currency(c.round_amount)}
                  {" · "}
                  {tTontine("startDate")}: {fmt.date(c.start_date)}
                </p>
              </div>
            </Link>

            <div className="flex shrink-0 items-center gap-2">
              {onCancel && c.status === "active" && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1.5 text-destructive hover:bg-destructive/10"
                    >
                      <ShieldOff className="h-3.5 w-3.5" />
                      {t("cancelCycle")}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>{t("cancelConfirmTitle")}</AlertDialogTitle>
                      <AlertDialogDescription>{t("cancelConfirmDesc")}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                      <AlertDialogAction
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        onClick={() => onCancel(c.id)}
                        disabled={cancelDisabled}
                      >
                        {cancelDisabled && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {t("cancelCycle")}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
