"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  HandCoins,
  Crown,
  Plus,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
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
import { associationsApi, tontinesApi } from "@/lib/api";
import type {
  Association,
  TontineCycleDetail,
  TontineCycleStatus,
  TontineDetail,
  TontineRoundStatus,
} from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation, canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

const CYCLE_VARIANT: Record<TontineCycleStatus, "success" | "secondary" | "info" | "destructive"> = {
  active: "success",
  draft: "secondary",
  completed: "info",
  cancelled: "destructive",
};

const ROUND_PILL: Record<TontineRoundStatus, string> = {
  pending: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  collecting: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  paid_out: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  skipped: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};

const ROUND_LABEL: Record<TontineRoundStatus, string> = {
  pending: "roundStatusPending",
  collecting: "roundStatusCollecting",
  paid_out: "roundStatusPaidOut",
  skipped: "roundStatusSkipped",
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function TontineDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canConfigure = canConfigureAssociation(user);
  const canPayout = canDoBureauActions(user);

  const key = ["tontine", id];

  const { data: tontine, isLoading } = useQuery<TontineDetail>({
    queryKey: key,
    queryFn: () => tontinesApi.get(id),
    enabled: !!id,
  });

  const { data: association } = useQuery<Association>({
    queryKey: ["association", tontine?.association_id],
    queryFn: () => associationsApi.get(tontine!.association_id),
    enabled: !!tontine?.association_id,
  });
  const fmt = useFormatters(association?.currency);

  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const payoutMutation = useMutation({
    mutationFn: ({ cycleId, roundId }: { cycleId: string; roundId: string }) =>
      tontinesApi.payout(cycleId, roundId),
    onSuccess: () => {
      toast.success(t("payoutDone"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  const cancelMutation = useMutation({
    mutationFn: (cycleId: string) => tontinesApi.cancelCycle(cycleId),
    onSuccess: () => {
      toast.success(t("cancelled"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  const nextCycleMutation = useMutation({
    mutationFn: () => tontinesApi.createNextCycle(id),
    onSuccess: () => {
      toast.success(t("nextCycleCreated"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (!tontine) {
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

  const current = tontine.current_cycle ?? null;
  const currentCompleted = current?.status === "completed";
  const pastCycles = tontine.cycles.filter((c) => c.id !== current?.id);

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/tontines">
          <ArrowLeft className="h-4 w-4" />
          {t("backToList")}
        </Link>
      </Button>

      <PageHeader
        title={tontine.name}
        description={t("cyclesCount", { count: tontine.cycles_count })}
        actions={
          canConfigure && currentCompleted ? (
            <Button onClick={() => nextCycleMutation.mutate()} disabled={nextCycleMutation.isPending} className="gap-2">
              {nextCycleMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t("nextCycle")}
            </Button>
          ) : undefined
        }
      />

      {/* Config résumé */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{t("roundAmount")}: {fmt.currency(tontine.round_amount)}</Badge>
        <Badge variant="outline">{t(`freq_${tontine.frequency}`)}</Badge>
        <Badge variant="outline">{t("beneficiariesPerRound")}: {tontine.beneficiaries_per_round}</Badge>
        <Badge variant="outline">{t(`method_${tontine.selection_method}`)}</Badge>
        {!tontine.beneficiary_pays && <Badge variant="outline">{t("beneficiaryExempt")}</Badge>}
      </div>

      {current ? (
        <CycleCard
          cycle={current}
          isCurrent
          canConfigure={canConfigure}
          canPayout={canPayout}
          onPayout={(roundId) => payoutMutation.mutate({ cycleId: current.id, roundId })}
          payoutPending={payoutMutation.isPending}
          onCancel={() => cancelMutation.mutate(current.id)}
          fmt={fmt}
          t={t}
          tCommon={tCommon}
        />
      ) : (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">{t("noCycle")}</CardContent></Card>
      )}

      {/* Cycles passés */}
      {pastCycles.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("pastCycles")}
          </h2>
          {pastCycles.map((c) => (
            <CycleCard
              key={c.id}
              cycle={c}
              isCurrent={false}
              canConfigure={false}
              canPayout={false}
              onPayout={() => {}}
              payoutPending={false}
              onCancel={() => {}}
              fmt={fmt}
              t={t}
              tCommon={tCommon}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CycleCard({
  cycle,
  isCurrent,
  canConfigure,
  canPayout,
  onPayout,
  payoutPending,
  onCancel,
  fmt,
  t,
  tCommon,
}: {
  cycle: TontineCycleDetail;
  isCurrent: boolean;
  canConfigure: boolean;
  canPayout: boolean;
  onPayout: (roundId: string) => void;
  payoutPending: boolean;
  onCancel: () => void;
  fmt: ReturnType<typeof useFormatters>;
  t: ReturnType<typeof useTranslations>;
  tCommon: ReturnType<typeof useTranslations>;
}) {
  const isActive = cycle.status === "active";
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{t("cycleN", { n: cycle.cycle_number })}</span>
            <Badge variant={CYCLE_VARIANT[cycle.status]}>{t(`status${cap(cycle.status)}`)}</Badge>
            <span className="text-xs text-muted-foreground">
              {t("pot")}: {fmt.currency(cycle.pot_amount)}
            </span>
          </div>
          {canConfigure && isActive && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5 border-destructive/40 text-destructive">
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
                    onClick={onCancel}
                  >
                    {t("cancelCycle")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>

        <div className="divide-y divide-border">
          {cycle.rounds.map((r) => (
            <div key={r.id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="flex min-w-0 flex-1 items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-sm font-bold text-primary">
                  {r.round_number}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {r.status === "collecting" && <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />}
                    <p className="text-sm font-medium">
                      {r.beneficiaries.length > 1
                        ? t("sharedRound", { count: r.beneficiaries.length })
                        : (r.beneficiaries[0]?.name ?? "—")}
                    </p>
                  </div>
                  {r.beneficiaries.length > 1 && (
                    <div className="mt-1 space-y-0.5">
                      {r.beneficiaries.map((b) => (
                        <p key={b.membership_id} className="flex justify-between gap-2 text-xs">
                          <span className="truncate text-muted-foreground">• {b.name ?? "—"}</span>
                          <span className="shrink-0 tabular-nums">{fmt.currency(b.share_amount)}</span>
                        </p>
                      ))}
                    </div>
                  )}
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {r.paid_out_date
                      ? `${t("paidOutDate")} ${fmt.date(r.paid_out_date)}`
                      : r.scheduled_date
                        ? `${t("scheduledDate")} ${fmt.date(r.scheduled_date)}`
                        : t("beneficiary")}
                    {" · "}
                    {t("pot")}: {fmt.currency(r.expected_amount)}
                  </p>
                  {r.meeting_title && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">🗓 {r.meeting_title}</p>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", ROUND_PILL[r.status])}>
                  {t(ROUND_LABEL[r.status])}
                </span>
                {canPayout && isCurrent && isActive && r.status === "collecting" && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="sm" className="gap-1.5">
                        <HandCoins className="h-3.5 w-3.5" />
                        {t("payout")}
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>{t("payoutConfirmTitle")}</AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("payoutConfirmDesc", { round: r.round_number })}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                        <AlertDialogAction onClick={() => onPayout(r.id)} disabled={payoutPending}>
                          {payoutPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {t("payout")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
