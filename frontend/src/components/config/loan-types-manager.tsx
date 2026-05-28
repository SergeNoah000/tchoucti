"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HandCoins, Loader2, Plus, Power, Trash2 } from "lucide-react";
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
import { associationsApi, caissesApi, loanTypesApi } from "@/lib/api";
import type { Association } from "@/lib/types";

interface LoanType {
  id: string;
  source_caisse_id: string;
  source_caisse_name?: string | null;
  name: string;
  slug: string;
  description?: string | null;
  is_active: boolean;
  eligibility_min_seniority_months: number;
  eligibility_no_default: boolean;
  max_simultaneous: number;
  max_per_year: number;
  interest_rate_pct: string;
  late_fee_pct: string;
  max_duration_months: number;
}

interface Caisse {
  id: string;
  name: string;
  slug: string;
  category: string;
}

/**
 * Manager autonome des types de prêts : toggle d'activation + liste + form.
 * Partagé entre la page /dashboard/config/loans et l'étape 4 du wizard
 * d'onboarding. Lit l'état `loans.enabled` depuis association.config.
 */
export function LoanTypesManager({ association }: { association: Association }) {
  const t = useTranslations("configLoans");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const enabled = Boolean(
    (association.config as { loans?: { enabled?: boolean } })?.loans?.enabled,
  );

  const { data: types = [], isLoading } = useQuery<LoanType[]>({
    queryKey: ["loan-types", association.id],
    queryFn: () => loanTypesApi.list(association.id),
  });

  const { data: caisses = [] } = useQuery<Caisse[]>({
    queryKey: ["caisses", association.id],
    queryFn: () => caissesApi.list(association.id),
  });
  const sourceCaisses = useMemo(
    () => caisses.filter((c) => c.category !== "project"),
    [caisses],
  );

  const toggleEnabled = useMutation({
    mutationFn: (next: boolean) =>
      associationsApi.update(association.id, {
        config: {
          ...association.config,
          loans: { ...((association.config as { loans?: object })?.loans ?? {}), enabled: next },
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["associations"] });
      toast.success(t("toggleSaved"));
    },
    onError: () => toast.error(tCommon("error")),
  });

  const remove = useMutation({
    mutationFn: (id: string) => loanTypesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["loan-types", association.id] });
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
                <HandCoins className="h-12 w-12 text-muted-foreground" />
                <p className="font-medium">{t("emptyTitle")}</p>
                <p className="text-sm text-muted-foreground">{t("emptyDesc")}</p>
              </CardContent>
            </Card>
          ) : (
            <ul className="space-y-2">
              {types.map((tt) => (
                <li
                  key={tt.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-4"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <HandCoins className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold">{tt.name}</p>
                        {!tt.is_active && (
                          <Badge variant="outline" className="text-[10px]">
                            {t("inactive")}
                          </Badge>
                        )}
                      </div>
                      {tt.description && (
                        <p className="text-sm text-muted-foreground">{tt.description}</p>
                      )}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t("source")}: <span className="font-medium">{tt.source_caisse_name}</span>
                        {" · "}
                        {t("rate")}: <span className="font-medium">{tt.interest_rate_pct}%/mois</span>
                        {" · "}
                        {t("maxDuration")}: <span className="font-medium">{tt.max_duration_months}m</span>
                        {" · "}
                        {t("simultaneous")}: <span className="font-medium">{tt.max_simultaneous}</span>
                        {" · "}
                        {t("perYear")}: <span className="font-medium">{tt.max_per_year}/an</span>
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove.mutate(tt.id)}
                    disabled={remove.isPending}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {showForm ? (
            <LoanTypeForm
              associationId={association.id}
              caisses={sourceCaisses}
              onCancel={() => setShowForm(false)}
              onCreated={() => {
                setShowForm(false);
                queryClient.invalidateQueries({ queryKey: ["loan-types", association.id] });
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

function LoanTypeForm({
  associationId,
  caisses,
  onCancel,
  onCreated,
}: {
  associationId: string;
  caisses: Caisse[];
  onCancel: () => void;
  onCreated: () => void;
}) {
  const t = useTranslations("configLoans");
  const tCommon = useTranslations("common");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState(caisses[0]?.id ?? "");
  const [rate, setRate] = useState("5.0");
  const [lateFee, setLateFee] = useState("1.0");
  const [maxDuration, setMaxDuration] = useState("12");
  const [minSeniority, setMinSeniority] = useState("0");
  const [maxSimultaneous, setMaxSimultaneous] = useState("1");
  const [maxPerYear, setMaxPerYear] = useState("1");
  const [noDefault, setNoDefault] = useState(true);

  const create = useMutation({
    mutationFn: () =>
      loanTypesApi.create({
        association_id: associationId,
        source_caisse_id: source,
        name: name.trim(),
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        description: description.trim() || undefined,
        interest_rate_pct: rate,
        late_fee_pct: lateFee,
        max_duration_months: parseInt(maxDuration, 10) || 12,
        eligibility_min_seniority_months: parseInt(minSeniority, 10) || 0,
        max_simultaneous: parseInt(maxSimultaneous, 10) || 1,
        max_per_year: parseInt(maxPerYear, 10) || 1,
        eligibility_no_default: noDefault,
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
        <h3 className="text-sm font-semibold">{t("financialTitle")}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <HelpField label={t("rate")} example={t("rateExample")}>
            <Input value={rate} onChange={(e) => setRate(e.target.value)} />
          </HelpField>
          <HelpField label={t("lateFee")} example={t("lateFeeExample")}>
            <Input value={lateFee} onChange={(e) => setLateFee(e.target.value)} />
          </HelpField>
          <HelpField label={t("maxDuration")} example={t("maxDurationExample")}>
            <Input
              type="number"
              min={1}
              max={120}
              value={maxDuration}
              onChange={(e) => setMaxDuration(e.target.value)}
            />
          </HelpField>
        </div>
      </section>

      <section className="space-y-3 rounded-md border border-border bg-card p-3">
        <h3 className="text-sm font-semibold">{t("eligibilityTitle")}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <HelpField label={t("minSeniority")} hint={t("minSeniorityHint")}>
            <Input
              type="number"
              min={0}
              value={minSeniority}
              onChange={(e) => setMinSeniority(e.target.value)}
            />
          </HelpField>
          <HelpField label={t("maxSimultaneous")} hint={t("maxSimultaneousHint")}>
            <Input
              type="number"
              min={1}
              value={maxSimultaneous}
              onChange={(e) => setMaxSimultaneous(e.target.value)}
            />
          </HelpField>
          <HelpField label={t("maxPerYear")} hint={t("maxPerYearHint")}>
            <Input
              type="number"
              min={1}
              value={maxPerYear}
              onChange={(e) => setMaxPerYear(e.target.value)}
            />
          </HelpField>
        </div>
        <label className="flex cursor-pointer items-center justify-between gap-3 rounded-md bg-muted/30 p-2.5">
          <div>
            <p className="text-sm font-medium">{t("noDefault")}</p>
            <p className="text-xs text-muted-foreground">{t("noDefaultHint")}</p>
          </div>
          <Switch checked={noDefault} onCheckedChange={setNoDefault} />
        </label>
      </section>

      <ConfigPreview intent="success">
        <p className="font-medium">{t("previewTitle")}</p>
        <p className="mt-1">
          {t("previewText", {
            rate,
            duration: maxDuration,
            simultaneous: maxSimultaneous,
            year: maxPerYear,
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
