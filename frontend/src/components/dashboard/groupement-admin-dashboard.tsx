"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Users, Calendar, Wallet, ArrowRight, Plus } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { associationsApi, meetingsApi } from "@/lib/api";
import type { Association, Meeting } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";

export function GroupementAdminDashboard() {
  const t = useTranslations("dashboard");
  const tCommon = useTranslations("common");
  const tMeeting = useTranslations("meeting");
  const { user } = useAuthStore();
  const fmt = useFormatters();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });

  // Aggregate upcoming meetings across all associations the user can see.
  const { data: meetings = [] } = useQuery<Meeting[]>({
    queryKey: ["meetings-all", associations.map((a) => a.id).join(",")],
    queryFn: async () => {
      if (associations.length === 0) return [];
      const all = await Promise.all(
        associations.map((a) => meetingsApi.list({ association_id: a.id }) as Promise<Meeting[]>)
      );
      return all.flat();
    },
    enabled: associations.length > 0,
  });

  const activeAssociations = associations.filter((a) => a.is_active).length;
  const upcomingMeetings = meetings
    .filter((m) => m.status === "planned" || m.status === "ongoing")
    .sort((a, b) => new Date(a.scheduled_on).getTime() - new Date(b.scheduled_on).getTime());

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("welcome", { name: user?.full_name?.split(" ")[0] || "" })}
        description={t("subGroupementAdmin")}
        actions={
          <Button asChild className="gap-2">
            <Link href="/dashboard/members">
              <Plus className="h-4 w-4" />
              {t("createAssociation")}
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("associationsCount")} value={activeAssociations} icon={FolderKanban} accent="brand" />
        <StatCard label={t("totalMembers")} value="—" icon={Users} accent="sky" />
        <StatCard label={t("openMeetings")} value={upcomingMeetings.length} icon={Calendar} accent="emerald" />
        <StatCard label={t("treasuryBalance")} value="—" icon={Wallet} accent="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{t("groupementOverview")}</CardTitle>
              <CardDescription>{t("groupementOverviewDesc")}</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/dashboard/members" className="gap-1">
                {t("viewAll")} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {associations.length === 0 ? (
              <EmptyState
                icon={FolderKanban}
                title={t("noAssociationsYet")}
                description={t("noAssociationsYetDesc")}
                action={
                  <Button asChild>
                    <Link href="/dashboard/members" className="gap-2">
                      <Plus className="h-4 w-4" />
                      {t("createAssociation")}
                    </Link>
                  </Button>
                }
              />
            ) : (
              <div className="space-y-2">
                {associations.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between rounded-lg border border-border/40 bg-muted/30 px-3 py-2.5 text-sm"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <FolderKanban className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{a.name}</p>
                        {a.description && (
                          <p className="truncate text-xs text-muted-foreground">{a.description}</p>
                        )}
                      </div>
                    </div>
                    {a.is_active ? (
                      <Badge variant="success">{tCommon("active")}</Badge>
                    ) : (
                      <Badge variant="secondary">{tCommon("inactive")}</Badge>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
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
            {upcomingMeetings.length === 0 ? (
              <EmptyState
                icon={Calendar}
                title={t("noMeetings")}
                description={t("noMeetingsDesc")}
              />
            ) : (
              <div className="space-y-2">
                {upcomingMeetings.slice(0, 5).map((m) => (
                  <Link
                    key={m.id}
                    href={`/dashboard/meetings/${m.id}`}
                    className="flex items-center gap-3 rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-sm transition-colors hover:bg-accent/50"
                  >
                    <Calendar className="h-4 w-4 shrink-0 text-primary" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{m.title}</p>
                      <p className="truncate text-xs text-muted-foreground">{fmt.date(m.scheduled_on)}</p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
            <Button asChild variant="outline" className="mt-3 w-full gap-2">
              <Link href="/dashboard/meetings/new">
                <Plus className="h-4 w-4" />
                {tMeeting("newMeeting")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
