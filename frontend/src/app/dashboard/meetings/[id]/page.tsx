"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  PlayCircle,
  CheckCircle2,
  CalendarClock,
  Clock,
  MapPin,
  Users,
  ClipboardList,
  TrendingUp,
  Loader2,
  AlertCircle,
  ChevronDown,
  Search,
  Save,
  ArrowRight,
  XCircle,
  FileText,
  MessageSquare,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MeetingAttachments } from "@/components/meetings/meeting-attachments";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";

import { activitiesApi, associationsApi, meetingsApi, membersApi } from "@/lib/api";
import type {
  Activity,
  Association,
  AttendanceStatus,
  MeetingDetail,
  Membership,
} from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { cn, initials } from "@/lib/utils";

const ATTENDANCE_PILLS: Record<AttendanceStatus, string> = {
  present: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  absent: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  excused: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  late: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
};

const ATTENDANCES: AttendanceStatus[] = ["present", "absent", "excused", "late"];

interface AgendaRow {
  activity_id: string;
  label: string;
  default_amount: number;
  is_required: boolean;
  context: Record<string, unknown>;
}

interface MemberAgendaData {
  membership_id: string;
  member_name?: string | null;
  tontines: AgendaRow[];
  caisses: AgendaRow[];
  loans: AgendaRow[];
  aids: AgendaRow[];
}

interface MeetingAgendaData {
  meeting_id: string;
  members: MemberAgendaData[];
}

interface MemberLocalState {
  attendance: AttendanceStatus | null;
  amounts: Record<string, string>; // activity_id → amount string
  notes: string;                   // notes personnelles sur ce membre
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("meeting");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const meetingKey = ["meeting", id];

  const { data: meeting, isLoading } = useQuery<MeetingDetail>({
    queryKey: meetingKey,
    queryFn: () => meetingsApi.get(id),
    enabled: !!id,
  });

  const associationId = meeting?.association_id;

  const { data: association } = useQuery<Association>({
    queryKey: ["association", associationId],
    queryFn: () => associationsApi.get(associationId!),
    enabled: !!associationId,
  });
  const fmt = useFormatters(association?.currency);

  const { data: activities = [] } = useQuery<Activity[]>({
    queryKey: ["activities", associationId],
    queryFn: () => activitiesApi.list({ association_id: associationId }),
    enabled: !!associationId,
  });

  // Phase 3b — per-member agenda computed from config-v2 (tontines actives
  // sur cette séance, caisses récurrentes/obligatoires, aides en cours,
  // prêts actifs). Fallback : si l'agenda est vide, on retombe sur la liste
  // plate d'activités pour ne pas casser les assos legacy.
  const { data: agenda } = useQuery<MeetingAgendaData>({
    queryKey: ["meeting-agenda", meeting?.id],
    queryFn: () => meetingsApi.agenda(meeting!.id),
    enabled: !!meeting?.id,
  });

