"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Repeat,
  Coins,
  CircleDollarSign,
  Loader2,
  AlertCircle,
  HandCoins,
  Crown,
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
import type { Association, TontineCycleDetail, TontineCycleStatus, TontineRoundStatus } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";
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

const CYCLE_LABEL: Record<TontineCycleStatus, string> = {
  draft: "statusDraft",
  active: "statusActive",
  completed: "statusCompleted",
  cancelled: "statusCancelled",
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function TontineCycleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canManage = detectRole(user) !== "member";

  const cycleKey = ["tontine", id];

  const { data: cycle, isLoading } = useQuery<TontineCycleDetail>({
    queryKey: cycleKey,
    queryFn: () => tontinesApi.get(id),
    enabled: !!id,
  });

  // Pick up the cycle's association currency so amounts render correctly.
  const { data: association } = useQuery<Association>({
    queryKey: ["association", cycle?.association_id],
    queryFn: () => associationsApi.get(cycle!.association_id),
    enabled: !!cycle?.association_id,
  });
  const fmt = useFormatters(association?.currency);

  const refresh = () => queryClient.invalidateQueries({ queryKey: cycleKey });

  const payoutMutation = useMutation({
    mutationFn: (roundId: string) => tontinesApi.payout(id, roundId),
    onSuccess: () => {
      toast.success(t("payoutDone"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  const cancelMutation = useMutation({
    mutationFn: () => tontinesApi.cancel(id),
    onSuccess: () => {
      toast.success(t("cancelled"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("noData")),
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

  if (!cycle) {
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

  const isActive = cycle.status === "active";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/tontines">
          <ArrowLeft className="h-4 w-4" />
          {t("backToList")}
        </Link>
      </Button>

      <PageHeader
        title={cycle.name}
        description={t("cycleProgress", {
          current: cycle.current_round_number,
          total: cycle.rounds_count,
        })}
        actions={
          canManage && isActive ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" className="gap-2 border-destructive/40 text-destructive">
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
                    onClick={() => cancelMutation.mutate()}
                  >
                    {t("cancelCycle")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={CYCLE_VARIANT[cycle.status]}>{t(CYCLE_LABEL[cycle.status])}</Badge>
        <Badge variant="outline">{t("startDate")}: {fmt.date(cycle.start_date)}</Badge>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Coins} label={t("pot")} value={fmt.currency(cycle.pot_amount)} />
        <StatCard icon={CircleDollarSign} label={t("roundAmount")} value={fmt.currency(cycle.round_amount)} />
        <StatCard icon={Repeat} label={t("roundsCount")} value={String(cycle.rounds_count)} />
      </div>

      {/* Rounds */}
      <Card>
        <CardContent className="p-0">
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
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-0.5 text-xs font-medium",
                      ROUND_PILL[r.status]
                    )}
                  >
                    {t(ROUND_LABEL[r.status])}
                  </span>
                  {canManage && isActive && r.status === "collecting" && (
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
                          <AlertDialogAction
                            onClick={() => payoutMutation.mutate(r.id)}
                            disabled={payoutMutation.isPending}
                          >
                            {payoutMutation.isPending && (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
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
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="truncate text-lg font-bold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
