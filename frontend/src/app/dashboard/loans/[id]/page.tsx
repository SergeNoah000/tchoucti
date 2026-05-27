"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Banknote,
  Coins,
  Wallet,
  CalendarClock,
  Loader2,
  AlertCircle,
  Check,
  X,
  HandCoins,
  Send,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, loansApi } from "@/lib/api";
import type { Association, LoanDetail, LoanInstallmentStatus, LoanStatus } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_VARIANT: Record<LoanStatus, "warning" | "info" | "success" | "destructive" | "secondary"> = {
  requested: "warning",
  approved: "info",
  disbursed: "info",
  repaying: "info",
  paid: "success",
  rejected: "destructive",
  defaulted: "destructive",
  cancelled: "secondary",
};

const INST_PILL: Record<LoanInstallmentStatus, string> = {
  pending: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  partially_paid: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  late: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  waived: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function LoanDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("loan");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canManage = canDoBureauActions(user);

  const loanKey = ["loan", id];
  const { data: loan, isLoading } = useQuery<LoanDetail>({
    queryKey: loanKey,
    queryFn: () => loansApi.get(id),
    enabled: !!id,
  });

  // Fetch the loan's association just to drive the formatter currency.
  const { data: association } = useQuery<Association>({
    queryKey: ["association", loan?.association_id],
    queryFn: () => associationsApi.get(loan!.association_id),
    enabled: !!loan?.association_id,
  });
  const fmt = useFormatters(association?.currency);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: loanKey });
    queryClient.invalidateQueries({ queryKey: ["loans"] });
    queryClient.invalidateQueries({ queryKey: ["treasury"] });
    queryClient.invalidateQueries({ queryKey: ["movements"] });
  };

  const approveMutation = useMutation({
    mutationFn: () => loansApi.approve(id),
    onSuccess: () => { toast.success(t("approvedToast")); refresh(); },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
  });
  const disburseMutation = useMutation({
    mutationFn: () => loansApi.disburse(id),
    onSuccess: () => { toast.success(t("disbursedToast")); refresh(); },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
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

  if (!loan) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <AlertCircle className="mb-4 h-12 w-12 text-muted-foreground" />
        <p className="text-lg font-semibold">{t("notFound")}</p>
        <Button asChild variant="ghost" className="mt-4">
          <Link href="/dashboard/loans">← {t("backToList")}</Link>
        </Button>
      </div>
    );
  }

  const canRepay = loan.status === "repaying" || loan.status === "disbursed";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/loans">
          <ArrowLeft className="h-4 w-4" />
          {t("backToList")}
        </Link>
      </Button>

      <PageHeader
        title={loan.borrower_name ?? loan.reference}
        description={`${loan.reference} · ${t("requestedOn", { date: fmt.date(loan.requested_on) })}`}
        actions={
          canManage ? (
            <div className="flex items-center gap-2">
              {loan.status === "requested" && (
                <>
                  <ConfirmAction
                    trigger={
                      <Button className="gap-1.5">
                        <Check className="h-4 w-4" />
                        {t("approve")}
                      </Button>
                    }
                    title={t("approveConfirmTitle")}
                    description={t("approveConfirmDesc")}
                    actionLabel={t("approve")}
                    onConfirm={() => approveMutation.mutate()}
                  />
                  <RejectDialog loanId={loan.id} onDone={refresh} />
                </>
              )}
              {loan.status === "approved" && (
                <ConfirmAction
                  trigger={
                    <Button className="gap-1.5">
                      <Send className="h-4 w-4" />
                      {t("disburse")}
                    </Button>
                  }
                  title={t("disburseConfirmTitle")}
                  description={t("disburseConfirmDesc")}
                  actionLabel={t("disburse")}
                  onConfirm={() => disburseMutation.mutate()}
                />
              )}
              {canRepay && (
                <RepayDialog
                  loanId={loan.id}
                  max={loan.remaining_balance}
                  currency={association?.currency}
                  onDone={refresh}
                />
              )}
            </div>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={STATUS_VARIANT[loan.status]}>{t(`status_${loan.status}`)}</Badge>
        <Badge variant="outline">{loan.interest_rate_pct}% / {tCommon("date").toLowerCase()}</Badge>
        {loan.purpose && <span className="text-sm text-muted-foreground">{loan.purpose}</span>}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={Banknote} label={t("principal")} value={fmt.currency(loan.principal)} />
        <StatCard icon={Coins} label={t("totalDue")} value={fmt.currency(loan.total_due)} />
        <StatCard icon={Wallet} label={t("remaining")} value={fmt.currency(loan.remaining_balance)} />
        <StatCard icon={CalendarClock} label={t("installment")} value={fmt.currency(loan.installment_amount)} />
      </div>

      {/* Schedule */}
      <Card>
        <CardHeader>
          <CardTitle>{t("schedule")}</CardTitle>
        </CardHeader>
        <CardContent>
          {loan.installments.length === 0 ? (
            <EmptyState icon={CalendarClock} title={t("noSchedule")} />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t("number")}</th>
                    <th className="px-3 py-2 font-medium">{t("dueOn")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("capital")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("interestCol")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("expected")}</th>
                    <th className="px-3 py-2 font-medium">{tCommon("status")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {loan.installments.map((i) => (
                    <tr key={i.id}>
                      <td className="px-3 py-2 font-medium">{i.number}</td>
                      <td className="px-3 py-2 text-muted-foreground">{fmt.date(i.due_on)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmt.currency(i.principal_part)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmt.currency(i.interest_part)}</td>
                      <td className="px-3 py-2 text-right font-medium tabular-nums">
                        {fmt.currency(i.expected_amount)}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            INST_PILL[i.status],
                          )}
                        >
                          {t(`inst_${i.status}`)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Repayments */}
      <Card>
        <CardHeader>
          <CardTitle>{t("repayments")}</CardTitle>
        </CardHeader>
        <CardContent>
          {loan.repayments.length === 0 ? (
            <EmptyState icon={HandCoins} title={t("noRepayments")} />
          ) : (
            <div className="divide-y divide-border">
              {loan.repayments.map((r) => (
                <div key={r.id} className="flex items-center justify-between py-2.5 text-sm">
                  <div>
                    <p className="font-medium">{fmt.date(r.paid_on)}</p>
                    <p className="text-xs text-muted-foreground">
                      {t("capital")} {fmt.currency(r.principal)} · {t("interestCol")}{" "}
                      {fmt.currency(r.interest)}
                    </p>
                  </div>
                  <span className="font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                    +{fmt.currency(r.total_paid)}
                  </span>
                </div>
              ))}
            </div>
          )}
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
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="truncate text-base font-bold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ConfirmAction({
  trigger,
  title,
  description,
  actionLabel,
  onConfirm,
}: {
  trigger: React.ReactNode;
  title: string;
  description: string;
  actionLabel: string;
  onConfirm: () => void;
}) {
  const tCommon = useTranslations("common");
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{actionLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function RejectDialog({ loanId, onDone }: { loanId: string; onDone: () => void }) {
  const t = useTranslations("loan");
  const tCommon = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const rejectMutation = useMutation({
    mutationFn: () => loansApi.reject(loanId, reason.trim()),
    onSuccess: () => {
      toast.success(t("rejectedToast"));
      setOpen(false);
      setReason("");
      onDone();
    },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="gap-1.5 text-destructive">
          <X className="h-4 w-4" />
          {t("reject")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("rejectTitle")}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (reason.trim().length >= 2) rejectMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="lr-reason">{t("rejectReason")}</Label>
            <Input
              id="lr-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              minLength={2}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={rejectMutation.isPending || reason.trim().length < 2}
            >
              {t("reject")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RepayDialog({
  loanId,
  max,
  currency,
  onDone,
}: {
  loanId: string;
  max: number;
  currency?: string;
  onDone: () => void;
}) {
  const t = useTranslations("loan");
  const tCommon = useTranslations("common");
  const fmt = useFormatters(currency);
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  const repayMutation = useMutation({
    mutationFn: () => loansApi.repay(loanId, parseInt(amount, 10)),
    onSuccess: () => {
      toast.success(t("repaidToast"));
      setOpen(false);
      setAmount("");
      setError("");
      onDone();
    },
    onError: (err) => setError(extractError(err) ?? t("actionError")),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) {
          setAmount("");
          setError("");
        }
      }}
    >
      <DialogTrigger asChild>
        <Button className="gap-1.5">
          <HandCoins className="h-4 w-4" />
          {t("repay")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("repayTitle")}</DialogTitle>
          <DialogDescription>{t("repayDesc")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const a = parseInt(amount, 10);
            if (Number.isNaN(a) || a <= 0 || a > max) {
              setError(`${t("remaining")}: ${fmt.currency(max)}`);
              return;
            }
            setError("");
            repayMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="rp-amount">
              {t("repayAmount")} — {t("remaining")}: {fmt.currency(max)}
            </Label>
            <Input
              id="rp-amount"
              type="number"
              inputMode="numeric"
              min={1}
              max={max}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>
          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" disabled={repayMutation.isPending} className="gap-2">
              {repayMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("repay")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
