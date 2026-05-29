"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  Loader2,
  Plus,
  Repeat,
  Trash2,
  Upload,
  Wallet,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

import {
  associationsApi,
  caissesApi,
  setupApi,
  tontinesApi,
} from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type { Association, Tontine } from "@/lib/types";
import { HelpField, ConfigPreview } from "@/components/onboarding/help-field";
import { StepIndicator, WizardCard, type WizardStep } from "@/components/onboarding/wizard";
import { LoanTypesManager } from "@/components/config/loan-types-manager";
import { AidTypesManager } from "@/components/config/aid-types-manager";
import { CreateTontineDialog } from "@/components/tontines/create-cycle-dialog";

const STEP_KEYS = ["association", "caisses", "tontines", "loans", "aids"] as const;
type StepKey = (typeof STEP_KEYS)[number];

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  const { data: setupState } = useQuery<{ setup_complete: boolean; setup_step: number }>({
    queryKey: ["setup-state", association?.id],
    queryFn: () => setupApi.getState(association!.id),
    enabled: !!association?.id,
  });

  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    if (typeof setupState?.setup_step === "number") {
      setCurrentStep(Math.min(setupState.setup_step, STEP_KEYS.length - 1));
    }
  }, [setupState?.setup_step]);

  const steps: WizardStep[] = useMemo(
    () => [
      { key: "association", title: t("stepAssociation"), required: true },
      { key: "caisses", title: t("stepCaisses"), required: true },
      { key: "tontines", title: t("stepTontines") },
      { key: "loans", title: t("stepLoans") },
      { key: "aids", title: t("stepAids") },
    ],
    [t],
  );

  const advance = useMutation({
    mutationFn: (payload: { step?: number; complete?: boolean }) =>
      setupApi.advance(association!.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["setup-state", association?.id] });
    },
  });

  const finish = async () => {
    await advance.mutateAsync({ complete: true });
    toast.success(t("welcome"));
    router.replace("/dashboard");
  };

  if (!canConfigureAssociation(user)) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("notAdmin")}</p>
      </div>
    );
  }

  if (!association || !setupState) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 py-8">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  const stepKey: StepKey = STEP_KEYS[currentStep];

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </header>

      <StepIndicator steps={steps} currentIndex={currentStep} />

      {stepKey === "association" && (
        <StepAssociation
          association={association}
          onNext={async () => {
            await advance.mutateAsync({ step: 1 });
            setCurrentStep(1);
          }}
        />
      )}
      {stepKey === "caisses" && (
        <StepCaisses
          association={association}
          onBack={() => setCurrentStep(0)}
          onNext={async () => {
            await advance.mutateAsync({ step: 2 });
            setCurrentStep(2);
          }}
        />
      )}
      {stepKey === "tontines" && (
        <TontinesLinkStep
          association={association}
          onBack={() => setCurrentStep(1)}
          onSkip={async () => {
            await advance.mutateAsync({ step: 3 });
            setCurrentStep(3);
          }}
        />
      )}
      {stepKey === "loans" && (
        <LoansLinkStep
          association={association}
          onBack={() => setCurrentStep(2)}
          onSkip={async () => {
            await advance.mutateAsync({ step: 4 });
            setCurrentStep(4);
          }}
        />
      )}
      {stepKey === "aids" && (
        <AidsLinkStep
          association={association}
          onBack={() => setCurrentStep(3)}
          finishLabel={t("finish")}
          onSkip={finish}
        />
      )}
    </div>
  );
}

// ── Step 1 : Association profile + critères + frais + docs ────────────────

