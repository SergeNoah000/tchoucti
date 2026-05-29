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
  source_caisse_id: string;
  source_caisse_name?: string | null;
  name: string;
  slug: string;
  description?: string | null;
  is_active: boolean;
  member_contribution_amount: number;
  is_contribution_recurring: boolean;
  aid_ceiling_amount: number;
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
  const sourceCaisses = useMemo(
    () => caisses.filter((c) => c.category !== "project" && c.fund_kind !== "tontine"),
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
              {types.map((at) => (
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
                        {at.is_contribution_recurring && (
                          <Badge variant="secondary" className="text-[10px]">
                            {t("recurring")}
                          </Badge>
                        )}
                      </div>
                      {at.description && (
                        <p className="text-sm text-muted-foreground">{at.description}</p>
                      )}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t("source")}: <span className="font-medium">{at.source_caisse_name}</span>
                        {" · "}
                        {t("contribution")}: <span className="font-medium">{at.member_contribution_amount}</span>
                        {" · "}
                        {t("ceiling")}: <span className="font-medium">{at.aid_ceiling_amount}</span>
                        {" · "}
                        {t("maxClaims")}: <span className="font-medium">{at.max_claims_per_member_per_year}/an</span>
                        {" · "}
                        {t("delay")}: <span className="font-medium">{at.declaration_delay_days}j</span>
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
              ))}
            </ul>
          )}

          {showForm ? (
            <AidTypeForm
              associationId={association.id}
              currency={association.currency}
              caisses={sourceCaisses}
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
              disabled={sourceCaisses.length === 0}
            >
              <Plus className="h-4 w-4" />
              {t("addType")}
            </Button>
          )}
          {sourceCaisses.length === 0 && (
            <ConfigPreview intent="warning">{t("noSourceCaisse")}</ConfigPreview>
          )}
        </>
      )}
    </div>
  );
}

function AidTypeForm({
  associationId,
  currency,
  caisses,
  onCancel,
  onCreated,
}: {
  associationId: string;
  currency: string;
  caisses: Caisse[];
  onCancel: () => void;
  onCreated: () => void;
}) {
  const t = useTranslations("configAids");
  const tCommon = useTranslations("common");
  const fmt = useFormatters(currency);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState(caisses[0]?.id ?? "");
  const [contribution, setContribution] = useState("2000");
  const [recurring, setRecurring] = useState(false);
  const [ceiling, setCeiling] = useState("100000");
  const [maxClaims, setMaxClaims] = useState("1");
  const [delay, setDelay] = useState("30");

  const create = useMutation({
    mutationFn: () =>
      aidTypesApi.create({
        association_id: associationId,
        source_caisse_id: source,
        name: name.trim(),
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        description: description.trim() || undefined,
        member_contribution_amount: parseInt(contribution, 10) || 0,
        is_contribution_recurring: recurring,
        aid_ceiling_amount: parseInt(ceiling, 10) || 0,
        max_claims_per_member_per_year: parseInt(maxClaims, 10) || 1,
        declaration_delay_days: parseInt(delay, 10) || 30,
      }),
    onSuccess: () => onCreated(),
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? t("createError"));
    },
  });

  return (
    <div className="space-y-4 rounded-lg border-2 border-primary/30 bg-primary/5 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <HelpField label={t("typeName")} required example={t("typeNameExample")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </HelpField>
        <HelpField label={t("sourceCaisse")} hint={t("sourceCaisseHint")} required>
          <Select value={source} onValueChange={setSource}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {caisses.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </HelpField>
        <HelpField label={t("typeDescription")} className="sm:col-span-2">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </HelpField>
      </div>

      <section className="space-y-3 rounded-md border border-border bg-card p-3">
        <h3 className="text-sm font-semibold">{t("contributionTitle")}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <HelpField label={t("contribution")} example={t("contributionExample", { amount: fmt.currency(2000) })}>
            <Input
              type="number"
              min={0}
              value={contribution}
              onChange={(e) => setContribution(e.target.value)}
            />
          </HelpField>
          <HelpField label={t("ceiling")} example={t("ceilingExample", { amount: fmt.currency(100000) })}>
            <Input type="number" min={0} value={ceiling} onChange={(e) => setCeiling(e.target.value)} />
          </HelpField>
        </div>
        <label className="flex cursor-pointer items-center justify-between gap-3 rounded-md bg-muted/30 p-2.5">
          <div>
            <p className="text-sm font-medium">{t("recurringTitle")}</p>
            <p className="text-xs text-muted-foreground">{t("recurringHint")}</p>
          </div>
          <Switch checked={recurring} onCheckedChange={setRecurring} />
        </label>
      </section>

      <section className="space-y-3 rounded-md border border-border bg-card p-3">
        <h3 className="text-sm font-semibold">{t("constraintsTitle")}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <HelpField label={t("maxClaims")} hint={t("maxClaimsHint")}>
            <Input
              type="number"
              min={1}
              max={20}
              value={maxClaims}
              onChange={(e) => setMaxClaims(e.target.value)}
            />
          </HelpField>
          <HelpField label={t("delay")} hint={t("delayHint")}>
            <Input
              type="number"
              min={0}
              max={365}
              value={delay}
              onChange={(e) => setDelay(e.target.value)}
            />
          </HelpField>
        </div>
      </section>

      <ConfigPreview intent="success">
        <p className="font-medium">{t("previewTitle")}</p>
        <p className="mt-1">
          {t("previewText", {
            contribution: fmt.currency(parseInt(contribution, 10) || 0),
            ceiling: fmt.currency(parseInt(ceiling, 10) || 0),
            year: maxClaims,
            delay,
          })}
        </p>
      </ConfigPreview>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          {tCommon("cancel")}
        </Button>
        <Button
          onClick={() => create.mutate()}
          disabled={create.isPending || !name.trim() || !source}
          className="gap-2"
        >
          {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {tCommon("create")}
        </Button>
      </div>
    </div>
  );
}
