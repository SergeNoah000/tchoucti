"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Calendar,
  Plus,
  Clock,
  CheckCircle2,
  XCircle,
  PlayCircle,
  MapPin,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { meetingsApi, associationsApi } from "@/lib/api";
import type { Meeting, Association, MeetingStatus } from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_CLASSES: Record<MeetingStatus, { icon: LucideIcon; pill: string }> = {
  planned: {
    icon: Clock,
    pill: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  ongoing: {
    icon: PlayCircle,
    pill: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  },
  closed: {
    icon: CheckCircle2,
    pill: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  },
  cancelled: {
    icon: XCircle,
    pill: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  },
};

function StatusBadge({ status }: { status: MeetingStatus }) {
  const t = useTranslations("meeting");
  const cfg = STATUS_CLASSES[status] ?? STATUS_CLASSES.planned;
  const Icon = cfg.icon;
  const label =
    status === "planned" ? t("scheduled")
    : status === "ongoing" ? t("inProgress")
    : status === "closed" ? t("closed")
    : t("cancelled");
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", cfg.pill)}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

function MeetingCard({ meeting }: { meeting: Meeting }) {
  const fmt = useFormatters();
  const { day, month } = fmt.dayMonth(meeting.scheduled_on);

  return (
    <Link href={`/dashboard/meetings/${meeting.id}`} className="block group">
      <div className="flex items-start justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm group-hover:bg-accent/30">
        <div className="flex min-w-0 gap-4">
          <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg bg-primary/10 text-primary">
            <span className="text-lg font-bold leading-none">{day}</span>
            <span className="text-[10px] uppercase tracking-wide">{month}</span>
          </div>
          <div className="min-w-0 space-y-1">
            <p className="truncate font-semibold text-foreground leading-tight">{meeting.title}</p>
            {meeting.location && (
              <p className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                <MapPin className="h-3 w-3 shrink-0" />
                {meeting.location}
              </p>
            )}
            <p className="text-xs text-muted-foreground">{fmt.longDate(meeting.scheduled_on)}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <StatusBadge status={meeting.status} />
          {meeting.status === "closed" && meeting.total_in > 0 && (
            <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 tabular-nums">
              +{fmt.currency(meeting.total_in)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function MeetingsPage() {
  const t = useTranslations("meeting");

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const associationId = associations[0]?.id;

  const { data: meetings = [], isLoading } = useQuery<Meeting[]>({
    queryKey: ["meetings", associationId],
    queryFn: () => meetingsApi.list({ association_id: associationId }),
    enabled: !!associationId,
  });

  const ongoing = meetings.filter((m) => m.status === "ongoing");
  const planned = meetings.filter((m) => m.status === "planned");
  const closed = meetings.filter((m) => m.status === "closed");

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <Button asChild>
            <Link href="/dashboard/meetings/new" className="gap-2">
              <Plus className="h-4 w-4" />
              {t("create")}
            </Link>
          </Button>
        }
      />

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}

      {!isLoading && meetings.length === 0 && (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Calendar}
              title={t("empty")}
              description={t("emptyDesc")}
              action={
                <Button asChild>
                  <Link href="/dashboard/meetings/new" className="gap-2">
                    <Plus className="h-4 w-4" />
                    {t("create")}
                  </Link>
                </Button>
              }
            />
          </CardContent>
        </Card>
      )}

      {!isLoading && ongoing.length > 0 && (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            {t("groupOngoing")} ({ongoing.length})
          </h2>
          {ongoing.map((m) => <MeetingCard key={m.id} meeting={m} />)}
        </section>
      )}

      {!isLoading && planned.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("groupScheduled")} ({planned.length})
          </h2>
          {planned.map((m) => <MeetingCard key={m.id} meeting={m} />)}
        </section>
      )}

      {!isLoading && closed.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("groupClosed")} ({closed.length})
          </h2>
          {closed.map((m) => <MeetingCard key={m.id} meeting={m} />)}
        </section>
      )}
    </div>
  );
}