function StepAssociation({
  association,
  onNext,
}: {
  association: Association;
  onNext: () => Promise<void>;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const [name, setName] = useState(association.name);
  const [type, setType] = useState(association.type ?? "association");
  const [currency, setCurrency] = useState(association.currency || "XAF");
  const [city, setCity] = useState(association.city || "");
  const [address, setAddress] = useState(association.address || "");
  const [phone, setPhone] = useState(association.phone || "");
  const [description, setDescription] = useState(association.description || "");
  const [fee, setFee] = useState(
    (association.config as { registration_fee?: number })?.registration_fee?.toString() ?? "0",
  );

  type Criterion = {
    id: string;
    type: string;
    label: string;
    value: string;
    is_required: boolean;
  };
  const { data: criteria = [], refetch: refetchCriteria } = useQuery<Criterion[]>({
    queryKey: ["criteria", association.id],
    queryFn: () => setupApi.listCriteria(association.id),
  });

  type Doc = {
    id: string;
    title: string;
    kind: string;
    file_url: string;
    file_name: string;
    file_size: number;
  };
  const { data: documents = [], refetch: refetchDocs } = useQuery<Doc[]>({
    queryKey: ["documents", association.id],
    queryFn: () => setupApi.listDocuments(association.id),
  });

  const saveProfile = useMutation({
    mutationFn: () =>
      associationsApi.update(association.id, {
        name: name.trim(),
        type,
        currency,
        city: city.trim() || undefined,
        address: address.trim() || undefined,
        phone: phone.trim() || undefined,
        description: description.trim() || undefined,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["associations"] }),
  });

  const saveFee = useMutation({
    mutationFn: () => setupApi.setRegistrationFee(association.id, parseInt(fee, 10) || 0),
  });

  const goNext = async () => {
    if (name.trim().length < 2) {
      toast.error(t("errorName"));
      return;
    }
    await saveProfile.mutateAsync();
    await saveFee.mutateAsync();
    await onNext();
  };

  return (
    <WizardCard
      title={t("stepAssociationTitle")}
      description={t("stepAssociationDesc")}
      footer={
        <>
          <span className="text-xs text-muted-foreground">{t("required")}</span>
          <Button onClick={goNext} disabled={saveProfile.isPending} className="gap-2">
            {saveProfile.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {tCommon("next")}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </>
      }
    >
      <ConfigPreview intent="info">
        <Building2 className="mr-1.5 inline h-4 w-4" />
        {t("introAssociation")}
      </ConfigPreview>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <HelpField label={t("name")} required>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </HelpField>
        <HelpField label={t("type")} hint={t("typeHint")}>
          <Select value={type} onValueChange={(v) => setType(v as Association["type"])}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="association">{t("typeAssociation")}</SelectItem>
              <SelectItem value="tontine">{t("typeTontine")}</SelectItem>
              <SelectItem value="mutuelle">{t("typeMutuelle")}</SelectItem>
              <SelectItem value="cooperative">{t("typeCooperative")}</SelectItem>
              <SelectItem value="autre">{t("typeAutre")}</SelectItem>
            </SelectContent>
          </Select>
        </HelpField>
        <HelpField label={t("currency")} example={t("currencyExample")}>
          <Input
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))}
            maxLength={3}
          />
        </HelpField>
        <HelpField label={t("phone")}>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
        </HelpField>
        <HelpField label={t("city")} className="sm:col-span-1">
          <Input value={city} onChange={(e) => setCity(e.target.value)} />
        </HelpField>
        <HelpField label={t("address")} className="sm:col-span-1">
          <Input value={address} onChange={(e) => setAddress(e.target.value)} />
        </HelpField>
        <HelpField label={t("description")} className="sm:col-span-2">
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </HelpField>
      </div>

      {/* Frais d'inscription */}
      <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
        <h3 className="text-sm font-semibold">{t("feeTitle")}</h3>
        <HelpField
          label={t("feeAmount")}
          hint={t("feeHint")}
          example={t("feeExample")}
        >
          <Input
            type="number"
            min={0}
            value={fee}
            onChange={(e) => setFee(e.target.value)}
            placeholder="0"
          />
        </HelpField>
        {parseInt(fee, 10) > 0 && (
          <ConfigPreview intent="success">
            {t("feePreview", { amount: parseInt(fee, 10), currency })}
          </ConfigPreview>
        )}
      </section>

      {/* Critères d'adhésion */}
      <CriteriaSection
        associationId={association.id}
        criteria={criteria}
        onChanged={refetchCriteria}
      />

      {/* Documents légaux */}
      <DocumentsSection
        associationId={association.id}
        documents={documents}
        onChanged={refetchDocs}
      />
    </WizardCard>
  );
}

