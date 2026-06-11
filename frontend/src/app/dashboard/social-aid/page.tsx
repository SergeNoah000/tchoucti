"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { HeartHandshake, History, Plus, Loader2, Check, X, HandCoins, Pencil, ShieldCheck } from "lucide-react";
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
import { associationsApi, membersApi, socialAidApi } from "@/lib/api";
import type { Association, Membership, SocialAidCase, SocialAidKind, SocialAidStatus } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

const KINDS: SocialAidKind[] = ["death", "illness", "marriage", "birth", "other"];

const STATUS_VARIANT: Record<SocialAidStatus, "secondary" | "info" | "success" | "destructive" | "warning"> = {
  requested: "warning",
  reviewing: "info",
  approved: "info",
  paid: "success",
  rejected: "destructive",
  cancelled: "secondary",
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function SocialAidPage() {
  const t = useTranslations("socialAid");
  const { user } = useAuthStore();
  const canManage = canDoBureauActions(user);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const associationId = association?.id;

  const { data: cases = [], isLoading } = useQuery<SocialAidCase[]>({
    queryKey: ["social-aid", associationId],
    queryFn: () => socialAidApi.list(associationId!),
    enabled: !!associationId,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" className="gap-1.5">
              <Link href="/dashboard/social-aid/history">
                <History className="h-4 w-4" />
                {t("historyLink")}
              </Link>
            </Button>
            {associationId && <DeclareDialog association={association!} />}
          </div>
        }
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={HeartHandshake} title={t("empty")} description={t("emptyDesc")} />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {cases.map((c) => (
            <CaseCard
              key={c.id}
              c={c}
              canManage={canManage}
              associationId={associationId!}
              currency={association?.currency}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Case card ───────────────────────────────────────────────────────────────

function CaseCard({
  c,
  canManage,
  associationId,
  currency,
}: {
  c: SocialAidCase;
  canManage: boolean;
  associationId: string;
  currency?: string;
}) {
  const t = useTranslations("socialAid");
  const tCommon = useTranslations("common");
  const fmt = useFormatters(currency);
  const queryClient = useQueryClient();

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["social-aid", associationId] });
  const refreshAll = () => {
    refresh();
    queryClient.invalidateQueries({ queryKey: ["treasury", associationId] });
    queryClient.invalidateQueries({ queryKey: ["movements", associationId] });
  };

  const approveMutation = useMutation({
    mutationFn: () => socialAidApi.approve(c.id),
    onSuccess: () => {
      toast.success(t("approvedToast"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
  });

  const payoutMutation = useMutation({
    mutationFn: () => socialAidApi.payout(c.id),
    onSuccess: () => {
      toast.success(t("paidToast"));
      refreshAll();
    },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
  });

  const amount = c.status === "paid" ? c.paid_amount : c.approved_amount || c.requested_amount || 0;
  const canDecide = canManage && (c.status === "requested" || c.status === "reviewing");
  const canPayout = canManage && c.status === "approved";
  const canEdit =
    canManage && c.status !== "paid" && c.status !== "rejected" && c.status !== "cancelled";

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <HeartHandshake className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate font-semibold leading-tight">{c.title}</p>
              <Badge variant="outline" className="font-mono text-[10px]">{c.reference}</Badge>
              <Badge variant="brand" className="text-[10px]">{t(`kind_${c.kind}`)}</Badge>
            </div>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {c.beneficiary_name ?? "—"} · {t("requestedOn", { date: fmt.date(c.requested_on) })}
            </p>
            {c.rejection_reason && (
              <p className="mt-0.5 truncate text-xs text-destructive">{c.rejection_reason}</p>
            )}
            {c.funding_mode === "member_insurance" && c.insurance_minimum != null && (
              <p
                className={cn(
                  "mt-0.5 flex items-center gap-1 text-xs",
                  c.insurance_below_min
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-emerald-600 dark:text-emerald-400",
                )}
              >
                <ShieldCheck className="h-3 w-3 shrink-0" />
                {t("insuranceCriterion", {
                  balance: fmt.currency(c.insurance_balance ?? 0),
                  min: fmt.currency(c.insurance_minimum),
                })}
                {" · "}
                {c.insurance_below_min ? t("insuranceUnfavorable") : t("insuranceFavorable")}
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-bold tabular-nums">{amount > 0 ? fmt.currency(amount) : t("noScale")}</p>
            <Badge variant={STATUS_VARIANT[c.status]} className="mt-0.5">{t(`status_${c.status}`)}</Badge>
          </div>
          {canEdit && <EditDialog c={c} currency={currency} onDone={refresh} />}
          {canDecide && (
            <div className="flex items-center gap-1.5">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="sm" className="gap-1.5">
                    <Check className="h-3.5 w-3.5" />
                    {t("approve")}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t("approveConfirmTitle")}</AlertDialogTitle>
                    <AlertDialogDescription>{t("approveConfirmDesc")}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                    <AlertDialogAction onClick={() => approveMutation.mutate()}>
                      {t("approve")}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <RejectDialog caseId={c.id} onDone={refresh} />
            </div>
          )}
          {canPayout && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" className="gap-1.5">
                  {payoutMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <HandCoins className="h-3.5 w-3.5" />
                  )}
                  {t("payout")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("payoutConfirmTitle")}</AlertDialogTitle>
                  <AlertDialogDescription>{t("payoutConfirmDesc")}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => payoutMutation.mutate()}>
                    {t("payout")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Reject dialog ─────────────────────────────────────────────────────────────

function RejectDialog({ caseId, onDone }: { caseId: string; onDone: () => void }) {
  const t = useTranslations("socialAid");
  const tCommon = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const rejectMutation = useMutation({
    mutationFn: () => socialAidApi.reject(caseId, reason.trim()),
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
        <Button size="sm" variant="outline" className="gap-1.5 text-destructive">
          <X className="h-3.5 w-3.5" />
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
            <Label htmlFor="rj-reason">{t("rejectReason")}</Label>
            <Textarea
              id="rj-reason"
              rows={3}
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
              className="gap-2"
            >
              {rejectMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("reject")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Edit dialog (#3 — édition d'un dossier par le bureau) ─────────────────────

function EditDialog({
  c,
  currency,
  onDone,
}: {
  c: SocialAidCase;
  currency?: string;
  onDone: () => void;
}) {
  const t = useTranslations("socialAid");
  const tCommon = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<SocialAidKind>(c.kind);
  const [title, setTitle] = useState(c.title);
  const [eventDate, setEventDate] = useState(c.event_date ?? "");
  const [description, setDescription] = useState(c.description ?? "");
  const [requestedAmount, setRequestedAmount] = useState(
    c.requested_amount != null ? String(c.requested_amount) : "",
  );

  const reset = () => {
    setKind(c.kind);
    setTitle(c.title);
    setEventDate(c.event_date ?? "");
    setDescription(c.description ?? "");
    setRequestedAmount(c.requested_amount != null ? String(c.requested_amount) : "");
  };

  const updateMutation = useMutation({
    mutationFn: () =>
      socialAidApi.update(c.id, {
        kind,
        title: title.trim(),
        description: description.trim(),
        event_date: eventDate || undefined,
        requested_amount: requestedAmount === "" ? undefined : parseInt(requestedAmount, 10) || 0,
      }),
    onSuccess: () => {
      toast.success(t("editedToast"));
      setOpen(false);
      onDone();
    },
    onError: (err) => toast.error(extractError(err) ?? t("actionError")),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="gap-1.5">
          <Pencil className="h-3.5 w-3.5" />
          {tCommon("edit")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("editTitle")}</DialogTitle>
          <DialogDescription>{t("editDesc")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim().length >= 2) updateMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("kind")}</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as SocialAidKind)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => (
                    <SelectItem key={k} value={k}>
                      {t(`kind_${k}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ed-date">{t("eventDate")}</Label>
              <Input
                id="ed-date"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-title">{t("caseTitle")}</Label>
            <Input id="ed-title" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={2} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-amount">{t("requestedAmount")}</Label>
            <Input
              id="ed-amount"
              type="number"
              min={0}
              value={requestedAmount}
              onChange={(e) => setRequestedAmount(e.target.value)}
              placeholder={currency}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-desc">{t("descriptionField")}</Label>
            <Textarea
              id="ed-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" disabled={updateMutation.isPending || title.trim().length < 2} className="gap-2">
              {updateMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {tCommon("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Declare dialog ────────────────────────────────────────────────────────────

function DeclareDialog({ association }: { association: Association }) {
  const t = useTranslations("socialAid");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [membershipId, setMembershipId] = useState("");
  const [kind, setKind] = useState<SocialAidKind>("death");
  const [title, setTitle] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", association.id],
    queryFn: () => membersApi.list(association.id),
    enabled: open,
  });
  const activeMembers = members.filter((m) => m.status === "active");

  const declareMutation = useMutation({
    mutationFn: () =>
      socialAidApi.declare({
        association_id: association.id,
        beneficiary_membership_id: membershipId,
        kind,
        title: title.trim(),
        description: description.trim() || undefined,
        event_date: eventDate || undefined,
      }),
    onSuccess: () => {
      toast.success(t("declared"));
      queryClient.invalidateQueries({ queryKey: ["social-aid", association.id] });
      setOpen(false);
      reset();
    },
    onError: (err) => setError(extractError(err) ?? t("declareError")),
  });

  const reset = () => {
    setMembershipId("");
    setKind("death");
    setTitle("");
    setEventDate("");
    setDescription("");
    setError("");
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!membershipId || title.trim().length < 2) {
      setError(t("declareError"));
      return;
    }
    setError("");
    declareMutation.mutate();
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
          {t("declare")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("declareTitle")}</DialogTitle>
          <DialogDescription>{t("declareDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>{t("beneficiary")}</Label>
            {activeMembers.length === 0 ? (
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("kind")}</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as SocialAidKind)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => (
                    <SelectItem key={k} value={k}>
                      {t(`kind_${k}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sa-date">{t("eventDate")}</Label>
              <Input
                id="sa-date"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sa-title">{t("caseTitle")}</Label>
            <Input
              id="sa-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("caseTitlePlaceholder")}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sa-desc">{t("descriptionField")}</Label>
            <Textarea
              id="sa-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
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
            <Button
              type="submit"
              disabled={declareMutation.isPending || !membershipId}
              className="gap-2"
            >
              {declareMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("declare")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
