"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  PlayCircle,
  CheckCircle2,
  Clock,
  MapPin,
  Users,
  ClipboardList,
  Plus,
  Trash2,
  Loader2,
  AlertCircle,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { Input } from "@/components/ui/input";
import { meetingsApi, activitiesApi, membersApi } from "@/lib/api";
import type {
  MeetingDetail,
  MeetingAttendance,
  MeetingActivityEntry,
  Activity,
  Membership,
  AttendanceStatus,
} from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { cn, initials } from "@/lib/utils";

const ATTENDANCE_PILLS: Record<AttendanceStatus, string> = {
  present: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  absent: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  excused: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  late: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
};

const STATUS_OPTIONS: AttendanceStatus[] = ["present", "absent", "excused", "late"];

// ── Attendance row ────────────────────────────────────────────────────────

function AttendanceRow({
  membership,
  attendance,
  canEdit,
  onStatusChange,
}: {
  membership: Membership;
  attendance?: MeetingAttendance;
  canEdit: boolean;
  onStatusChange: (membershipId: string, status: AttendanceStatus) => void;
}) {
  const t = useTranslations("meeting");
  const status = attendance?.status ?? "absent";

  return (
    <div className="flex items-center justify-between py-2.5">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
          {initials(membership.user?.full_name)}
        </div>
        <span className="text-sm font-medium">{membership.user?.full_name ?? "—"}</span>
      </div>
      {canEdit ? (
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onStatusChange(membership.id, s)}
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-medium transition-all",
                status === s
                  ? ATTENDANCE_PILLS[s] + " ring-2 ring-offset-1 ring-current"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {t(s)}
            </button>
          ))}
        </div>
      ) : (
        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", ATTENDANCE_PILLS[status])}>
          {t(status)}
        </span>
      )}
    </div>
  );
}

// ── Entry row ─────────────────────────────────────────────────────────────

