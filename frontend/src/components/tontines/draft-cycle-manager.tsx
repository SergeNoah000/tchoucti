"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, PlayCircle, Save, Users } from "lucide-react";
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

  const initial = useMemo(
    () => cycle.rounds.flatMap((r) => r.beneficiaries.map((b) => b.membership_id)),
    [cycle.rounds],
  );
  const [selected, setSelected] = useState<string[]>(initial);

  const { data: members = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId),
  });
  const activeMembers = useMemo(() => members.filter((m) => m.status === "active"), [members]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tontine", tontineId] });

  const save = useMutation({
    mutationFn: () =>
      tontinesApi.setParticipants(cycle.id, {
        participant_ids: selected,
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
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const dirty = useMemo(
    () => selected.join(",") !== initial.join(","),
    [selected, initial],
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
            {t("selectParticipants")} ({selected.length})
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
