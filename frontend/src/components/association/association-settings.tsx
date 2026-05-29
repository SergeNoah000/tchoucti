"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save, Building2, Repeat, HeartHandshake, Wallet, CalendarClock, Bell } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CurrencySelect } from "@/components/common/currency-select";
import { LogoUpload } from "@/components/common/logo-upload";
import { associationsApi } from "@/lib/api";
import type {
  Association,
  AssociationType,
  MeetingMode,
  SettingsFrequency,
  TontineAllocation,
} from "@/lib/types";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

interface AssociationSettingsProps {
  association: Association;
  canManage: boolean;
}

/** Mutation shared by every section — patches the association and refreshes it. */
function useSettingsSave(associationId: string) {
  const t = useTranslations("settings");
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => associationsApi.update(associationId, payload),
    onSuccess: () => {
      toast.success(t("saved"));
      queryClient.invalidateQueries({ queryKey: ["association", associationId] });
      queryClient.invalidateQueries({ queryKey: ["associations"] });
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });
}

export function AssociationSettings({ association, canManage }: AssociationSettingsProps) {
  return (
    <div className="space-y-4">
      <GeneralSection association={association} canManage={canManage} />
      <TontineSection association={association} canManage={canManage} />
      <SocialFundSection association={association} canManage={canManage} />
      <PaymentsSection association={association} canManage={canManage} />
      <MeetingsSection association={association} canManage={canManage} />
      <NotificationsSection association={association} canManage={canManage} />
    </div>
  );
}

// ── Shared section shell ────────────────────────────────────────────────────

