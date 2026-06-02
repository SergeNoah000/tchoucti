"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Users, Calendar, Wallet, ArrowRight, Plus, HeartHandshake, Repeat } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/common/page-header";
import { AssociationLoginLink } from "@/components/association/association-login-link";
import { EmptyState } from "@/components/common/empty-state";
import { associationsApi, meetingsApi, membersApi } from "@/lib/api";
import type { Association, Meeting, Membership } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";

export function AssociationAdminDashboard() {
  const t = useTranslations("dashboard");
  const tMeeting = useTranslations("meeting");
  const { user } = useAuthStore();
  const fmt = useFormatters();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const associationId = associations[0]?.id;

  const { data: memberships = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId!),
    enabled: !!associationId,
  });

  const { data: meetings = [] } = useQuery<Meeting[]>({
    queryKey: ["meetings", associationId],
    queryFn: () => meetingsApi.list({ association_id: associationId }),
    enabled: !!associationId,
  });

  const activeMembers = memberships.filter((m) => m.status === "active").length;
  const upcoming = meetings
    .filter((m) => m.status === "planned" || m.status === "ongoing")
    .sort((a, b) => new Date(a.scheduled_on).getTime() - new Date(b.scheduled_on).getTime());

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("welcome", { name: user?.full_name?.split(" ")[0] || "" })}
        description={t("subAssociationAdmin")}
        actions={
          <Button asChild className="gap-2">
            <Link href="/dashboard/meetings/new">
              <Plus className="h-4 w-4" />
              {t("scheduleMeeting")}
            </Link>
          </Button>
        }
      />

      {associations[0] && <AssociationLoginLink association={associations[0]} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("membersCount")} value={activeMembers} icon={Users} accent="brand" />
        <StatCard label={t("openMeetings")} value={upcoming.length} icon={Calendar} accent="sky" />
        <StatCard label={t("monthlyCollection")} value="—" icon={Wallet} accent="emerald" />
        <StatCard label={t("treasuryBalance")} value="—" icon={Wallet} accent="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{t("upcoming")}</CardTitle>
              <CardDescription>{t("upcomingDesc")}</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/dashboard/meetings" className="gap-1">
                {t("viewAll")} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {upcoming.length === 0 ? (
              <EmptyState
                icon={Calendar}
                title={t("noMeetings")}
                description={t("noMeetingsDesc")}
                action={
                  <Button asChild>
                    <Link href="/dashboard/meetings/new" className="gap-2">
                      <Plus className="h-4 w-4" />
                      {tMeeting("newMeeting")}
                    </Link>
                  </Button>
                }
              />
            ) : (
              <div className="space-y-2">
                {upcoming.slice(0, 6).map((m) => (
                  <Link
                    key={m.id}
                    href={`/dashboard/meetings/${m.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/30 px-3 py-2.5 text-sm transition-colors hover:bg-accent/50"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <Calendar className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{m.title}</p>
                        <p className="truncate text-xs text-muted-foreground">{fmt.longDate(m.scheduled_on)}</p>
                      </div>
                    </div>
                    {m.status === "ongoing" && (
                      <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                        {tMeeting("inProgress")}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("quickActions")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/dashboard/meetings/new">
                <Plus className="h-4 w-4" />
                {tMeeting("newMeeting")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/dashboard/members">
                <Users className="h-4 w-4" />
                {t("inviteMember")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/dashboard/tontines">
                <Repeat className="h-4 w-4" />
                Tontines
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/dashboard/social-aid">
                <HeartHandshake className="h-4 w-4" />
                Aide sociale
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