function EntryRow({
  entry,
  activities,
  memberships,
  canEdit,
  onVoid,
}: {
  entry: MeetingActivityEntry;
  activities: Activity[];
  memberships: Membership[];
  canEdit: boolean;
  onVoid: (entryId: string) => void;
}) {
  const t = useTranslations("meeting");
  const fmt = useFormatters();
  const activity = activities.find((a) => a.id === entry.activity_id);
  const membership = memberships.find((m) => m.id === entry.membership_id);

  return (
    <div className="flex items-center justify-between py-2.5">
      <div className="flex items-center gap-3">
        <div
          className="h-3 w-3 rounded-full flex-shrink-0"
          style={{ backgroundColor: activity?.color ?? "var(--primary)" }}
        />
        <div>
          <p className="text-sm font-medium">{membership?.user?.full_name ?? "—"}</p>
          <p className="text-xs text-muted-foreground">{activity?.name ?? entry.activity_id}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold tabular-nums">{fmt.currency(entry.amount)}</span>
        {entry.status === "draft" && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            {t("entryDraft")}
          </span>
        )}
        {entry.status === "recorded" && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            {t("entryRecorded")}
          </span>
        )}
        {canEdit && entry.status === "draft" && (
          <button
            onClick={() => onVoid(entry.id)}
            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            aria-label={t("entryVoided")}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Add entry form ────────────────────────────────────────────────────────

function AddEntryForm({
  meetingId,
  activities,
  memberships,
  onAdded,
}: {
  meetingId: string;
  activities: Activity[];
  memberships: Membership[];
  onAdded: () => void;
}) {
  const t = useTranslations("meeting");
  const [membershipId, setMembershipId] = useState("");
  const [activityId, setActivityId] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  const visibleActivities = activities.filter((a) => a.is_visible_in_meeting && a.is_active);

  const addMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => meetingsApi.addEntry(meetingId, payload),
    onSuccess: () => {
      setMembershipId("");
      setActivityId("");
      setAmount("");
      setError("");
      onAdded();
    },
    onError: (err) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? t("addEntryError"));
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!membershipId || !activityId || !amount) {
      setError(t("requiredFields"));
      return;
    }
    addMutation.mutate({
      meeting_id: meetingId,
      membership_id: membershipId,
      activity_id: activityId,
      amount: parseInt(amount, 10),
    });
  }

  function handleActivityChange(id: string) {
    setActivityId(id);
    const act = visibleActivities.find((a) => a.id === id);
    const cfgAmount = (act?.config as { amount?: number } | undefined)?.amount;
    if (cfgAmount) setAmount(String(cfgAmount));
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-dashed border-border bg-muted/30 p-4 space-y-3">
      <p className="text-sm font-medium text-muted-foreground">{t("newEntry")}</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Select value={membershipId} onValueChange={setMembershipId}>
          <SelectTrigger className="bg-background">
            <SelectValue placeholder={t("selectMember")} />
          </SelectTrigger>
          <SelectContent>
            {memberships.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.user?.full_name ?? m.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={activityId} onValueChange={handleActivityChange}>
          <SelectTrigger className="bg-background">
            <SelectValue placeholder={t("selectActivity")} />
          </SelectTrigger>
          <SelectContent>
            {visibleActivities.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          type="number"
          inputMode="numeric"
          min={1}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder={t("amountPlaceholder")}
          aria-label={t("amountAria")}
        />
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          {error}
        </p>
      )}

      <Button type="submit" size="sm" disabled={addMutation.isPending} className="gap-2">
        {addMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
        {t("addEntry")}
      </Button>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("meeting");
  const tCommon = useTranslations("common");
  const fmt = useFormatters();
  const queryClient = useQueryClient();

  const meetingQuery = useQuery<MeetingDetail>({
    queryKey: ["meeting", id],
    queryFn: () => meetingsApi.get(id),
    enabled: !!id,
  });

  const meeting = meetingQuery.data;
  const associationId = meeting?.association_id;

  const { data: activities = [] } = useQuery<Activity[]>({
    queryKey: ["activities", associationId],
    queryFn: () => activitiesApi.list({ association_id: associationId }),
    enabled: !!associationId,
  });

  const { data: memberships = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId!),
    enabled: !!associationId,
  });

  const canEdit = meeting?.status === "ongoing";

  const reload = () => queryClient.invalidateQueries({ queryKey: ["meeting", id] });

  const openMutation = useMutation({
    mutationFn: () => meetingsApi.open(meeting!.id),
    onSuccess: reload,
  });

  const closeMutation = useMutation({
    mutationFn: () => meetingsApi.close(meeting!.id),
    onSuccess: reload,
  });

  const attendanceMutation = useMutation({
    mutationFn: ({ membershipId, status }: { membershipId: string; status: AttendanceStatus }) =>
      meetingsApi.upsertAttendances(meeting!.id, [{ membership_id: membershipId, status }]),
    onSuccess: reload,
  });

  const voidEntryMutation = useMutation({
    mutationFn: (entryId: string) => meetingsApi.voidEntry(meeting!.id, entryId),
    onSuccess: reload,
  });

  // ── Stats ────────────────────────────────────────────────────────────
  const presentCount = meeting?.attendances.filter((a) => a.status === "present" || a.status === "late").length ?? 0;
  const totalEntries = meeting?.entries.filter((e) => e.status !== "voided").length ?? 0;
  const totalAmount = meeting?.entries
    .filter((e) => e.status !== "voided")
    .reduce((s, e) => s + e.amount, 0) ?? 0;

  if (meetingQuery.isLoading) {
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

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-start">
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

        <div className="flex shrink-0 items-center gap-2">
          {meeting.status === "planned" && (
            <Button onClick={() => openMutation.mutate()} disabled={openMutation.isPending} className="gap-2">
              {openMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {t("start")}
            </Button>
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
        <div className="flex items-center gap-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          {t("bannerOngoing")}
        </div>
      )}
      {meeting.status === "closed" && (
        <div className="flex items-center gap-2 rounded-xl bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">
          <CheckCircle2 className="h-4 w-4" />
          {t("bannerClosed", { date: meeting.closed_at ? fmt.date(meeting.closed_at) : "—" })}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Users className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("statPresent")}</p>
                <p className="text-xl font-bold">{presentCount}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <ClipboardList className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("statEntries")}</p>
                <p className="text-xl font-bold">{totalEntries}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-emerald-100 dark:bg-emerald-900/30 p-2">
                <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("statCollected")}</p>
                <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">
                  {fmt.currency(meeting.status === "closed" ? meeting.total_in : totalAmount)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="entries">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="entries" className="gap-2">
            <ClipboardList className="h-4 w-4" />
            {t("tabEntries")} ({totalEntries})
          </TabsTrigger>
          <TabsTrigger value="attendance" className="gap-2">
            <Users className="h-4 w-4" />
            {t("tabAttendance")} ({meeting.attendances.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="entries" className="mt-4 space-y-4">
          {canEdit && (
            <AddEntryForm
              meetingId={meeting.id}
              activities={activities}
              memberships={memberships}
              onAdded={reload}
            />
          )}

          <Card>
            <CardContent className="p-0">
              {meeting.entries.filter((e) => e.status !== "voided").length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                  <ClipboardList className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">{t("noEntries")}</p>
                  {canEdit && <p className="text-xs mt-1">{t("noEntriesHint")}</p>}
                </div>
              ) : (
                <div className="divide-y divide-border px-4">
                  {meeting.entries
                    .filter((e) => e.status !== "voided")
                    .map((entry) => (
                      <EntryRow
                        key={entry.id}
                        entry={entry}
                        activities={activities}
                        memberships={memberships}
                        canEdit={canEdit}
                        onVoid={(eid) => voidEntryMutation.mutate(eid)}
                      />
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="attendance" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {memberships.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                  <Users className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">{t("noMembers")}</p>
                </div>
              ) : (
                <div className="divide-y divide-border px-4">
                  {memberships.map((m) => {
                    const att = meeting.attendances.find((a) => a.membership_id === m.id);
                    return (
                      <AttendanceRow
                        key={m.id}
                        membership={m}
                        attendance={att}
                        canEdit={canEdit}
                        onStatusChange={(mid, s) => attendanceMutation.mutate({ membershipId: mid, status: s })}
                      />
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
