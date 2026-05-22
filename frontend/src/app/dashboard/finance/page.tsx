"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Wallet,
  Plus,
  Loader2,
  ArrowDownLeft,
  ArrowUpRight,
  ArrowLeftRight,
  PiggyBank,
  Ban,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, financeApi } from "@/lib/api";
import type { Association, MovementDirection, Treasury, TreasuryMovement } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

const DIR_META: Record<MovementDirection, { icon: typeof ArrowDownLeft; cls: string; sign: string }> = {
  in: { icon: ArrowDownLeft, cls: "text-emerald-600 dark:text-emerald-400", sign: "+" },
  out: { icon: ArrowUpRight, cls: "text-destructive", sign: "−" },
  xfer: { icon: ArrowLeftRight, cls: "text-muted-foreground", sign: "" },
};

export default function FinancePage() {
  const t = useTranslations("finance");
  const { user } = useAuthStore();
  const canManage = detectRole(user) !== "member";

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const associationId = associations[0]?.id;

  const { data: treasury, isLoading } = useQuery<Treasury>({
    queryKey: ["treasury", associationId],
    queryFn: () => financeApi.treasury(associationId!),
    enabled: !!associationId,
  });

  const { data: movements = [] } = useQuery<TreasuryMovement[]>({
    queryKey: ["movements", associationId],
    queryFn: () => financeApi.movements(associationId!),
    enabled: !!associationId,
  });

  // Format amounts in the treasury's actual currency (XAF, EUR, …).
  const fmt = useFormatters(treasury?.currency);

  if (isLoading || !treasury) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={canManage ? <NewMovementDialog treasury={treasury} /> : undefined}
      />

      {/* Global balance */}
      <Card className="overflow-hidden">
        <CardContent className="flex items-center gap-4 p-6">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Wallet className="h-7 w-7" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("globalBalance")}
            </p>
            <p className="text-3xl font-bold tabular-nums">
              {fmt.currency(treasury.balance)}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Funds */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("funds")}
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {treasury.funds.map((f) => (
            <Card key={f.id}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <PiggyBank className="h-4 w-4" />
                  <span className="truncate text-sm font-medium">{f.name}</span>
                </div>
                <p className="mt-1.5 text-xl font-bold tabular-nums">{fmt.currency(f.balance)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Movements */}
      <Card>
        <CardHeader>
          <CardTitle>{t("movements")}</CardTitle>
        </CardHeader>
        <CardContent>
          {movements.length === 0 ? (
            <EmptyState
              icon={Wallet}
              title={t("emptyMovements")}
              description={t("emptyMovementsDesc")}
            />
          ) : (
            <div className="divide-y divide-border">
              {movements.map((m) => {
                const meta = DIR_META[m.direction];
                const Icon = meta.icon;
                return (
                  <div key={m.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted", meta.cls)}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className={cn("truncate text-sm font-medium", m.is_voided && "line-through opacity-60")}>
                          {m.description || tSource(t, m.source_type)}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {fmt.date(m.occurred_on)} · {t(`dir_${m.direction}`)}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {m.is_voided && <Badge variant="secondary">{t("voided")}</Badge>}
                      <span
                        className={cn(
                          "text-sm font-semibold tabular-nums",
                          m.is_voided ? "text-muted-foreground line-through" : meta.cls,
                        )}
                      >
                        {meta.sign}
                        {fmt.currency(m.amount)}
                      </span>
                      {canManage && !m.is_voided && m.source_type === "manual" && (
                        <VoidDialog movementId={m.id} associationId={associationId!} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function tSource(t: (k: string) => string, src: string): string {
  const key = `src_${src}`;
  try {
    const v = t(key);
    return v === key ? src : v;
  } catch {
    return src;
  }
}

// ── New movement dialog ─────────────────────────────────────────────────────

function NewMovementDialog({ treasury }: { treasury: Treasury }) {
  const t = useTranslations("finance");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [direction, setDirection] = useState<MovementDirection>("in");
  const [amount, setAmount] = useState("");
  const [fundId, setFundId] = useState(treasury.funds[0]?.id ?? "");
  const [toFundId, setToFundId] = useState(treasury.funds[1]?.id ?? "");
  const [date, setDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const reset = () => {
    setDirection("in");
    setAmount("");
    setFundId(treasury.funds[0]?.id ?? "");
    setToFundId(treasury.funds[1]?.id ?? "");
    setDescription("");
    setError("");
  };

  const createMutation = useMutation({
    mutationFn: () =>
      financeApi.createMovement({
        association_id: treasury.association_id,
        direction,
        amount: parseInt(amount, 10),
        fund_id: fundId,
        to_fund_id: direction === "xfer" ? toFundId : undefined,
        occurred_on: date,
        description: description.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success(t("posted"));
      queryClient.invalidateQueries({ queryKey: ["treasury", treasury.association_id] });
      queryClient.invalidateQueries({ queryKey: ["movements", treasury.association_id] });
      setOpen(false);
      reset();
    },
    onError: (err) => setError(extractError(err) ?? t("postError")),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseInt(amount, 10);
    if (Number.isNaN(amt) || amt <= 0) return setError(t("amountError"));
    if (direction === "xfer" && fundId === toFundId) return setError(t("sameFundError"));
    setError("");
    createMutation.mutate();
  };

  const isXfer = direction === "xfer";

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          {t("newMovement")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("newMovementTitle")}</DialogTitle>
          <DialogDescription>{t("newMovementDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 py-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("direction")}</Label>
              <Select value={direction} onValueChange={(v) => setDirection(v as MovementDirection)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="in">{t("dir_in")}</SelectItem>
                  <SelectItem value="out">{t("dir_out")}</SelectItem>
                  <SelectItem value="xfer">{t("dir_xfer")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mv-amount">{`${t("amount")} (${treasury.currency})`}</Label>
              <Input
                id="mv-amount"
                type="number"
                inputMode="numeric"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{isXfer ? t("fromFund") : t("fund")}</Label>
            <Select value={fundId} onValueChange={setFundId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {treasury.funds.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isXfer && (
            <div className="space-y-1.5">
              <Label>{t("toFund")}</Label>
              <Select value={toFundId} onValueChange={setToFundId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {treasury.funds.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="mv-date">{t("date")}</Label>
            <Input
              id="mv-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mv-desc">{t("descriptionField")}</Label>
            <Input id="mv-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
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
            <Button type="submit" disabled={createMutation.isPending} className="gap-2">
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("post")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Void dialog ─────────────────────────────────────────────────────────────

function VoidDialog({ movementId, associationId }: { movementId: string; associationId: string }) {
  const t = useTranslations("finance");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const voidMutation = useMutation({
    mutationFn: () => financeApi.voidMovement(movementId, reason.trim()),
    onSuccess: () => {
      toast.success(t("voidDone"));
      queryClient.invalidateQueries({ queryKey: ["treasury", associationId] });
      queryClient.invalidateQueries({ queryKey: ["movements", associationId] });
      setOpen(false);
      setReason("");
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive">
          <Ban className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("voidConfirmTitle")}</DialogTitle>
          <DialogDescription>{t("voidConfirmDesc")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (reason.trim().length >= 2) voidMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="void-reason">{t("voidReason")}</Label>
            <Input
              id="void-reason"
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
              disabled={voidMutation.isPending || reason.trim().length < 2}
              className="gap-2"
            >
              {voidMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("void")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
