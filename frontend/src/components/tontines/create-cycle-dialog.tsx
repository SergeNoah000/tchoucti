"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Loader2, Check, Shuffle, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { membersApi, tontinesApi } from "@/lib/api";
import type { Association, Membership } from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

/**
 * Dialog de création d'un cycle de tontine — sélection des participants,
 * bénéficiaires par tour, shuffle, participation obligatoire/optionnelle,
 * preview des tours. Partagé entre /dashboard/tontines, la page config
 * tontines et le wizard d'onboarding.
 */
export function CreateCycleDialog({ association }: { association: Association }) {
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const fmt = useFormatters(association.currency);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState(
    association.config?.tontine?.contribution_amount?.toString() ?? "",
  );
  const [startDate, setStartDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [shuffle, setShuffle] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [beneficiariesPerRound, setBeneficiariesPerRound] = useState("1");
  const [isMandatory, setIsMandatory] = useState(true);
  const [error, setError] = useState("");

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", association.id],
    queryFn: () => membersApi.list(association.id),
    enabled: open,
  });
  const activeMembers = useMemo(() => members.filter((m) => m.status === "active"), [members]);

  const buildRounds = () => {
    const k = Math.max(1, parseInt(beneficiariesPerRound, 10) || 1);
    const rounds: Array<{ beneficiaries: Array<{ membership_id: string }> }> = [];
    for (let i = 0; i < selected.length; i += k) {
      const slice = selected.slice(i, i + k);
      if (slice.length === 0) continue;
      rounds.push({ beneficiaries: slice.map((id) => ({ membership_id: id })) });
    }
    return rounds;
  };

  const previewRounds = useMemo(() => buildRounds(), [selected, beneficiariesPerRound]); // eslint-disable-line react-hooks/exhaustive-deps

  const computedExclusions = useMemo(() => {
    if (isMandatory) return [];
    const selectedSet = new Set(selected);
    return activeMembers.filter((m) => !selectedSet.has(m.id)).map((m) => m.id);
  }, [isMandatory, selected, activeMembers]);

  const createMutation = useMutation({
    mutationFn: () =>
      tontinesApi.create({
        association_id: association.id,
        name: name.trim(),
        round_amount: parseInt(amount, 10),
        start_date: startDate,
        rounds: buildRounds(),
        shuffle,
        is_mandatory: isMandatory,
        excluded_membership_ids: computedExclusions,
      }),
    onSuccess: () => {
      toast.success(t("created"));
      queryClient.invalidateQueries({ queryKey: ["tontines", association.id] });
      setOpen(false);
      reset();
    },
    onError: (err) => setError(extractError(err) ?? t("createError")),
  });

  const reset = () => {
    setName("");
    setAmount(association.config?.tontine?.contribution_amount?.toString() ?? "");
    setShuffle(false);
    setSelected([]);
    setBeneficiariesPerRound("1");
    setIsMandatory(true);
    setError("");
  };

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseInt(amount, 10);
    if (name.trim().length < 2 || Number.isNaN(amt) || amt <= 0) {
      setError(t("createError"));
      return;
    }
    if (selected.length < 2) {
      setError(t("minParticipants"));
      return;
    }
    setError("");
    createMutation.mutate();
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
          {t("create")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("createTitle")}</DialogTitle>
          <DialogDescription>{t("createDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="tc-name">{t("name")}</Label>
            <Input
              id="tc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("namePlaceholder")}
              required
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tc-amount">{`${t("roundAmount")} (${association.currency})`}</Label>
              <Input
                id="tc-amount"
                type="number"
                inputMode="numeric"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tc-date">{t("startDate")}</Label>
              <Input
                id="tc-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tc-bpr">{t("beneficiariesPerRound")}</Label>
            <Input
              id="tc-bpr"
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={beneficiariesPerRound}
              onChange={(e) => setBeneficiariesPerRound(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t("beneficiariesPerRoundHint")}</p>
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Shuffle className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{t("shuffle")}</p>
                <p className="text-xs text-muted-foreground">{t("shuffleHint")}</p>
              </div>
            </div>
            <Switch checked={shuffle} onCheckedChange={setShuffle} />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{t("isMandatory")}</p>
                <p className="text-xs text-muted-foreground">{t("isMandatoryHint")}</p>
              </div>
            </div>
            <Switch checked={isMandatory} onCheckedChange={setIsMandatory} />
          </div>
          {!isMandatory && computedExclusions.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
              {t("excludedHint", { count: computedExclusions.length })}
            </div>
          )}

          <div className="space-y-1.5">
            <Label>
              {t("selectParticipants")} ({selected.length})
            </Label>
            <p className="text-xs text-muted-foreground">{t("participantsHint")}</p>
            {activeMembers.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
                {t("noMembers")}
              </p>
            ) : (
              <div className="max-h-52 space-y-1 overflow-y-auto rounded-lg border border-border p-1">
                {activeMembers.map((m) => {
                  const isSel = selected.includes(m.id);
                  const order = selected.indexOf(m.id) + 1;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => toggle(m.id)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                        isSel ? "bg-primary/10 text-foreground" : "hover:bg-accent/50",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <span
                          className={cn(
                            "flex h-5 w-5 items-center justify-center rounded border text-[10px] font-bold",
                            isSel
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-border text-transparent",
                          )}
                        >
                          {isSel ? order : ""}
                        </span>
                        {m.user.full_name}
                      </span>
                      {isSel && <Check className="h-4 w-4 text-primary" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {previewRounds.length > 0 && (
            <div className="space-y-1.5">
              <Label>{t("roundsPreview", { count: previewRounds.length })}</Label>
              <div className="space-y-1 rounded-lg border border-border/60 bg-muted/20 p-2 text-xs">
                {previewRounds.map((r, i) => {
                  const amt = parseInt(amount, 10) || 0;
                  const pot = amt * selected.length;
                  const share = r.beneficiaries.length > 0 ? Math.floor(pot / r.beneficiaries.length) : 0;
                  const names = r.beneficiaries
                    .map((b) => activeMembers.find((m) => m.id === b.membership_id)?.user.full_name ?? "—")
                    .join(", ");
                  return (
                    <div key={i} className="flex items-start justify-between gap-2">
                      <span className="font-medium text-muted-foreground">
                        {t("round")} {i + 1}:
                      </span>
                      <span className="flex-1 truncate text-right">
                        {names}
                        {r.beneficiaries.length > 1 && pot > 0 && (
                          <span className="ml-1 text-muted-foreground">
                            ({fmt.currency(share)} {t("each")})
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

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
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Users className="h-4 w-4" />
              )}
              {t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