  const { data: memberships = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId!),
    enabled: !!associationId,
  });

  const canEdit = meeting?.status === "ongoing";

  const openMutation = useMutation({
    mutationFn: () => meetingsApi.open(meeting!.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meetingKey }),
  });

  const closeMutation = useMutation({
    mutationFn: () => meetingsApi.close(meeting!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: meetingKey });
      queryClient.invalidateQueries({ queryKey: ["treasury", associationId] });
      queryClient.invalidateQueries({ queryKey: ["movements", associationId] });
    },
  });

  // ── Stats (live from server snapshot) ─────────────────────────────────────
  const presentCount = useMemo(
    () =>
      meeting?.attendances.filter((a) => a.status === "present" || a.status === "late").length ?? 0,
    [meeting?.attendances],
  );
  const totalEntries = useMemo(
    () => meeting?.entries.filter((e) => e.status !== "voided").length ?? 0,
    [meeting?.entries],
  );
  const totalAmount = useMemo(
    () =>
      meeting?.entries
        .filter((e) => e.status !== "voided")
        .reduce((s, e) => s + e.amount, 0) ?? 0,
    [meeting?.entries],
  );

  // ── Récap : breakdown des présences ──────────────────────────────────────
  const recap = useMemo(() => {
    const out = { present: 0, absent: 0, excused: 0, late: 0 };
    for (const a of meeting?.attendances ?? []) {
      if (a.status in out) out[a.status as keyof typeof out]++;
    }
    return out;
  }, [meeting?.attendances]);
  const noStatus = (meeting && memberships.length)
    ? memberships.length - recap.present - recap.absent - recap.excused - recap.late
    : 0;

  // ── Notes de séance (compte-rendu) ───────────────────────────────────────
  const [notesDraft, setNotesDraft] = useState<string>("");
  const [notesInitialised, setNotesInitialised] = useState(false);
  useEffect(() => {
    if (meeting && !notesInitialised) {
      setNotesDraft(meeting.notes ?? "");
      setNotesInitialised(true);
    }
  }, [meeting, notesInitialised]);
  const notesDirty = (meeting?.notes ?? "") !== notesDraft;
  const saveNotes = useMutation({
    mutationFn: () => meetingsApi.update(meeting!.id, { notes: notesDraft }),
    onSuccess: () => {
      toast.success(t("notesSaved"));
      queryClient.invalidateQueries({ queryKey: meetingKey });
    },
    onError: () => toast.error(t("notesError")),
  });

  // ── Member search ────────────────────────────────────────────────────────
  const [search, setSearch] = useState("");
  const filteredMembers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return memberships;
    return memberships.filter((m) => m.user.full_name.toLowerCase().includes(q));
  }, [memberships, search]);

  // ── Master-detail : un seul membre actif à la fois ──────────────────────
  // (Avant : Collapsible par membre. Le client préfère un tab-pane : liste à
  // gauche, panneau de saisie du membre sélectionné à droite.)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  // Sélectionne le 1er membre filtré par défaut (ou quand la sélection sort de la liste).
  useEffect(() => {
    if (filteredMembers.length === 0) return;
    if (!selectedMemberId || !filteredMembers.some((m) => m.id === selectedMemberId)) {
      setSelectedMemberId(filteredMembers[0]!.id);
    }
  }, [filteredMembers, selectedMemberId]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
        <p className="text-lg font-semibold">{t("notFound")}</p>
        <Button asChild variant="ghost" className="mt-4">
          <Link href="/dashboard/meetings">← {t("backToList")}</Link>
        </Button>
      </div>
    );
  }

  const visibleActivities = activities.filter((a) => a.is_visible_in_meeting && a.is_active);

  // Sélectionne le membre suivant dans la liste filtrée.
  const advanceTo = (currentMembershipId: string) => {
    const idx = filteredMembers.findIndex((m) => m.id === currentMembershipId);
    const next = filteredMembers[idx + 1];
    if (next) setSelectedMemberId(next.id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
        <div className="min-w-0 space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
            <Link href="/dashboard/meetings">
              <ArrowLeft className="h-4 w-4" />
              {t("backToList")}
            </Link>
          </Button>
          <h1 className="text-2xl font-bold tracking-tight">{meeting.title}</h1>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {fmt.longDate(meeting.scheduled_on)}
            </span>
            {meeting.location && (
              <span className="flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" />
                {meeting.location}
              </span>
            )}
          </div>
        </div>

        {/* Lifecycle actions */}
        <div className="flex shrink-0 items-center gap-2">
          {meeting.status === "planned" && (
            <>
              <RescheduleDialog meetingId={meeting.id} currentDate={meeting.scheduled_on} />
              <CancelDialog meetingId={meeting.id} />
              <Button onClick={() => openMutation.mutate()} disabled={openMutation.isPending} className="gap-2">
                {openMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="h-4 w-4" />
                )}
                {t("start")}
              </Button>
            </>
          )}
          {meeting.status === "ongoing" && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="outline"
                  className="gap-2 border-emerald-500 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {t("close")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("confirmCloseTitle")}</AlertDialogTitle>
                  <AlertDialogDescription>{t("confirmCloseDesc")}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => closeMutation.mutate()} disabled={closeMutation.isPending}>
                    {closeMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t("confirmCloseAction")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      {/* Status banner */}
      {meeting.status === "ongoing" && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          {t("bannerOngoing")}
        </div>
      )}
      {meeting.status === "closed" && (
        <div className="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
          <CheckCircle2 className="h-4 w-4" />
          {t("bannerClosed", { date: meeting.closed_at ? fmt.date(meeting.closed_at) : "—" })}
        </div>
      )}

      {/* Live stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Users} label={t("statPresent")} value={`${presentCount} / ${memberships.length}`} />
        <StatCard icon={ClipboardList} label={t("statEntries")} value={String(totalEntries)} />
        <StatCard
          icon={TrendingUp}
          label={t("statCollected")}
          value={fmt.currency(meeting.status === "closed" ? meeting.total_in : totalAmount)}
          accent="emerald"
        />
      </div>

      {/* Récap de la séance — breakdown des présences */}
      <Card>
        <CardContent className="space-y-3 p-4">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />
            {t("recapTitle")}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <RecapPill label={t("recapPresent")} value={recap.present} tone="emerald" />
            <RecapPill label={t("recapLate")} value={recap.late} tone="amber" />
            <RecapPill label={t("recapExcused")} value={recap.excused} tone="sky" />
            <RecapPill label={t("recapAbsent")} value={recap.absent} tone="rose" />
            <RecapPill label={t("recapNoStatus")} value={noStatus} tone="slate" />
          </div>
          {meeting.description && (
            <p className="border-l-2 border-primary/30 pl-3 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{t("recapAgenda")} :</span>{" "}
              {meeting.description}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Pièces jointes globales à la séance */}
      <Card>
        <CardContent className="p-4">
          <MeetingAttachments
            associationId={meeting.association_id}
            meetingId={meeting.id}
            canUpload={canEdit}
          />
        </CardContent>
      </Card>

      {/* Notes de séance — compte-rendu (bureau seulement) */}
      {(canEdit || meeting.notes) && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <MessageSquare className="h-3.5 w-3.5" />
                {t("notesTitle")}
              </p>
              {canEdit && notesDirty && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  onClick={() => saveNotes.mutate()}
                  disabled={saveNotes.isPending}
                >
                  {saveNotes.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  {t("notesSave")}
                </Button>
              )}
            </div>
            {canEdit ? (
              <>
                <Textarea
                  value={notesDraft}
                  onChange={(e) => setNotesDraft(e.target.value)}
                  placeholder={t("notesPlaceholder")}
                  rows={6}
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground">{t("notesHint")}</p>
              </>
            ) : (
              <p className="whitespace-pre-wrap text-sm text-foreground">
                {meeting.notes || t("notesEmpty")}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("searchMembers")}
          className="pl-9"
        />
      </div>

      {/* Master-detail : liste de membres à gauche, panneau de saisie à droite. */}
      {memberships.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            {t("noMembers")}
          </CardContent>
        </Card>
      ) : filteredMembers.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            {t("noMatchingMembers")}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(220px,1fr)_2fr]">
          <ul className="space-y-1 lg:max-h-[70vh] lg:overflow-y-auto lg:pr-1">
            {filteredMembers.map((m) => {
              const hasAttendance = meeting.attendances.some((a) => a.membership_id === m.id);
              const hasEntries = meeting.entries.some(
                (e) => e.membership_id === m.id && e.status !== "voided",
              );
              const isSelected = selectedMemberId === m.id;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedMemberId(m.id)}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                      isSelected
                        ? "border-primary/50 bg-primary/5 text-foreground"
                        : "border-border hover:border-primary/30 hover:bg-accent/40",
                    )}
                  >
                    <span className="truncate">{m.user.full_name}</span>
                    {(hasAttendance || hasEntries) && (
                      <span className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                        {t("saved")}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>

          <div>
            {(() => {
              const selected = filteredMembers.find((m) => m.id === selectedMemberId);
              if (!selected) return null;
              return (
                <MemberRow
                  key={selected.id}
                  meeting={meeting}
                  member={selected}
                  activities={visibleActivities}
                  memberAgenda={agenda?.members.find((ma) => ma.membership_id === selected.id) ?? null}
                  canEdit={canEdit}
                  isOpen={true}
                  setOpen={() => {}}
                  onSavedAdvance={() => advanceTo(selected.id)}
                  currency={association?.currency}
                />
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Recap pill (breakdown des présences) ─────────────────────────────────────

const _PILL_TONES = {
  emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  sky: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200",
  rose: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
  slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
} as const;

function RecapPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: keyof typeof _PILL_TONES;
}) {
  return (
    <div className={`rounded-lg px-3 py-2 ${_PILL_TONES[tone]}`}>
      <p className="text-[10px] uppercase tracking-wider opacity-80">{label}</p>
      <p className="text-xl font-bold tabular-nums leading-tight">{value}</p>
    </div>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  accent?: "emerald";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "rounded-lg p-2",
              accent === "emerald"
                ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"
                : "bg-primary/10 text-primary",
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p
              className={cn(
                "truncate tabular-nums",
                accent === "emerald"
                  ? "text-lg font-bold text-emerald-600 dark:text-emerald-400"
                  : "text-xl font-bold",
              )}
            >
              {value}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Member row (collapsible) ─────────────────────────────────────────────────

function AgendaSection({
  title,
  rows,
  amounts,
  setAmount,
  canEdit,
}: {
  title: string;
  rows: AgendaRow[];
  amounts: Record<string, string>;
  setAmount: (activityId: string, value: string) => void;
  canEdit: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {rows.map((r) => (
          <div
            key={`${r.activity_id}-${JSON.stringify(r.context)}`}
            className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 px-3 py-2"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">{r.label}</span>
              {r.is_required && (
                <span className="text-[10px] uppercase tracking-wide text-destructive/70">
                  Obligatoire
                </span>
              )}
            </span>
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              disabled={!canEdit}
              value={amounts[r.activity_id] ?? (r.default_amount > 0 ? String(r.default_amount) : "")}
              onChange={(e) => setAmount(r.activity_id, e.target.value)}
              placeholder={r.default_amount > 0 ? String(r.default_amount) : "0"}
              className="h-8 w-28 text-right text-sm"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function MemberRow({
  meeting,
  member,
  activities,
  memberAgenda,
  canEdit,
  isOpen,
  setOpen,
  onSavedAdvance,
  currency,
}: {
  meeting: MeetingDetail;
  member: Membership;
  activities: Activity[];
  memberAgenda: MemberAgendaData | null;
  canEdit: boolean;
  isOpen: boolean;
  setOpen: (open: boolean) => void;
  onSavedAdvance: () => void;
  currency?: string;
}) {
  const t = useTranslations("meeting");
  const fmt = useFormatters(currency);
  const queryClient = useQueryClient();

  // ── Initialise local state from server snapshot ──
  const serverAttendanceObj = useMemo(
    () => meeting.attendances.find((a) => a.membership_id === member.id),
    [meeting.attendances, member.id],
  );
  const serverAttendance = serverAttendanceObj?.status ?? null;
  const serverNotes = serverAttendanceObj?.notes ?? "";
  const serverEntries = useMemo(
    () => meeting.entries.filter((e) => e.membership_id === member.id && e.status !== "voided"),
    [meeting.entries, member.id],
  );
  const serverAmounts: Record<string, string> = useMemo(() => {
    const out: Record<string, string> = {};
    for (const e of serverEntries) out[e.activity_id] = String(e.amount);
    return out;
  }, [serverEntries]);

  const [local, setLocal] = useState<MemberLocalState>({
    attendance: serverAttendance as AttendanceStatus | null,
    amounts: serverAmounts,
    notes: serverNotes,
  });

  // Re-sync when the meeting snapshot changes (e.g. after a save).
  useEffect(() => {
    setLocal({
      attendance: serverAttendance as AttendanceStatus | null,
      amounts: serverAmounts,
      notes: serverNotes,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverAttendance, serverNotes, JSON.stringify(serverAmounts)]);

  const dirty = useMemo(() => {
    if (local.attendance !== serverAttendance) return true;
    if ((local.notes ?? "") !== (serverNotes ?? "")) return true;
    const keys = new Set([...Object.keys(local.amounts), ...Object.keys(serverAmounts)]);
    for (const k of keys) {
      const lv = (local.amounts[k] ?? "").trim();
      const sv = serverAmounts[k] ?? "";
      const lvN = parseInt(lv, 10);
      if (lv === "" && sv === "") continue;
      if (lv === "" && sv !== "") return true;
      if (sv === "" && lv !== "" && !Number.isNaN(lvN) && lvN > 0) return true;
      if (sv !== "" && lv !== "" && lv !== sv) return true;
    }
    return false;
  }, [local, serverAttendance, serverAmounts, serverNotes]);

  // Sum of locally-edited (or saved) amounts for this member.
  const memberTotal = useMemo(() => {
    return Object.values(local.amounts).reduce((s, v) => {
      const n = parseInt(v, 10);
      return s + (Number.isNaN(n) ? 0 : Math.max(0, n));
    }, 0);
  }, [local.amounts]);

  // ── Save ──
  const saveMutation = useMutation({
    mutationFn: () =>
      meetingsApi.saveMember(meeting.id, {
        membership_id: member.id,
        attendance: local.attendance ?? undefined,
        attendance_notes: local.notes.trim() || undefined,
        entries: Object.entries(local.amounts)
          .map(([activity_id, raw]) => {
            const amount = parseInt(raw, 10);
            return Number.isNaN(amount) || amount <= 0 ? null : { activity_id, amount };
          })
          .filter((x): x is { activity_id: string; amount: number } => x !== null),
      }),
    onSuccess: () => {
      toast.success(t("memberSaved"));
      queryClient.invalidateQueries({ queryKey: ["meeting", meeting.id] });
    },
  });

  const setAmount = (activityId: string, value: string) =>
    setLocal((s) => ({ ...s, amounts: { ...s.amounts, [activityId]: value } }));
  const setAttendance = (a: AttendanceStatus) => setLocal((s) => ({ ...s, attendance: a }));

  // True s'il existe DÉJÀ des données pour ce membre côté serveur — toute
  // sauvegarde écrase et sera tracée dans le journal d'éditions de la séance.
  const hadServerData = useMemo(
    () => serverAttendance !== null || Object.keys(serverAmounts).length > 0,
    [serverAttendance, serverAmounts],
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingNext, setPendingNext] = useState(false);

  const doSave = async (andNext: boolean) => {
    await saveMutation.mutateAsync();
    if (andNext) onSavedAdvance();
  };

  const handleSave = async (andNext: boolean) => {
    if (hadServerData && dirty) {
      setPendingNext(andNext);
      setConfirmOpen(true);
      return;
    }
    await doSave(andNext);
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setOpen} asChild>
      <div
        className={cn(
          "rounded-xl border bg-card transition-all",
          isOpen ? "border-primary/30 shadow-sm" : "border-border hover:border-primary/20",
        )}
      >
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
          >
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                {initials(member.user.full_name)}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{member.user.full_name}</p>
                <p className="truncate text-xs text-muted-foreground">{member.user.email}</p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {local.attendance && (
                <span
                  className={cn(
                    "rounded-full px-2.5 py-0.5 text-xs font-medium",
                    ATTENDANCE_PILLS[local.attendance],
                  )}
                >
                  {t(local.attendance)}
                </span>
              )}
              {memberTotal > 0 && (
                <span className="text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                  +{fmt.currency(memberTotal)}
                </span>
              )}
              {dirty && canEdit && (
                <Badge variant="warning" className="text-[10px]">
                  {t("unsaved")}
                </Badge>
              )}
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-muted-foreground transition-transform",
                  isOpen && "rotate-180",
                )}
              />
            </div>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent className="space-y-4 border-t border-border/60 px-4 py-4">
          {/* Attendance */}
          <div className="space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("attendance")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {ATTENDANCES.map((a) => {
                const active = local.attendance === a;
                return (
                  <button
                    key={a}
                    type="button"
                    disabled={!canEdit}
                    onClick={() => setAttendance(a)}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium transition-all",
                      active
                        ? ATTENDANCE_PILLS[a] + " ring-2 ring-offset-1 ring-current"
                        : "bg-muted text-muted-foreground hover:bg-accent",
                      !canEdit && "cursor-not-allowed opacity-60",
                    )}
                  >
                    {t(a)}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Agenda sections (Phase 3b, driven by config-v2).
              Fallback : si l'agenda est vide (asso legacy ou pas encore
              configurée), on retombe sur la liste plate d'activités pour
              ne pas casser les flux existants. */}
          {memberAgenda &&
          (memberAgenda.tontines.length > 0 ||
            memberAgenda.caisses.length > 0 ||
            memberAgenda.loans.length > 0 ||
            memberAgenda.aids.length > 0) ? (
            <>
              <AgendaSection
                title={t("sectionTontines")}
                rows={memberAgenda.tontines}
                amounts={local.amounts}
                setAmount={setAmount}
                canEdit={canEdit}
              />
              <AgendaSection
                title={t("sectionCaisses")}
                rows={memberAgenda.caisses}
                amounts={local.amounts}
                setAmount={setAmount}
                canEdit={canEdit}
              />
              <AgendaSection
                title={t("sectionLoans")}
                rows={memberAgenda.loans}
                amounts={local.amounts}
                setAmount={setAmount}
                canEdit={canEdit}
              />
              <AgendaSection
                title={t("sectionAids")}
                rows={memberAgenda.aids}
                amounts={local.amounts}
                setAmount={setAmount}
                canEdit={canEdit}
              />
            </>
          ) : (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("activities")}
              </p>
              {activities.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border px-3 py-3 text-center text-sm text-muted-foreground">
                  {t("noActivities")}
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {activities.map((a) => (
                    <div
                      key={a.id}
                      className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 px-3 py-2"
                    >
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: a.color || "var(--primary)" }}
                      />
                      <span className="min-w-0 flex-1 truncate text-sm">{a.name}</span>
                      <Input
                        type="number"
                        inputMode="numeric"
                        min={0}
                        disabled={!canEdit}
                        value={local.amounts[a.id] ?? ""}
                        onChange={(e) => setAmount(a.id, e.target.value)}
                        placeholder="0"
                        className="h-8 w-28 text-right text-sm"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Notes personnelles sur ce membre — saisies par le bureau, incluses
              dans la section « Détail par membre » du PV PDF. */}
          {(canEdit || local.notes) && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("memberNotes")}
              </p>
              {canEdit ? (
                <Textarea
                  value={local.notes}
                  onChange={(e) => setLocal((s) => ({ ...s, notes: e.target.value }))}
                  placeholder={t("memberNotesPlaceholder")}
                  rows={3}
                  maxLength={500}
                />
              ) : (
                <p className="whitespace-pre-wrap rounded-md border border-border/40 bg-muted/30 px-3 py-2 text-sm">
                  {local.notes}
                </p>
              )}
            </div>
          )}

          {/* Pièces jointes spécifiques à ce membre dans cette séance. */}
          <MeetingAttachments
            associationId={meeting.association_id}
            meetingId={meeting.id}
            membershipId={member.id}
            canUpload={canEdit}
          />

          {/* Footer actions */}
          {canEdit && (
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <p className="text-xs text-muted-foreground">
                {t("memberTotal")}:{" "}
                <span className="font-semibold tabular-nums text-foreground">
                  {fmt.currency(memberTotal)}
                </span>
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={saveMutation.isPending || !dirty}
                  onClick={() => handleSave(false)}
                  className="gap-1.5"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  {dirty ? t("addEntry") : t("saved")}
                </Button>
                <Button
                  size="sm"
                  disabled={saveMutation.isPending}
                  onClick={() => handleSave(true)}
                  className="gap-1.5"
                >
                  {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {t("saveAndNext")}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}
        </CollapsibleContent>

        {/* L'AlertDialog DOIT rester à l'intérieur du <div> parent : Collapsible
            est utilisé avec `asChild` (cf. ligne ouvrante) et n'accepte qu'un
            seul enfant — Radix Slot appelle React.Children.only(). Le dialog
            étant rendu via portail, sa position DOM n'a pas d'impact visuel. */}
        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("editConfirmTitle")}</AlertDialogTitle>
              <AlertDialogDescription>
                {t("editConfirmDesc", { name: member.user.full_name })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("editConfirmCancel")}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  setConfirmOpen(false);
                  void doSave(pendingNext);
                }}
              >
                {t("editConfirmConfirm")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </Collapsible>
  );
}

// ── Phase 4 — reschedule / cancel a single meeting ────────────────────────

function RescheduleDialog({
  meetingId,
  currentDate,
}: {
  meetingId: string;
  currentDate: string;
}) {
  const t = useTranslations("meeting");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(currentDate);

  const mutation = useMutation({
    mutationFn: () => meetingsApi.update(meetingId, { scheduled_on: date }),
    onSuccess: () => {
      toast.success(t("rescheduleSaved"));
      queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      setOpen(false);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? tCommon("error"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="gap-2">
          <CalendarClock className="h-4 w-4" />
          {t("reschedule")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("rescheduleTitle")}</DialogTitle>
          <DialogDescription>{t("rescheduleDesc")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="resched-date">{t("newDate")}</Label>
          <Input
            id="resched-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {tCommon("cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !date || date === currentDate}
            className="gap-2"
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {tCommon("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelDialog({ meetingId }: { meetingId: string }) {
  const t = useTranslations("meeting");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => meetingsApi.cancel(meetingId),
    onSuccess: () => {
      toast.success(t("cancelSaved"));
      queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? tCommon("error"));
    },
  });

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" className="gap-2 border-destructive/40 text-destructive">
          <XCircle className="h-4 w-4" />
          {t("cancelMeeting")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("cancelConfirmTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("cancelConfirmDesc")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("cancelMeeting")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