function SectionCard({
  icon: Icon,
  title,
  description,
  canManage,
  pending,
  onSave,
  children,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  canManage: boolean;
  pending: boolean;
  onSave: () => void;
  children: React.ReactNode;
}) {
  const t = useTranslations("settings");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-primary" />
          {title}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {children}
        {canManage && (
          <div className="flex justify-end pt-1">
            <Button onClick={onSave} disabled={pending} className="gap-2">
              {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {t("save")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
  disabled,
  description,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  );
}

const FREQUENCIES: SettingsFrequency[] = ["weekly", "biweekly", "monthly", "quarterly"];

function num(v: string): number | undefined {
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? undefined : n;
}

// ── 1. Général ──────────────────────────────────────────────────────────────

function GeneralSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const [name, setName] = useState(association.name);
  const [type, setType] = useState<AssociationType>(association.type);
  const [currency, setCurrency] = useState(association.currency);
  const [email, setEmail] = useState(association.email ?? "");
  const [phone, setPhone] = useState(association.phone ?? "");

  const TYPES: AssociationType[] = ["tontine", "mutuelle", "cooperative", "association", "autre"];

  return (
    <SectionCard
      icon={Building2}
      title={t("secGeneral")}
      description={t("secGeneralDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          name: name.trim(),
          type,
          currency: currency.trim() || "XAF",
          email: email.trim() || null,
          phone: phone.trim() || null,
        })
      }
    >
      <div className="mb-4">
        <Field label={t("logo")}>
          <LogoUpload
            associationId={association.id}
            currentLogoUrl={association.logo_url}
            disabled={!canManage}
          />
        </Field>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t("name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!canManage} />
        </Field>
        <Field label={t("type")}>
          <Select value={type} onValueChange={(v) => setType(v as AssociationType)} disabled={!canManage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPES.map((ty) => (
                <SelectItem key={ty} value={ty}>
                  {t(`type_${ty}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label={t("currency")}>
          <CurrencySelect
            value={currency}
            onValueChange={setCurrency}
            disabled={!canManage || association.currency_locked}
          />
          {association.currency_locked && (
            <p className="mt-1 text-xs text-muted-foreground">{t("currencyLockedHint")}</p>
          )}
        </Field>
        <Field label={t("email")}>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!canManage} />
        </Field>
        <Field label={t("phone")}>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} disabled={!canManage} />
        </Field>
      </div>
    </SectionCard>
  );
}

// ── 2. Tontine ──────────────────────────────────────────────────────────────

function TontineSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const cfg = association.config.tontine ?? {};
  const [amount, setAmount] = useState(cfg.contribution_amount?.toString() ?? "");
  const [frequency, setFrequency] = useState<SettingsFrequency>(cfg.frequency ?? "monthly");
  const [duration, setDuration] = useState(cfg.cycle_duration_months?.toString() ?? "");
  const [participants, setParticipants] = useState(cfg.participants_count?.toString() ?? "");
  const [method, setMethod] = useState<TontineAllocation>(cfg.allocation_method ?? "fixed_order");

  const METHODS: TontineAllocation[] = [
    "fixed_order",
    "random_draw",
    "auction",
    "urgency_priority",
    "member_vote",
  ];

  return (
    <SectionCard
      icon={Repeat}
      title={t("secTontine")}
      description={t("secTontineDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          config: {
            ...association.config,
            tontine: {
              contribution_amount: num(amount),
              frequency,
              cycle_duration_months: num(duration),
              participants_count: num(participants),
              allocation_method: method,
            },
          },
        })
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={`${t("contributionAmount")} (${association.currency})`}>
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("frequency")}>
          <Select value={frequency} onValueChange={(v) => setFrequency(v as SettingsFrequency)} disabled={!canManage}>
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
        </Field>
        <Field label={t("cycleDuration")}>
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("participantsCount")}>
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            value={participants}
            onChange={(e) => setParticipants(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("allocationMethod")}>
          <Select value={method} onValueChange={(v) => setMethod(v as TontineAllocation)} disabled={!canManage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {METHODS.map((m) => (
                <SelectItem key={m} value={m}>
                  {t(`alloc_${m}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>
    </SectionCard>
  );
}

// ── 3. Caisse sociale ───────────────────────────────────────────────────────

function SocialFundSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const cfg = association.config.social_fund ?? {};
  const ev = cfg.events ?? {};
  const [amount, setAmount] = useState(cfg.contribution_amount?.toString() ?? "");
  const [conditions, setConditions] = useState(cfg.conditions ?? "");
  const [death, setDeath] = useState(ev.death?.toString() ?? "");
  const [illness, setIllness] = useState(ev.illness?.toString() ?? "");
  const [marriage, setMarriage] = useState(ev.marriage?.toString() ?? "");
  const [birth, setBirth] = useState(ev.birth?.toString() ?? "");

  const events: { key: string; value: string; set: (v: string) => void }[] = [
    { key: "event_death", value: death, set: setDeath },
    { key: "event_illness", value: illness, set: setIllness },
    { key: "event_marriage", value: marriage, set: setMarriage },
    { key: "event_birth", value: birth, set: setBirth },
  ];

  return (
    <SectionCard
      icon={HeartHandshake}
      title={t("secSocialFund")}
      description={t("secSocialFundDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          config: {
            ...association.config,
            social_fund: {
              contribution_amount: num(amount),
              conditions: conditions.trim() || undefined,
              events: {
                death: num(death),
                illness: num(illness),
                marriage: num(marriage),
                birth: num(birth),
              },
            },
          },
        })
      }
    >
      <Field label={`${t("socialContribution")} (${association.currency})`}>
        <Input
          type="number"
          inputMode="numeric"
          min={0}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          disabled={!canManage}
        />
      </Field>
      <Field label={t("conditions")}>
        <Textarea
          rows={2}
          value={conditions}
          onChange={(e) => setConditions(e.target.value)}
          placeholder={t("conditionsPlaceholder")}
          disabled={!canManage}
        />
      </Field>
      <div className="space-y-1.5">
        <Label>{t("coveredEvents")}</Label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {events.map((e) => (
            <div key={e.key} className="flex items-center gap-2">
              <span className="w-24 shrink-0 text-sm text-muted-foreground">{t(e.key)}</span>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={e.value}
                onChange={(ev2) => e.set(ev2.target.value)}
                disabled={!canManage}
              />
            </div>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

// ── 4. Paiements ────────────────────────────────────────────────────────────

function PaymentsSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const cfg = association.config.payments ?? {};
  const [cash, setCash] = useState(cfg.cash ?? true);
  const [mtn, setMtn] = useState(cfg.mtn_momo ?? false);
  const [orange, setOrange] = useState(cfg.orange_money ?? false);
  const [bank, setBank] = useState(cfg.bank_transfer ?? false);

  return (
    <SectionCard
      icon={Wallet}
      title={t("secPayments")}
      description={t("secPaymentsDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          config: {
            ...association.config,
            payments: { cash, mtn_momo: mtn, orange_money: orange, bank_transfer: bank },
          },
        })
      }
    >
      <div className="space-y-2">
        <ToggleRow label={t("pay_cash")} checked={cash} onChange={setCash} disabled={!canManage} />
        <ToggleRow label={t("pay_mtn_momo")} checked={mtn} onChange={setMtn} disabled={!canManage} />
        <ToggleRow label={t("pay_orange_money")} checked={orange} onChange={setOrange} disabled={!canManage} />
        <ToggleRow label={t("pay_bank_transfer")} checked={bank} onChange={setBank} disabled={!canManage} />
      </div>
    </SectionCard>
  );
}

// ── 5. Réunions ─────────────────────────────────────────────────────────────

function MeetingsSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const cfg = association.config.meetings ?? {};
  const remindersCfg =
    (association.config.notifications as { meeting_reminders?: { enabled?: boolean; days_before?: number[] } } | undefined)
      ?.meeting_reminders ?? {};
  const [frequency, setFrequency] = useState<SettingsFrequency>(cfg.frequency ?? "monthly");
  const [mode, setMode] = useState<MeetingMode>(cfg.mode ?? "physical");
  const [quorum, setQuorum] = useState(cfg.quorum?.toString() ?? "");
  const [autoNotify, setAutoNotify] = useState(cfg.auto_notify ?? true);
  const [defaultTitle, setDefaultTitle] = useState<string>(
    (cfg as { default_title?: string }).default_title ?? "Séance du {date}"
  );
  const [defaultLocation, setDefaultLocation] = useState<string>(
    (cfg as { default_location?: string }).default_location ?? ""
  );
  const [horizon, setHorizon] = useState<string>(
    (cfg as { horizon?: number }).horizon?.toString() ?? "12"
  );
  const [remindersEnabled, setRemindersEnabled] = useState<boolean>(remindersCfg.enabled ?? true);
  const [daysBefore, setDaysBefore] = useState<string>(
    (remindersCfg.days_before ?? [7, 1]).join(", ")
  );

  const MODES: MeetingMode[] = ["physical", "virtual", "hybrid"];

  const parseDaysBefore = (raw: string): number[] => {
    const parts = raw.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    const nums = parts
      .map((s) => parseInt(s, 10))
      .filter((n) => Number.isFinite(n) && n >= 0 && n <= 60);
    return Array.from(new Set(nums)).sort((a, b) => b - a);
  };

  return (
    <SectionCard
      icon={CalendarClock}
      title={t("secMeetings")}
      description={t("secMeetingsDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          config: {
            ...association.config,
            meetings: {
              frequency,
              mode,
              quorum: num(quorum),
              auto_notify: autoNotify,
              default_title: defaultTitle.trim() || undefined,
              default_location: defaultLocation.trim() || undefined,
              horizon: Math.max(1, Math.min(60, parseInt(horizon, 10) || 12)),
            },
            notifications: {
              ...(association.config.notifications ?? {}),
              meeting_reminders: {
                enabled: remindersEnabled,
                days_before: parseDaysBefore(daysBefore),
              },
            },
          },
        })
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t("frequency")}>
          <Select value={frequency} onValueChange={(v) => setFrequency(v as SettingsFrequency)} disabled={!canManage}>
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
        </Field>
        <Field label={t("meetingMode")}>
          <Select value={mode} onValueChange={(v) => setMode(v as MeetingMode)} disabled={!canManage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODES.map((m) => (
                <SelectItem key={m} value={m}>
                  {t(`mode_${m}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label={t("quorum")}>
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={quorum}
            onChange={(e) => setQuorum(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("horizon")} hint={t("horizonHint")}>
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={60}
            value={horizon}
            onChange={(e) => setHorizon(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("defaultTitle")} hint={t("defaultTitleHint")}>
          <Input
            value={defaultTitle}
            onChange={(e) => setDefaultTitle(e.target.value)}
            disabled={!canManage}
          />
        </Field>
        <Field label={t("defaultLocation")}>
          <Input
            value={defaultLocation}
            onChange={(e) => setDefaultLocation(e.target.value)}
            disabled={!canManage}
          />
        </Field>
      </div>
      <ToggleRow
        label={t("autoNotify")}
        description={t("autoNotifyDesc")}
        checked={autoNotify}
        onChange={setAutoNotify}
        disabled={!canManage}
      />
      <ToggleRow
        label={t("remindersEnabled")}
        description={t("remindersEnabledDesc")}
        checked={remindersEnabled}
        onChange={setRemindersEnabled}
        disabled={!canManage}
      />
      <Field label={t("remindersDaysBefore")} hint={t("remindersDaysBeforeHint")}>
        <Input
          value={daysBefore}
          onChange={(e) => setDaysBefore(e.target.value)}
          disabled={!canManage || !remindersEnabled}
          placeholder="7, 1"
        />
      </Field>
    </SectionCard>
  );
}

// ── 6. Notifications ────────────────────────────────────────────────────────

function NotificationsSection({ association, canManage }: AssociationSettingsProps) {
  const t = useTranslations("settings");
  const save = useSettingsSave(association.id);
  const cfg = association.config.notifications ?? {};
  const [state, setState] = useState({
    contribution_reminder: cfg.contribution_reminder ?? true,
    meeting: cfg.meeting ?? true,
    penalty: cfg.penalty ?? true,
    tour_allocation: cfg.tour_allocation ?? true,
    birthday: cfg.birthday ?? false,
    loan_due: cfg.loan_due ?? true,
  });
  const toggle = (k: keyof typeof state) => (v: boolean) => setState((s) => ({ ...s, [k]: v }));

  const KEYS: (keyof typeof state)[] = [
    "contribution_reminder",
    "meeting",
    "penalty",
    "tour_allocation",
    "birthday",
    "loan_due",
  ];

  return (
    <SectionCard
      icon={Bell}
      title={t("secNotifications")}
      description={t("secNotificationsDesc")}
      canManage={canManage}
      pending={save.isPending}
      onSave={() => save.mutate({ config: { ...association.config, notifications: state } })}
    >
      <div className="space-y-2">
        {KEYS.map((k) => (
          <ToggleRow
            key={k}
            label={t(`notif_${k}`)}
            checked={state[k]}
            onChange={toggle(k)}
            disabled={!canManage}
          />
        ))}
      </div>
    </SectionCard>
  );
}
