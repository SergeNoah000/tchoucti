"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, Plus, ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
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
import { associationsApi, loansApi, loanTypesApi, membersApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import type { Association, Loan, LoanStatus, Membership } from "@/lib/types";

interface LoanTypeOption {
  id: string;
  name: string;
  interest_rate_pct: number | string;
  late_fee_pct: number | string;
  max_duration_months: number;
  is_active: boolean;
}
import { useFormatters } from "@/lib/format";

const LOAN_STATUS_VARIANT: Record<
  LoanStatus,
  "warning" | "info" | "success" | "destructive" | "secondary"
> = {
  requested: "warning",
  approved: "info",
  disbursed: "info",
  repaying: "info",
  paid: "success",
  rejected: "destructive",
  defaulted: "destructive",
  cancelled: "secondary",
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function LoansPage() {
  const t = useTranslations("loan");

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const fmt = useFormatters(association?.currency);
  const associationId = association?.id;

  const { data: loans = [], isLoading } = useQuery<Loan[]>({
    queryKey: ["loans", associationId],
    queryFn: () => loansApi.list(associationId!),
    enabled: !!associationId,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={association ? <RequestLoanDialog association={association} /> : undefined}
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : loans.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={Banknote} title={t("empty")} description={t("emptyDesc")} />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {loans.map((l) => (
            <Link
              key={l.id}
              href={`/dashboard/loans/${l.id}`}
              className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Banknote className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate font-semibold leading-tight">{l.borrower_name ?? "—"}</p>
                    <Badge variant="outline" className="font-mono text-[10px]">{l.reference}</Badge>
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {fmt.currency(l.principal)} · {l.duration_months} {t("duration").toLowerCase()}
                    {" · "}
                    {l.interest_rate_pct}%
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <div className="text-right">
                  {(l.status === "repaying" || l.status === "disbursed") && (
                    <p className="text-xs font-medium text-muted-foreground tabular-nums">
                      {t("remaining")}: {fmt.currency(l.remaining_balance)}
                    </p>
                  )}
                  <Badge variant={LOAN_STATUS_VARIANT[l.status]} className="mt-0.5">
                    {t(`status_${l.status}`)}
                  </Badge>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Request dialog ──────────────────────────────────────────────────────────

function RequestLoanDialog({ association }: { association: Association }) {
  const t = useTranslations("loan");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isBureau = canDoBureauActions(user);

  const [open, setOpen] = useState(false);
  const [membershipId, setMembershipId] = useState("");
  const [loanTypeId, setLoanTypeId] = useState("");
  const [principal, setPrincipal] = useState("");
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState("");

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", association.id],
    queryFn: () => membersApi.list(association.id),
    enabled: open,
  });
  const activeMembers = members.filter((m) => m.status === "active");
  const myMembership = members.find((m) => m.user_id === user?.id);

  // Membre simple : la demande est forcément pour lui-même.
  useEffect(() => {
    if (open && !isBureau && myMembership && !membershipId) {
      setMembershipId(myMembership.id);
    }
  }, [open, isBureau, myMembership, membershipId]);

  const { data: loanTypes = [] } = useQuery<LoanTypeOption[]>({
    queryKey: ["loan-types", association.id],
    queryFn: () => loanTypesApi.list(association.id, true),
    enabled: open,
  });

  const selectedType = loanTypes.find((lt) => lt.id === loanTypeId);

  // Présélectionne le 1er type disponible à l'ouverture.
  useEffect(() => {
    if (open && !loanTypeId && loanTypes.length > 0) {
      setLoanTypeId(loanTypes[0].id);
    }
  }, [open, loanTypeId, loanTypes]);

  const requestMutation = useMutation({
    mutationFn: () =>
      loansApi.request({
        association_id: association.id,
        borrower_membership_id: membershipId,
        loan_type_id: loanTypeId,
        principal: parseInt(principal, 10),
        purpose: purpose.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success(t("requested"));
      queryClient.invalidateQueries({ queryKey: ["loans", association.id] });
      setOpen(false);
      reset();
    },
    onError: (err) => setError(extractError(err) ?? t("requestError")),
  });

  const reset = () => {
    setMembershipId("");
    setLoanTypeId("");
    setPrincipal("");
    setPurpose("");
    setError("");
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const p = parseInt(principal, 10);
    if (!membershipId || !loanTypeId || Number.isNaN(p) || p <= 0) {
      setError(t("requestError"));
      return;
    }
    setError("");
    requestMutation.mutate();
  };

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
          {t("request")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("requestTitle")}</DialogTitle>
          <DialogDescription>{t("requestDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>{t("borrower")}</Label>
            {!isBureau ? (
              // Membre simple : demande pour soi-même uniquement.
              <p className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
                {myMembership?.user.full_name ?? user?.full_name}{" "}
                <span className="text-muted-foreground">({t("borrowerSelf")})</span>
              </p>
            ) : activeMembers.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-3 text-center text-sm text-muted-foreground">
                {t("noMembers")}
              </p>
            ) : (
              <Select value={membershipId} onValueChange={setMembershipId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("selectMember")} />
                </SelectTrigger>
                <SelectContent>
                  {activeMembers.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.user.full_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>{t("loanType")}</Label>
            {loanTypes.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-3 text-center text-sm text-muted-foreground">
                {t("noLoanTypes")}
              </p>
            ) : (
              <Select value={loanTypeId} onValueChange={setLoanTypeId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("selectType")} />
                </SelectTrigger>
                <SelectContent>
                  {loanTypes.map((lt) => (
                    <SelectItem key={lt.id} value={lt.id}>
                      {lt.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {selectedType && (
              <p className="text-xs text-muted-foreground">
                {t("loanTypeHint", {
                  rate: String(selectedType.interest_rate_pct),
                  max: selectedType.max_duration_months,
                })}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ln-principal">{`${t("principal")} (${association.currency})`}</Label>
            <Input
              id="ln-principal"
              type="number"
              inputMode="numeric"
              min={1}
              value={principal}
              onChange={(e) => setPrincipal(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-purpose">{t("purpose")}</Label>
            <Textarea
              id="ln-purpose"
              rows={2}
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder={t("purposePlaceholder")}
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
            <Button type="submit" disabled={requestMutation.isPending || !membershipId || !loanTypeId} className="gap-2">
              {requestMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("request")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
