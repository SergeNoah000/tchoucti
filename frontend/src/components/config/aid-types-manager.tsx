"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartHandshake, Loader2, Plus, Power, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { HelpField, ConfigPreview } from "@/components/onboarding/help-field";
import { aidTypesApi, associationsApi, caissesApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import type { Association } from "@/lib/types";

interface AidType {
  id: string;
  funding_mode?: "fixed" | "temporary" | "member_insurance";
  source_caisse_id?: string | null;
  source_caisse_name?: string | null;
  auto_create_caisse?: boolean;
  insurance_caisse_id?: string | null;
  insurance_caisse_name?: string | null;
  insurance_minimum?: number;
  refill_period_days?: number;
  name: string;
  slug: string;
  description?: string | null;
  is_active: boolean;
  member_contribution_amount: number;
  is_contribution_recurring: boolean;
  amount_mode?: "ceiling" | "objective";
  aid_ceiling_amount: number;
  objective_amount?: number;
  max_claims_per_member_per_year: number;
  declaration_delay_days: number;
}

interface Caisse {
  id: string;
  name: string;
  slug: string;
  category: string;
  fund_kind?: string | null;
}

/**
 * Manager autonome des types d'aides sociales : toggle d'activation + liste
 * + form. Partagé entre /dashboard/config/aids et l'étape 5 du wizard.
 *
 * Configuration simplifiée d'un type : un NOM, une SOURCE (caisse individuelle
 * d'assurance OU caisse collective de secours) et un MONTANT à donner.
 */
export function AidTypesManager({ association }: { association: Association }) {
  const t = useTranslations("configAids");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const enabled = Boolean(
    (association.config as { aids?: { enabled?: boolean } })?.aids?.enabled,
  );

  const { data: types = [], isLoading } = useQuery<AidType[]>({
    queryKey: ["aid-types", association.id],
    queryFn: () => aidTypesApi.list(association.id),
  });

  const { data: caisses = [] } = useQuery<Caisse[]>({
    queryKey: ["caisses", association.id],
    queryFn: () => caissesApi.list(association.id),
  });
  // Caisses collectives (secours) : COLLECTIVE, hors projet/tontine.
  const collectiveCaisses = useMemo(
    () =>
      caisses.filter(
        (c) => c.category === "collective" && c.fund_kind !== "tontine",
      ),
    [caisses],
  );
  // Caisses individuelles (assurance) : PERSONAL, un solde par membre.
  const personalCaisses = useMemo(
    () => caisses.filter((c) => c.category === "personal"),
    [caisses],
  );

  const toggleEnabled = useMutation({
    mutationFn: (next: boolean) =>
      associationsApi.update(association.id, {
        config: {
          ...association.config,
          aids: { ...((association.config as { aids?: object })?.aids ?? {}), enabled: next },
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["associations"] });
      toast.success(t("toggleSaved"));
    },
    onError: () => toast.error(tCommon("error")),
  });

  const remove = useMutation({
    mutationFn: (id: string) => aidTypesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aid-types", association.id] });
      toast.success(t("typeDeleted"));
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? tCommon("error"));
    },
  });

  const [showForm, setShowForm] = useState(false);

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Power className="h-5 w-5" />
            </div>
            <div>
              <p className="font-semibold">{t("enableTitle")}</p>
              <p className="text-sm text-muted-foreground">{t("enableHint")}</p>
            </div>
          </div>
          <Switch
            checked={enabled}
            disabled={toggleEnabled.isPending}
            onCheckedChange={(v) => toggleEnabled.mutate(v)}
          />
        </CardContent>
      </Card>

      {!enabled && <ConfigPreview intent="warning">{t("disabledPreview")}</ConfigPreview>}

      {enabled && (
        <>
          <ConfigPreview intent="info">{t("intro")}</ConfigPreview>

          {isLoading ? (
            <Skeleton className="h-32 w-full rounded-xl" />
          ) : types.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
                <HeartHandshake className="h-12 w-12 text-muted-foreground" />
                <p className="font-medium">{t("emptyTitle")}</p>
                <p className="text-sm text-muted-foreground">{t("emptyDesc")}</p>
              </CardContent>
            </Card>
          ) : (
            <ul className="space-y-2">
              {types.map((at) => {
                const isInsurance = at.funding_mode === "member_insurance";
                return (
                  <li
                    key={at.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-4"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <HeartHandshake className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-semibold">{at.name}</p>
                          {!at.is_active && (
                            <Badge variant="outline" className="text-[10px]">
                              {t("inactive")}
                            </Badge>
                          )}
                          <Badge variant="secondary" className="text-[10px]">
                            {isInsurance ? t("sourceIndividual") : t("sourceCollective")}
                          </Badge>
                        </div>
                        {at.description && (
                          <p className="text-sm text-muted-foreground">{at.description}</p>
                        )}
                        <p className="mt-1 text-xs text-muted-foreground">
                          {t("source")}:{" "}
                          <span className="font-medium">
                            {isInsurance
                              ? at.insurance_caisse_name ?? t("sourceIndividual")
                              : at.source_caisse_name ?? t("sourceCollective")}
                          </span>
                          {" · "}
                          {t("amountToGive")}:{" "}
                          <span className="font-medium">{at.aid_ceiling_amount}</span>
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove.mutate(at.id)}
                      disabled={remove.isPending}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}

          {showForm ? (
            <AidTypeForm
              associationId={association.id}
              currency={association.currency}
              collectiveCaisses={collectiveCaisses}
              personalCaisses={personalCaisses}
              onCancel={() => setShowForm(false)}
              onCreated={() => {
                setShowForm(false);
                queryClient.invalidateQueries({ queryKey: ["aid-types", association.id] });
              }}
            />
          ) : (
            <Button
              variant="outline"
              onClick={() => setShowForm(true)}
              className="w-full gap-2"
            >
              <Plus className="h-4 w-4" />
              {t("addType")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function AidTypeForm({
  associationId,
  currency,
  collectiveCaisses,
  personalCaisses,
  onCancel,
  onCreated,
}: {
  associationId: string;
  currency: string;
  collectiveCaisses: Caisse[];
  personalCaisses: Caisse[];
  onCancel: () => void;
  onCreated: () => void;
}) {
  const t = useTranslations("configAids");
  const tCommon = useTranslations("common");
  const fmt = useFormatters(currency);

  // Source : "individual" (caisse perso d'assurance) ou "collective" (secours).
  type SourceMode = "individual" | "collective";

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>(
    collectiveCaisses.length > 0 ? "collective" : "individual",
  );
  const [collectiveCaisse, setCollectiveCaisse] = useState(collectiveCaisses[0]?.id ?? "");
  const [personalCaisse, setPersonalCaisse] = useState(personalCaisses[0]?.id ?? "");
  const [amount, setAmount] = useState("100000");

  const amountNum = parseInt(amount, 10) || 0;

  const create = useMutation({
    mutationFn: () =>
      aidTypesApi.create({
        association_id: associationId,
        funding_mode: sourceMode === "individual" ? "member_insurance" : "fixed",
        source_caisse_id: sourceMode === "collective" ? collectiveCaisse : undefined,
        insurance_caisse_id: sourceMode === "individual" ? personalCaisse : undefined,
        name: name.trim(),
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        description: description.trim() || undefined,
        aid_ceiling_amount: amountNum,
      }),
    onSuccess: () => onCreated(),
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? t("createError"));
    },
  });

  const noCaisse =
    sourceMode === "collective"
      ? collectiveCaisses.length === 0
      : personalCaisses.length === 0;

  return (
    <div className="space-y-4 rounded-lg border-2 border-primary/30 bg-primary/5 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <HelpField label={t("typeName")} required example={t("typeNameExample")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </HelpField>
        <HelpField label={t("typeDescription")}>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </HelpField>
      </div>

      <section className="space-y-3 rounded-md border border-border bg-card p-3">
        <h3 className="text-sm font-semibold">{t("sourceTitle")}</h3>

        <HelpField label={t("sourceModeLabel")} hint={t("sourceModeHint")} required>
          <Select value={sourceMode} onValueChange={(v) => setSourceMode(v as SourceMode)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="collective">{t("sourceCollective")}</SelectItem>
              <SelectItem value="individual">{t("sourceIndividual")}</SelectItem>
            </SelectContent>
          </Select>
        </HelpField>

        {sourceMode === "collective" ? (
          <HelpField label={t("collectiveCaisse")} hint={t("collectiveCaisseHint")} required>
            {collectiveCaisses.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
                {t("noCollectiveCaisse")}
              </p>
            ) : (
              <Select value={collectiveCaisse} onValueChange={setCollectiveCaisse}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {collectiveCaisses.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </HelpField>
        ) : (
          <HelpField label={t("individualCaisse")} hint={t("individualCaisseHint")} required>
            {personalCaisses.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
                {t("noPersonalCaisse")}
              </p>
            ) : (
              <Select value={personalCaisse} onValueChange={setPersonalCaisse}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {personalCaisses.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </HelpField>
        )}
      </section>

      <HelpField
        label={t("amountToGive")}
        hint={t("amountToGiveHint")}
        example={t("amountToGiveExample", { amount: fmt.currency(100000) })}
        required
      >
        <Input type="number" min={0} value={amount} onChange={(e) => setAmount(e.target.value)} />
      </HelpField>

      <ConfigPreview intent="success">
        <p className="font-medium">{t("previewTitle")}</p>
        <p className="mt-1">
          {sourceMode === "collective"
            ? t("previewCollective", { amount: fmt.currency(amountNum) })
            : t("previewIndividual", { amount: fmt.currency(amountNum) })}
        </p>
      </ConfigPreview>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          {tCommon("cancel")}
        </Button>
        <Button
          onClick={() => create.mutate()}
          disabled={
            create.isPending ||
            !name.trim() ||
            amountNum <= 0 ||
            noCaisse ||
            (sourceMode === "collective" && !collectiveCaisse) ||
            (sourceMode === "individual" && !personalCaisse)
          }
          className="gap-2"
        >
          {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {tCommon("create")}
        </Button>
      </div>
    </div>
  );
}
