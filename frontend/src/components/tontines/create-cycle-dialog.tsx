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

const FREQUENCIES = ["weekly", "biweekly", "monthly", "bimonthly", "custom"] as const;
const METHODS = ["manual", "random", "seniority", "vote", "auction", "need"] as const;

/**
 * Crée une tontine (durable) + son 1er cycle + ses séances d'office.
 * L'ordre de sélection des participants = l'ordre de passage des tours.
 */
export function CreateTontineDialog({ association }: { association: Association }) {
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const fmt = useFormatters(association.currency);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState(
    association.config?.tontine?.contribution_amount?.toString() ?? "",
  );
  const [frequency, setFrequency] = useState<string>("monthly");
  const [customDays, setCustomDays] = useState("30");
  const [beneficiariesPerRound, setBeneficiariesPerRound] = useState("1");
  const [beneficiaryPays, setBeneficiaryPays] = useState(true);
  const [selectionMethod, setSelectionMethod] = useState<string>("manual");
  const [startDate, setStartDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [shuffle, setShuffle] = useState(false);
  const [isMandatory, setIsMandatory] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", association.id],
    queryFn: () => membersApi.list(association.id),
    enabled: open,
  });
  const activeMembers = useMemo(() => members.filter((m) => m.status === "active"), [members]);

  const k = Math.max(1, parseInt(beneficiariesPerRound, 10) || 1);
  const nRounds = selected.length > 0 ? Math.ceil(selected.length / k) : 0;
  const payers = beneficiaryPays ? selected.length : Math.max(0, selected.length - k);
  const pot = (parseInt(amount, 10) || 0) * payers;

  const computedExclusions = useMemo(() => {
    if (isMandatory) return [];
    const sel = new Set(selected);
    return activeMembers.filter((m) => !sel.has(m.id)).map((m) => m.id);
  }, [isMandatory, selected, activeMembers]);

  const createMutation = useMutation({
    mutationFn: () =>
      tontinesApi.create({
        association_id: association.id,
        name: name.trim(),
        round_amount: parseInt(amount, 10),
        frequency,
        custom_interval_days: frequency === "custom" ? parseInt(customDays, 10) || 30 : undefined,
        beneficiaries_per_round: k,
        beneficiary_pays: beneficiaryPays,
        selection_method: selectionMethod,
        start_date: startDate,
        is_mandatory: isMandatory,
        participant_ids: selected,
        excluded_membership_ids: computedExclusions,
        shuffle,
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
    setFrequency("monthly");
    setCustomDays("30");
    setBeneficiariesPerRound("1");
    setBeneficiaryPays(true);
    setSelectionMethod("manual");
    setShuffle(false);
    setIsMandatory(true);
    setSelected([]);
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
      <DialogContent className="max-h-[88vh] min-w-0 overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("createTitle")}</DialogTitle>
          <DialogDescription>{t("createDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="min-w-0 space-y-4 py-2">
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
            <div className="space-y-1.5">
              <Label>{t("frequency")}</Label>
              <Select value={frequency} onValueChange={setFrequency}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FREQUENCIES.map((f) => (
                    <SelectItem key={f} value={f}>
                      {t(`freq_${f}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {frequency === "custom" && (
              <div className="space-y-1.5">
                <Label htmlFor="tc-days">{t("customDays")}</Label>
                <Input
                  id="tc-days"
                  type="number"
                  min={1}
                  value={customDays}
                  onChange={(e) => setCustomDays(e.target.value)}
                />
              </div>
            )}
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
            </div>
            <div className="space-y-1.5">
              <Label>{t("selectionMethod")}</Label>
              <Select value={selectionMethod} onValueChange={setSelectionMethod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {METHODS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {t(`method_${m}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{t("beneficiaryPays")}</p>
                <p className="text-xs text-muted-foreground">{t("beneficiaryPaysHint")}</p>
              </div>
            </div>
            <Switch checked={beneficiaryPays} onCheckedChange={setBeneficiaryPays} />
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

          {nRounds > 0 && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2.5 text-sm text-sky-900 dark:border-sky-900/40 dark:bg-sky-900/20 dark:text-sky-200">
              {t("createPreview", {
                participants: selected.length,
                perRound: k,
                rounds: nRounds,
                pot: fmt.currency(pot),
              })}
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