function CriteriaSection({
  associationId,
  criteria,
  onChanged,
}: {
  associationId: string;
  criteria: Array<{ id: string; type: string; label: string; value: string; is_required: boolean }>;
  onChanged: () => void;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  const [type, setType] = useState("age_min");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [isRequired, setIsRequired] = useState(true);

  const add = useMutation({
    mutationFn: () =>
      setupApi.addCriterion(associationId, {
        type,
        label: label.trim() || t(`criterion_${type}` as never, { default: type } as never),
        value: value.trim(),
        is_required: isRequired,
      }),
    onSuccess: () => {
      onChanged();
      setLabel("");
      setValue("");
    },
    onError: () => toast.error(tCommon("error")),
  });

  const remove = useMutation({
    mutationFn: (id: string) => setupApi.deleteCriterion(associationId, id),
    onSuccess: () => onChanged(),
  });

  return (
    <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
      <div>
        <h3 className="text-sm font-semibold">{t("criteriaTitle")}</h3>
        <p className="text-xs text-muted-foreground">{t("criteriaHint")}</p>
      </div>

      {criteria.length > 0 && (
        <ul className="space-y-1.5">
          {criteria.map((c) => (
            <li
              key={c.id}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm"
            >
              <div className="flex min-w-0 items-center gap-2">
                <Badge variant="outline">{c.type}</Badge>
                <span className="truncate font-medium">{c.label}:</span>
                <span className="truncate text-muted-foreground">{c.value}</span>
                {c.is_required && (
                  <span className="text-[10px] uppercase tracking-wide text-destructive/70">
                    {t("required")}
                  </span>
                )}
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => remove.mutate(c.id)}
                disabled={remove.isPending}
              >
                <X className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[150px_1fr_1fr_auto] sm:items-end">
        <HelpField label={t("criterionType")}>
          <Select value={type} onValueChange={setType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="age_min">{t("criterion_age_min")}</SelectItem>
              <SelectItem value="age_max">{t("criterion_age_max")}</SelectItem>
              <SelectItem value="gender">{t("criterion_gender")}</SelectItem>
              <SelectItem value="location">{t("criterion_location")}</SelectItem>
              <SelectItem value="profession">{t("criterion_profession")}</SelectItem>
              <SelectItem value="other">{t("criterion_other")}</SelectItem>
            </SelectContent>
          </Select>
        </HelpField>
        <HelpField label={t("criterionLabel")}>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("criterion_" + type as never)} />
        </HelpField>
        <HelpField label={t("criterionValue")} example={t(`criterion_${type}_example` as never, { default: "" } as never)}>
          <Input value={value} onChange={(e) => setValue(e.target.value)} />
        </HelpField>
        <Button
          variant="outline"
          onClick={() => value.trim() && add.mutate()}
          disabled={add.isPending || !value.trim()}
          className="gap-1.5"
        >
          <Plus className="h-4 w-4" />
          {tCommon("create")}
        </Button>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <Switch checked={isRequired} onCheckedChange={setIsRequired} />
        {t("criterionRequired")}
      </label>
    </section>
  );
}

function DocumentsSection({
  associationId,
  documents,
  onChanged,
}: {
  associationId: string;
  documents: Array<{ id: string; title: string; kind: string; file_url: string; file_name: string; file_size: number }>;
  onChanged: () => void;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("statuts");
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async () => {
    if (!file || !title.trim()) {
      toast.error(t("docMissing"));
      return;
    }
    setPending(true);
    try {
      await setupApi.uploadDocument(associationId, file, title.trim(), kind);
      setTitle("");
      setFile(null);
      onChanged();
      toast.success(t("docUploaded"));
    } catch {
      toast.error(tCommon("error"));
    } finally {
      setPending(false);
    }
  };

  const remove = useMutation({
    mutationFn: (id: string) => setupApi.deleteDocument(associationId, id),
    onSuccess: () => onChanged(),
  });

  return (
    <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
      <div>
        <h3 className="text-sm font-semibold">{t("docsTitle")}</h3>
        <p className="text-xs text-muted-foreground">{t("docsHint")}</p>
      </div>

      {documents.length > 0 && (
        <ul className="space-y-1.5">
          {documents.map((d) => (
            <li
              key={d.id}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm"
            >
              <a
                href={d.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-w-0 items-center gap-2 hover:underline"
              >
                <Badge variant="outline">{d.kind}</Badge>
                <span className="truncate font-medium">{d.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  ({Math.round(d.file_size / 1024)} KB)
                </span>
              </a>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => remove.mutate(d.id)}
                disabled={remove.isPending}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[200px_1fr_auto] sm:items-end">
        <HelpField label={t("docKind")}>
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="statuts">{t("doc_statuts")}</SelectItem>
              <SelectItem value="roi">{t("doc_roi")}</SelectItem>
              <SelectItem value="recepisse">{t("doc_recepisse")}</SelectItem>
              <SelectItem value="autre">{t("doc_autre")}</SelectItem>
            </SelectContent>
          </Select>
        </HelpField>
        <HelpField label={t("docTitle")}>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("docTitlePlaceholder")}
          />
        </HelpField>
        <div className="space-y-1.5">
          <label
            htmlFor="doc-file"
            className="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50"
          >
            <Upload className="h-4 w-4" />
            {file ? file.name : t("docPickFile")}
          </label>
          <input
            id="doc-file"
            type="file"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
      </div>
      <Button onClick={submit} disabled={pending || !file || !title.trim()} className="gap-2">
        {pending && <Loader2 className="h-4 w-4 animate-spin" />}
        {t("docUpload")}
      </Button>
    </section>
  );
}

// ── Step 2 : Caisses ───────────────────────────────────────────────────────

function StepCaisses({
  association,
  onBack,
  onNext,
}: {
  association: Association;
  onBack: () => void;
  onNext: () => Promise<void>;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  type Caisse = {
    id: string;
    name: string;
    slug: string;
    category: string;
    is_system: boolean;
    is_recurring: boolean;
    recurring_amount: number;
    has_ceiling: boolean;
    ceiling_amount: number;
    has_objective: boolean;
    objective_amount: number;
  };
  const { data: caisses = [] } = useQuery<Caisse[]>({
    queryKey: ["caisses", association.id],
    queryFn: () => caissesApi.list(association.id),
  });

  const [showForm, setShowForm] = useState(false);

  return (
    <WizardCard
      title={t("stepCaissesTitle")}
      description={t("stepCaissesDesc")}
      footer={
        <>
          <Button variant="outline" onClick={onBack} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            {tCommon("previous")}
          </Button>
          <Button onClick={onNext} className="gap-2">
            {tCommon("next")}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </>
      }
    >
      <ConfigPreview intent="info">
        <Wallet className="mr-1.5 inline h-4 w-4" />
        {t("introCaisses")}
      </ConfigPreview>

      <ul className="space-y-2">
        {caisses.map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3"
          >
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Wallet className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 truncate text-sm font-semibold">
                  <span className="truncate">{c.name}</span>
                  {c.is_system && (
                    <Badge variant="secondary" className="text-[10px]">
                      {t("system")}
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-[10px]">
                    {t(`cat_${c.category}` as never)}
                  </Badge>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {c.is_recurring
                    ? t("caissePreviewRecurring", { amount: c.recurring_amount })
                    : c.has_objective
                      ? t("caissePreviewObjective", { amount: c.objective_amount })
                      : t("caissePreviewFree")}
                </p>
              </div>
            </div>
            {!c.is_system && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() =>
                  caissesApi.remove(c.id).then(() =>
                    queryClient.invalidateQueries({ queryKey: ["caisses", association.id] }),
                  )
                }
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            )}
          </li>
        ))}
      </ul>

      {showForm ? (
        <CaisseForm
          associationId={association.id}
          onCancel={() => setShowForm(false)}
          onCreated={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["caisses", association.id] });
          }}
        />
      ) : (
        <Button variant="outline" onClick={() => setShowForm(true)} className="w-full gap-2">
          <Plus className="h-4 w-4" />
          {t("caisseAdd")}
        </Button>
      )}
    </WizardCard>
  );
}

function CaisseForm({
  associationId,
  onCancel,
  onCreated,
}: {
  associationId: string;
  onCancel: () => void;
  onCreated: () => void;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<"collective" | "project" | "personal">("collective");
  const [recurring, setRecurring] = useState(false);
  const [recurringAmount, setRecurringAmount] = useState("");
  const [memberRequired, setMemberRequired] = useState(false);
  const [memberRequiredAmount, setMemberRequiredAmount] = useState("");
  const [hasObjective, setHasObjective] = useState(false);
  const [objectiveAmount, setObjectiveAmount] = useState("");
  const [objectiveDeadline, setObjectiveDeadline] = useState("");

  const create = useMutation({
    mutationFn: () =>
      caissesApi.create({
        association_id: associationId,
        name: name.trim(),
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        description: description.trim() || undefined,
        category,
        is_recurring: recurring,
        recurring_amount: recurring ? parseInt(recurringAmount, 10) || 0 : 0,
        is_member_required: memberRequired,
        member_required_amount: memberRequired ? parseInt(memberRequiredAmount, 10) || 0 : 0,
        has_objective: category === "project" || hasObjective,
        objective_amount: hasObjective || category === "project" ? parseInt(objectiveAmount, 10) || 0 : 0,
        objective_deadline: objectiveDeadline || undefined,
      }),
    onSuccess: () => onCreated(),
    onError: () => toast.error(t("caisseCreateError")),
  });

  return (
    <div className="space-y-4 rounded-lg border-2 border-primary/30 bg-primary/5 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <HelpField label={t("caisseName")} required example={t("caisseNameExample")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </HelpField>
        <HelpField label={t("caisseCategory")} hint={t("caisseCategoryHint")}>
          <Select value={category} onValueChange={(v) => setCategory(v as typeof category)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="collective">{t("cat_collective")} — {t("cat_collective_hint")}</SelectItem>
              <SelectItem value="project">{t("cat_project")} — {t("cat_project_hint")}</SelectItem>
              <SelectItem value="personal">{t("cat_personal")} — {t("cat_personal_hint")}</SelectItem>
            </SelectContent>
          </Select>
        </HelpField>
        <HelpField label={t("caisseDescription")} className="sm:col-span-2">
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </HelpField>
      </div>

      <div className="space-y-3 rounded-md border border-border bg-card p-3">
        <label className="flex cursor-pointer items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">{t("caisseRecurring")}</p>
            <p className="text-xs text-muted-foreground">{t("caisseRecurringHint")}</p>
          </div>
          <Switch checked={recurring} onCheckedChange={setRecurring} />
        </label>
        {recurring && (
          <HelpField label={t("caisseRecurringAmount")} example={t("caisseRecurringAmountExample")}>
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
            <p className="text-sm font-medium">{t("caisseMemberRequired")}</p>
            <p className="text-xs text-muted-foreground">{t("caisseMemberRequiredHint")}</p>
          </div>
          <Switch checked={memberRequired} onCheckedChange={setMemberRequired} />
        </label>
        {memberRequired && (
          <HelpField label={t("caisseMemberAmount")} example={t("caisseMemberAmountExample")}>
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
                {t("caisseObjective")}
                {category === "project" && (
                  <span className="ml-1 text-xs text-destructive">
                    ({t("caisseProjectRequired")})
                  </span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">{t("caisseObjectiveHint")}</p>
            </div>
            <Switch
              checked={hasObjective || category === "project"}
              onCheckedChange={setHasObjective}
              disabled={category === "project"}
            />
          </label>
          {(hasObjective || category === "project") && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <HelpField
                label={t("caisseObjectiveAmount")}
                example={t("caisseObjectiveAmountExample")}
              >
                <Input
                  type="number"
                  min={1}
                  value={objectiveAmount}
                  onChange={(e) => setObjectiveAmount(e.target.value)}
                />
              </HelpField>
              <HelpField label={t("caisseObjectiveDeadline")}>
                <Input
                  type="date"
                  value={objectiveDeadline}
                  onChange={(e) => setObjectiveDeadline(e.target.value)}
                />
              </HelpField>
            </div>
          )}
        </div>
      )}

      <ConfigPreview intent="success">
        <p className="font-medium">{t("caissePreviewTitle")}</p>
        <p className="mt-1">
          {recurring && t("caissePreviewRecurringText", { amount: parseInt(recurringAmount || "0", 10) })}
          {memberRequired &&
            ` ${t("caissePreviewMemberText", { amount: parseInt(memberRequiredAmount || "0", 10) })}`}
          {(hasObjective || category === "project") &&
            ` ${t("caissePreviewObjectiveText", { amount: parseInt(objectiveAmount || "0", 10) })}`}
          {!recurring && !memberRequired && !hasObjective && category !== "project" &&
            t("caissePreviewFreeText")}
        </p>
      </ConfigPreview>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          {tCommon("cancel")}
        </Button>
        <Button
          onClick={() => create.mutate()}
          disabled={create.isPending || !name.trim()}
          className="gap-2"
        >
          {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {tCommon("create")}
        </Button>
      </div>
    </div>
  );
}

// ── Stub step (tontines / loans / aids) ────────────────────────────────────

// ── Stub link step (tontines / loans / aids) ──────────────────────────────
// La vraie CRUD vit sur la page de config standalone correspondante. Le
// wizard se contente d'afficher l'état actuel (nombre d'éléments configurés)
// et de renvoyer l'admin vers la page complète. Au retour, il revient au
// wizard via la bannière "Retour à l'onboarding".

function WizardStepFooter({
  onBack,
  onSkip,
  finishLabel,
}: {
  onBack: () => void;
  onSkip: () => Promise<void>;
  finishLabel?: string;
}) {
  const t = useTranslations("onboarding");
  const tCommon = useTranslations("common");
  return (
    <>
      <Button variant="outline" onClick={onBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" />
        {tCommon("previous")}
      </Button>
      <Button onClick={onSkip} className="gap-2">
        {finishLabel ? (
          <>
            <CheckCircle2 className="h-4 w-4" />
            {finishLabel}
          </>
        ) : (
          <>
            {t("continue")}
            <ArrowRight className="h-4 w-4" />
          </>
        )}
      </Button>
    </>
  );
}

// ── Wizard step 3 — Tontines (CRUD inline) ─────────────────────────────────

function TontinesLinkStep({
  association,
  onBack,
  onSkip,
}: {
  association: Association;
  onBack: () => void;
  onSkip: () => Promise<void>;
}) {
  const t = useTranslations("onboarding");
  const tTontine = useTranslations("tontine");
  const fmt = useFormatters(association.currency);
  const { data: tontines = [] } = useQuery<Tontine[]>({
    queryKey: ["tontines", association.id],
    queryFn: () => tontinesApi.list(association.id),
  });

  return (
    <WizardCard
      title={t("stepTontinesTitle")}
      description={t("stepTontinesDesc")}
      footer={<WizardStepFooter onBack={onBack} onSkip={onSkip} />}
    >
      <ConfigPreview intent="info">{t("stepTontinesIntro")}</ConfigPreview>
      {tontines.length > 0 && (
        <ul className="space-y-2">
          {tontines.map((tt) => (
            <li
              key={tt.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Repeat className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{tt.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {t("countTontines", { active: tt.cycles_count })} · {tTontine("roundAmount")}:{" "}
                    {fmt.currency(tt.round_amount)}
                  </p>
                </div>
              </div>
              {tt.current_cycle && (
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {tTontine(
                    `status${tt.current_cycle.status.charAt(0).toUpperCase() + tt.current_cycle.status.slice(1)}`,
                  )}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
      <CreateTontineDialog association={association} />
    </WizardCard>
  );
}

// ── Wizard step 4 — Loans (CRUD inline) ────────────────────────────────────

function LoansLinkStep({
  association,
  onBack,
  onSkip,
}: {
  association: Association;
  onBack: () => void;
  onSkip: () => Promise<void>;
}) {
  const t = useTranslations("onboarding");
  return (
    <WizardCard
      title={t("stepLoansTitle")}
      description={t("stepLoansDesc")}
      footer={<WizardStepFooter onBack={onBack} onSkip={onSkip} />}
    >
      <LoanTypesManager association={association} />
    </WizardCard>
  );
}

// ── Wizard step 5 — Aides sociales (CRUD inline) ───────────────────────────

function AidsLinkStep({
  association,
  onBack,
  onSkip,
  finishLabel,
}: {
  association: Association;
  onBack: () => void;
  onSkip: () => Promise<void>;
  finishLabel?: string;
}) {
  const t = useTranslations("onboarding");
  return (
    <WizardCard
      title={t("stepAidsTitle")}
      description={t("stepAidsDesc")}
      footer={<WizardStepFooter onBack={onBack} onSkip={onSkip} finishLabel={finishLabel} />}
    >
      <AidTypesManager association={association} />
    </WizardCard>
  );
}
