"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Edit2,
  Loader2,
  Lock,
  Plus,
  Trash2,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { HelpField, ConfigPreview } from "@/components/onboarding/help-field";
import { OnboardingBanner } from "@/components/onboarding/onboarding-banner";

import { associationsApi, caissesApi, financeApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type { Association } from "@/lib/types";

interface Caisse {
  id: string;
  fund_id: string;
  name: string;
  slug: string;
  description?: string | null;
  category: "system" | "collective" | "project" | "personal";
  is_system: boolean;
  is_active: boolean;
  is_recurring: boolean;
  recurring_amount: number;
  is_member_required: boolean;
  member_required_amount: number;
  has_ceiling: boolean;
  ceiling_amount: number;
  has_objective: boolean;
  objective_amount: number;
  objective_deadline?: string | null;
}

interface Treasury {
  balance: number;
  currency: string;
  funds: { id: string; balance: number }[];
}

export default function ConfigCaissesPage() {
  const t = useTranslations("configCaisses");
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

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
  return <ConfigCaissesInner association={association} />;
}

function ConfigCaissesInner({ association }: { association: Association }) {
  const t = useTranslations("configCaisses");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const fmt = useFormatters(association.currency);

  const { data: caisses = [], isLoading } = useQuery<Caisse[]>({
    queryKey: ["caisses", association.id, "with-inactive"],
    queryFn: () => caissesApi.list(association.id, true),
  });

  const { data: treasury } = useQuery<Treasury>({
    queryKey: ["treasury", association.id],
    queryFn: () => financeApi.treasury(association.id),
  });
  const fundBalances = new Map<string, number>(
    treasury?.funds.map((f) => [f.id, f.balance]) ?? [],
  );

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Caisse | null>(null);

  const removeMutation = useMutation({
    mutationFn: (id: string) => caissesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["caisses", association.id, "with-inactive"] });
      toast.success(t("deleted"));
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? tCommon("error"));
    },
  });

  return (
    <div className="space-y-6">
      <OnboardingBanner />
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <Button asChild variant="ghost" className="gap-1.5">
            <Link href="/dashboard">
              <ArrowLeft className="h-4 w-4" />
              {tCommon("back")}
            </Link>
          </Button>
        }
      />

      <ConfigPreview intent="info">{t("intro")}</ConfigPreview>

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : (
        <ul className="space-y-2">
          {caisses.map((c) => {
            const balance = fundBalances.get(c.fund_id) ?? 0;
            const progress =
              c.has_objective && c.objective_amount > 0
                ? Math.min(100, Math.round((balance / c.objective_amount) * 100))
                : null;
            return (
              <li
                key={c.id}
                className="rounded-lg border border-border bg-card p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      {c.is_system ? <Lock className="h-5 w-5" /> : <Wallet className="h-5 w-5" />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold">{c.name}</p>
                        <Badge variant="outline" className="text-[10px]">
                          {t(`cat_${c.category}`)}
                        </Badge>
                        {c.is_system && (
                          <Badge variant="secondary" className="text-[10px]">
                            {t("system")}
                          </Badge>
                        )}
                        {!c.is_active && (
                          <Badge variant="outline" className="text-[10px] text-muted-foreground">
                            {t("inactive")}
                          </Badge>
                        )}
                      </div>
                      {c.description && (
                        <p className="text-sm text-muted-foreground">{c.description}</p>
                      )}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {c.is_recurring && (
                          <>
                            {t("recurring")}: <span className="font-medium">{fmt.currency(c.recurring_amount)}/séance</span>
                          </>
                        )}
                        {c.is_member_required && (
                          <>
                            {c.is_recurring && " · "}
                            {t("required")}: <span className="font-medium">{fmt.currency(c.member_required_amount)}/membre</span>
                          </>
                        )}
                        {c.has_ceiling && (
                          <>
                            {(c.is_recurring || c.is_member_required) && " · "}
                            {t("ceiling")}: <span className="font-medium">{fmt.currency(c.ceiling_amount)}</span>
                          </>
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">{t("balance")}</p>
                      <p className="text-lg font-bold tabular-nums">{fmt.currency(balance)}</p>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => setEditing(c)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    {!c.is_system && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>{t("deleteConfirmTitle")}</AlertDialogTitle>
                            <AlertDialogDescription>
                              {t("deleteConfirmDesc", { name: c.name })}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                            <AlertDialogAction
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                              onClick={() => removeMutation.mutate(c.id)}
                            >
                              {tCommon("delete")}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </div>

                {progress !== null && (
                  <div className="mt-3">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {t("objective")}: {fmt.currency(c.objective_amount)}
                        {c.objective_deadline && ` · ${fmt.date(c.objective_deadline)}`}
                      </span>
                      <span className="font-medium">{progress}%</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Button variant="outline" onClick={() => setCreating(true)} className="w-full gap-2">
        <Plus className="h-4 w-4" />
        {t("add")}
      </Button>

      {creating && (
        <CaisseFormDialog
          associationId={association.id}
          caisse={null}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            queryClient.invalidateQueries({ queryKey: ["caisses", association.id, "with-inactive"] });
          }}
        />
      )}
      {editing && (
        <CaisseFormDialog
          associationId={association.id}
          caisse={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            queryClient.invalidateQueries({ queryKey: ["caisses", association.id, "with-inactive"] });
          }}
        />
      )}
    </div>
  );
}

// ── Caisse form (create + edit) ───────────────────────────────────────────

function CaisseFormDialog({
  associationId,
  caisse,
  onClose,
  onSaved,
}: {
  associationId: string;
  caisse: Caisse | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("configCaisses");
  const tCommon = useTranslations("common");
  const isEdit = caisse !== null;
  const isSystem = caisse?.is_system ?? false;

  const [name, setName] = useState(caisse?.name ?? "");
  const [description, setDescription] = useState(caisse?.description ?? "");
  const [category, setCategory] = useState<"collective" | "project" | "personal">(
    (caisse?.category as "collective" | "project" | "personal") ?? "collective",
  );
  const [recurring, setRecurring] = useState(caisse?.is_recurring ?? false);
  const [recurringAmount, setRecurringAmount] = useState(
    caisse?.recurring_amount ? String(caisse.recurring_amount) : "",
  );
  const [memberRequired, setMemberRequired] = useState(caisse?.is_member_required ?? false);
  const [memberRequiredAmount, setMemberRequiredAmount] = useState(
    caisse?.member_required_amount ? String(caisse.member_required_amount) : "",
  );
  const [hasObjective, setHasObjective] = useState(caisse?.has_objective ?? false);
  const [objectiveAmount, setObjectiveAmount] = useState(
    caisse?.objective_amount ? String(caisse.objective_amount) : "",
  );
  const [objectiveDeadline, setObjectiveDeadline] = useState(caisse?.objective_deadline ?? "");
  const [isActive, setIsActive] = useState(caisse?.is_active ?? true);

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        description: description.trim() || undefined,
        is_active: isActive,
        is_recurring: recurring,
        recurring_amount: recurring ? parseInt(recurringAmount, 10) || 0 : 0,
        is_member_required: memberRequired,
        member_required_amount: memberRequired ? parseInt(memberRequiredAmount, 10) || 0 : 0,
        has_objective: category === "project" || hasObjective,
        objective_amount:
          hasObjective || category === "project" ? parseInt(objectiveAmount, 10) || 0 : 0,
        objective_deadline: objectiveDeadline || undefined,
      };
      if (isEdit) {
        return caissesApi.update(caisse!.id, payload);
      }
      return caissesApi.create({
        association_id: associationId,
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        category,
        ...payload,
      });
    },
    onSuccess: () => {
      toast.success(t(isEdit ? "updated" : "created"));
      onSaved();
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? t("createError"));
    },
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? t("editTitle") : t("addTitle")}</DialogTitle>
          <DialogDescription>
            {isSystem ? t("systemEditableHint") : t("addDesc")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <HelpField label={t("name")} required>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </HelpField>
            {!isEdit && (
              <HelpField label={t("category")} hint={t("categoryHint")}>
                <Select value={category} onValueChange={(v) => setCategory(v as typeof category)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="collective">
                      {t("cat_collective")} — {t("cat_collective_hint")}
                    </SelectItem>
                    <SelectItem value="project">
                      {t("cat_project")} — {t("cat_project_hint")}
                    </SelectItem>
                    <SelectItem value="personal">
                      {t("cat_personal")} — {t("cat_personal_hint")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </HelpField>
            )}
            <HelpField label={t("description")} className="sm:col-span-2">
              <Textarea
                value={description ?? ""}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </HelpField>
          </div>

          {isEdit && (
            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-md bg-muted/30 p-2.5">
              <div>
                <p className="text-sm font-medium">{t("active")}</p>
                <p className="text-xs text-muted-foreground">{t("activeHint")}</p>
              </div>
              <Switch checked={isActive} onCheckedChange={setIsActive} />
            </label>
          )}

          {!isSystem && (
            <>
              <div className="space-y-3 rounded-md border border-border bg-card p-3">
                <label className="flex cursor-pointer items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{t("recurringField")}</p>
                    <p className="text-xs text-muted-foreground">{t("recurringHint")}</p>
                  </div>
                  <Switch checked={recurring} onCheckedChange={setRecurring} />
                </label>
                {recurring && (
                  <HelpField label={t("recurringAmount")}>
                    <Input
                      type="number"
                      min={1}
                      value={recurringAmount}
                      onChange={(e) => setRecurringAmount(e.target.value)}
                    />
                  </HelpField>
                )}
              </div>

              <div className="space-y-3 rounded-md border border-border bg-card p-3">
                <label className="flex cursor-pointer items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{t("memberRequired")}</p>
                    <p className="text-xs text-muted-foreground">{t("memberRequiredHint")}</p>
                  </div>
                  <Switch checked={memberRequired} onCheckedChange={setMemberRequired} />
                </label>
                {memberRequired && (
                  <HelpField label={t("memberAmount")}>
                    <Input
                      type="number"
                      min={1}
                      value={memberRequiredAmount}
                      onChange={(e) => setMemberRequiredAmount(e.target.value)}
                    />
                  </HelpField>
                )}
              </div>

              {category !== "personal" && (
                <div className="space-y-3 rounded-md border border-border bg-card p-3">
                  <label className="flex cursor-pointer items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">
                        {t("objective")}
                        {category === "project" && (
                          <span className="ml-1 text-xs text-destructive">
                            ({t("projectRequired")})
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">{t("objectiveHint")}</p>
                    </div>
                    <Switch
                      checked={hasObjective || category === "project"}
                      onCheckedChange={setHasObjective}
                      disabled={category === "project"}
                    />
                  </label>
                  {(hasObjective || category === "project") && (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <HelpField label={t("objectiveAmount")}>
                        <Input
                          type="number"
                          min={1}
                          value={objectiveAmount}
                          onChange={(e) => setObjectiveAmount(e.target.value)}
                        />
                      </HelpField>
                      <HelpField label={t("objectiveDeadline")}>
                        <Input
                          type="date"
                          value={objectiveDeadline ?? ""}
                          onChange={(e) => setObjectiveDeadline(e.target.value)}
                        />
                      </HelpField>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tCommon("cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim()}
            className="gap-2"
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {tCommon("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
