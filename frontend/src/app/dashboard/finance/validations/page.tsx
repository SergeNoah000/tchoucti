"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck,
  Loader2,
  Check,
  X,
  Ban,
  Banknote,
  HeartHandshake,
  Repeat,
  PiggyBank,
  Clock,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, payoutsApi } from "@/lib/api";
import type { PayoutRequest } from "@/lib/api";
import type { Association } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions, canValidatePayouts } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import { formatDateTime } from "@/lib/utils";

const KIND_META: Record<
  string,
  { icon: typeof Banknote; label: string; cls: string }
> = {
  loan_disbursement: { icon: Banknote, label: "Décaissement prêt", cls: "text-sky-600" },
  aid_payout: { icon: HeartHandshake, label: "Versement aide", cls: "text-rose-600" },
  tontine_payout: { icon: Repeat, label: "Versement tontine", cls: "text-violet-600" },
  caisse_withdrawal: { icon: PiggyBank, label: "Retrait caisse", cls: "text-amber-600" },
  manual_out: { icon: Banknote, label: "Sortie manuelle", cls: "text-muted-foreground" },
};

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function PayoutValidationsPage() {
  const { user } = useAuthStore();
  const canValidate = canValidatePayouts(user);
  const canBureau = canDoBureauActions(user);
  const qc = useQueryClient();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];
  const associationId = association?.id;
  const fmt = useFormatters(association?.currency);

  const { data: pending = [], isLoading } = useQuery<PayoutRequest[]>({
    queryKey: ["payouts", associationId, "pending"],
    queryFn: () => payoutsApi.list(associationId!, "pending"),
    enabled: !!associationId && canBureau,
  });

  const { data: history = [] } = useQuery<PayoutRequest[]>({
    queryKey: ["payouts", associationId, "history"],
    queryFn: async () => {
      const [validated, rejected, cancelled] = await Promise.all([
        payoutsApi.list(associationId!, "validated"),
        payoutsApi.list(associationId!, "rejected"),
        payoutsApi.list(associationId!, "cancelled"),
      ]);
      return [...validated, ...rejected, ...cancelled]
        .sort((a, b) => (b.decided_at || "").localeCompare(a.decided_at || ""))
        .slice(0, 30);
    },
    enabled: !!associationId && canBureau,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["payouts"] });
    qc.invalidateQueries({ queryKey: ["loans"] });
    qc.invalidateQueries({ queryKey: ["social-aid"] });
    qc.invalidateQueries({ queryKey: ["treasury"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  const validateM = useMutation({
    mutationFn: (id: string) => payoutsApi.validate(id),
    onSuccess: () => {
      toast.success("Sortie validée — l'argent a été décaissé.");
      invalidate();
    },
    onError: (e) => toast.error(extractError(e) || "Échec de la validation"),
  });

  const [rejectTarget, setRejectTarget] = useState<PayoutRequest | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const rejectM = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      payoutsApi.reject(id, note),
    onSuccess: () => {
      toast.success("Sortie refusée.");
      setRejectTarget(null);
      setRejectNote("");
      invalidate();
    },
    onError: (e) => toast.error(extractError(e) || "Échec du refus"),
  });

  const cancelM = useMutation({
    mutationFn: (id: string) => payoutsApi.cancel(id),
    onSuccess: () => {
      toast.success("Demande annulée.");
      invalidate();
    },
    onError: (e) => toast.error(extractError(e) || "Échec de l'annulation"),
  });

  if (!canBureau) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="Accès réservé"
        description="Cette page est réservée aux membres du bureau."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Validation des sorties"
        description={
          canValidate
            ? "Validez ou refusez les sorties d'argent préparées. C'est la validation qui déclenche réellement le décaissement."
            : "Suivi des sorties d'argent en attente de validation du trésorier."
        }
      />

      {/* En attente */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <Clock className="h-4 w-4" /> En attente ({pending.length})
        </h2>
        {isLoading ? (
          <Skeleton className="h-24 w-full rounded-xl" />
        ) : pending.length === 0 ? (
          <EmptyState
            icon={Check}
            title="Rien à valider"
            description="Aucune sortie d'argent n'est en attente de validation."
          />
        ) : (
          pending.map((p) => {
            const meta = KIND_META[p.kind] ?? KIND_META.manual_out;
            const Icon = meta.icon;
            const busy = validateM.isPending || rejectM.isPending || cancelM.isPending;
            return (
              <Card key={p.id}>
                <CardContent className="flex flex-wrap items-center gap-4 p-4">
                  <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-muted ${meta.cls}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{meta.label}</span>
                      <Badge variant="secondary">{fmt.currency(p.amount)}</Badge>
                    </div>
                    <p className="truncate text-sm text-muted-foreground">
                      {p.description || "—"}
                      {p.beneficiary_name ? ` · ${p.beneficiary_name}` : ""}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Préparé par {p.prepared_by_name || "—"} · {formatDateTime(p.prepared_at)}
                      {p.fund_name ? ` · fonds : ${p.fund_name}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {canValidate ? (
                      <>
                        <Button
                          size="sm"
                          variant="brand"
                          disabled={busy}
                          onClick={() => validateM.mutate(p.id)}
                        >
                          {validateM.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Check className="h-4 w-4" />
                          )}
                          Valider
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => setRejectTarget(p)}
                        >
                          <X className="h-4 w-4" />
                          Refuser
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => cancelM.mutate(p.id)}
                      >
                        <Ban className="h-4 w-4" />
                        Annuler
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </section>

      {/* Historique */}
      {history.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">Historique récent</h2>
          <Card>
            <CardContent className="divide-y p-0">
              {history.map((p) => {
                const meta = KIND_META[p.kind] ?? KIND_META.manual_out;
                const statusBadge =
                  p.status === "validated"
                    ? { label: "Validée", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" }
                    : p.status === "rejected"
                      ? { label: "Refusée", cls: "bg-destructive/10 text-destructive" }
                      : { label: "Annulée", cls: "bg-muted text-muted-foreground" };
                return (
                  <div key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <span className={`text-xs font-medium ${meta.cls}`}>{meta.label}</span>
                    <span className="text-sm font-medium">{fmt.currency(p.amount)}</span>
                    <span className="truncate text-sm text-muted-foreground">
                      {p.beneficiary_name || p.description || ""}
                    </span>
                    <span className={`ml-auto rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge.cls}`}>
                      {statusBadge.label}
                    </span>
                    <span className="w-full text-xs text-muted-foreground sm:w-auto">
                      {p.decided_by_name ? `par ${p.decided_by_name} · ` : ""}
                      {p.decided_at ? formatDateTime(p.decided_at) : ""}
                    </span>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </section>
      )}

      {/* Dialog de refus */}
      <Dialog open={!!rejectTarget} onOpenChange={(o) => !o && setRejectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Refuser la sortie</DialogTitle>
            <DialogDescription>
              {rejectTarget
                ? `${KIND_META[rejectTarget.kind]?.label ?? "Sortie"} · ${fmt.currency(rejectTarget.amount)}`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            placeholder="Motif du refus (optionnel)"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)}>
              Annuler
            </Button>
            <Button
              variant="destructive"
              disabled={rejectM.isPending}
              onClick={() =>
                rejectTarget && rejectM.mutate({ id: rejectTarget.id, note: rejectNote })
              }
            >
              {rejectM.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
              Confirmer le refus
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
