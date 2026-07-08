"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, ArrowDown, Loader2, ListOrdered } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { tontinesApi } from "@/lib/api";
import type { TontineCycleDetail } from "@/lib/types";

interface Row {
  membershipId: string;
  label: string;
  roundNumber: number;
}

function extractError(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}

export function ReorderPassageDialog({
  cycle,
  tontineId,
  trigger,
}: {
  cycle: TontineCycleDetail;
  tontineId: string;
  trigger: React.ReactNode;
}) {
  const t = useTranslations("tontine");
  const tCommon = useTranslations("common");
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  // Bénéficiaires des tours PAS ENCORE servis (statut pending), en ordre de passage.
  const initial = useMemo<Row[]>(() => {
    const rows: Row[] = [];
    [...cycle.rounds]
      .filter((r) => r.status === "pending")
      .sort((a, b) => a.round_number - b.round_number)
      .forEach((r) => {
        r.beneficiaries.forEach((b) => {
          rows.push({
            membershipId: b.membership_id,
            label: b.name || b.member_name || "—",
            roundNumber: r.round_number,
          });
        });
      });
    return rows;
  }, [cycle]);

  const [rows, setRows] = useState<Row[]>(initial);

  // Ré-initialise à l'ouverture (au cas où le cycle a changé).
  const onOpenChange = (o: boolean) => {
    if (o) setRows(initial);
    setOpen(o);
  };

  const move = (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= rows.length) return;
    setRows((prev) => {
      const next = [...prev];
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  const dirty = rows.some((r, i) => r.membershipId !== initial[i]?.membershipId);

  const save = useMutation({
    mutationFn: () =>
      tontinesApi.reorderCycle(
        cycle.id,
        rows.map((r) => r.membershipId),
      ),
    onSuccess: () => {
      toast.success(t("reorderSaved"));
      qc.invalidateQueries({ queryKey: ["tontine", tontineId] });
      setOpen(false);
    },
    onError: (e) => toast.error(extractError(e) || t("reorderError")),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ListOrdered className="h-4 w-4" />
            {t("reorderTitle")}
          </DialogTitle>
          <DialogDescription>{t("reorderDesc")}</DialogDescription>
        </DialogHeader>

        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("reorderEmpty")}</p>
        ) : (
          <ol className="max-h-[50vh] space-y-1.5 overflow-y-auto py-1">
            {rows.map((r, idx) => (
              <li
                key={`${r.membershipId}-${idx}`}
                className="flex items-center gap-3 rounded-lg border px-3 py-2"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {idx + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{r.label}</span>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    disabled={idx === 0}
                    onClick={() => move(idx, -1)}
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    disabled={idx === rows.length - 1}
                    onClick={() => move(idx, 1)}
                  >
                    <ArrowDown className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {tCommon("cancel")}
          </Button>
          <Button disabled={!dirty || save.isPending || rows.length === 0} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("reorderSave")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
