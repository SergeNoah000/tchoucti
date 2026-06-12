"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, PlayCircle, Save, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { membersApi, tontinesApi } from "@/lib/api";
import type { Membership, TontineCycleDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

/** Gère les participants d'un cycle BROUILLON : sélection ordonnée, (re)génération
 *  des tours, puis démarrage du cycle. */
export function DraftCycleManager({
  tontineId,
  cycle,
  associationId,
}: {
  tontineId: string;
  cycle: TontineCycleDetail;
  associationId: string;
}) {
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  // État initial depuis les bénéficiaires existants : ordre des membres (1re
  // apparition), nombre de noms par membre, et libellés existants à préserver.
  const { initialOrder, initialCounts, initialNames } = useMemo(() => {
    const order: string[] = [];
    const cnt: Record<string, number> = {};
    const names: Record<string, string[]> = {};
    for (const r of cycle.rounds) {
      for (const b of r.beneficiaries) {
        if (!(b.membership_id in cnt)) {
          order.push(b.membership_id);
          cnt[b.membership_id] = 0;
          names[b.membership_id] = [];
        }
        cnt[b.membership_id] += 1;
        names[b.membership_id].push(b.name ?? "");
      }
    }
    return { initialOrder: order, initialCounts: cnt, initialNames: names };
  }, [cycle.rounds]);

  const [selected, setSelected] = useState<string[]>(initialOrder);
  const [counts, setCounts] = useState<Record<string, number>>(initialCounts);

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId),
  });
  const activeMembers = useMemo(() => members.filter((m) => m.status === "active"), [members]);

  // Slots (un par nom) + libellés : préserve les noms existants, défaut sinon.
  const { slotIds, slotNames, totalSlots } = useMemo(() => {
    const ids: string[] = [];
    const labels: (string | null)[] = [];
    for (const id of selected) {
      const m = activeMembers.find((x) => x.id === id);
      const full = m?.user.full_name ?? "";
      const n = Math.max(1, counts[id] ?? 1);
      for (let i = 0; i < n; i++) {
        ids.push(id);
        const existing = initialNames[id]?.[i];
        labels.push(existing && existing.trim() ? existing : n > 1 ? `${full} ${i + 1}` : full);
      }
    }
    return { slotIds: ids, slotNames: labels, totalSlots: ids.length };
  }, [selected, counts, activeMembers, initialNames]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tontine", tontineId] });

  const save = useMutation({
    mutationFn: () =>
      tontinesApi.setParticipants(cycle.id, {
        participant_ids: slotIds,
        participant_names: slotNames,
        is_mandatory: cycle.is_mandatory,
      }),
    onSuccess: () => {
      toast.success(t("participantsSaved"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  const activate = useMutation({
    mutationFn: () => tontinesApi.activateCycle(cycle.id),
    onSuccess: () => {
      toast.success(t("cycleStarted"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("error")),
  });

  const toggle = (id: string) =>
    setSelected((s) => {
      if (s.includes(id)) {
        setCounts((c) => {
          const next = { ...c };
          delete next[id];
          return next;
        });
        return s.filter((x) => x !== id);
      }
      setCounts((c) => ({ ...c, [id]: 1 }));
      return [...s, id];
    });

  const setCount = (id: string, n: number) =>
    setCounts((c) => ({ ...c, [id]: Math.max(1, Math.min(20, n)) }));

  const dirty = useMemo(
    () => slotIds.join(",") !== initialOrder.flatMap((id) => Array(initialCounts[id]).fill(id)).join(","),
    [slotIds, initialOrder, initialCounts],
  );
  const canActivate = cycle.rounds_count > 0 && !dirty;

  return (
    <Card className="border-dashed">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-start gap-2">
          <Users className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">{t("draftParticipantsTitle")}</p>
            <p className="text-xs text-muted-foreground">{t("draftParticipantsHint")}</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>
            {t("selectParticipants")} ({selected.length}
            {totalSlots !== selected.length ? ` · ${t("namesTotal", { n: totalSlots })}` : ""})
          </Label>
          {activeMembers.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
              {t("noMembers")}
            </p>
          ) : (
            <div className="max-h-60 space-y-1 overflow-y-auto rounded-lg border border-border p-1">
              {activeMembers.map((m) => {
                const isSel = selected.includes(m.id);
                const order = selected.indexOf(m.id) + 1;
                const cnt = counts[m.id] ?? 1;
                return (
                  <div
                    key={m.id}
                    className={cn(
                      "flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      isSel ? "bg-primary/10 text-foreground" : "hover:bg-accent/50",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => toggle(m.id)}
                      className="flex flex-1 items-center gap-2 text-left"
                    >
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
                    </button>
                    {isSel && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-muted-foreground">{t("namesLabel")}</span>
                        <button
                          type="button"
                          onClick={() => setCount(m.id, cnt - 1)}
                          disabled={cnt <= 1}
                          className="flex h-6 w-6 items-center justify-center rounded border border-border text-sm disabled:opacity-40"
                        >
                          −
                        </button>
                        <span className="w-5 text-center text-sm font-semibold tabular-nums">{cnt}</span>
                        <button
                          type="button"
                          onClick={() => setCount(m.id, cnt + 1)}
                          className="flex h-6 w-6 items-center justify-center rounded border border-border text-sm"
                        >
                          +
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={save.isPending || !dirty}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {t("saveParticipants")}
          </Button>
          <Button
            size="sm"
            className="gap-1.5"
            disabled={activate.isPending || !canActivate}
            onClick={() => activate.mutate()}
          >
            {activate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            {t("startCycle")}
          </Button>
        </div>
        {dirty && <p className="text-right text-xs text-amber-600">{t("saveBeforeStart")}</p>}
      </CardContent>
    </Card>
  );
}
