"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Calendar, Wallet, ArrowRight, HandCoins, HeartHandshake, FileText, Plus } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { associationsApi, meetingsApi } from "@/lib/api";
import type { Association, Meeting } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";

export function MemberDashboard() {
  const t = useTranslations("dashboard");
  const tCommon = useTranslations("common");
  const tNav = useTranslations("nav");
  const { user } = useAuthStore();
  const fmt = useFormatters();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });

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

  const upcoming = meetings
    .filter((m) => m.status === "planned" || m.status === "ongoing")
    .sort((a, b) => new Date(a.scheduled_on).getTime() - new Date(b.scheduled_on).getTime());

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("welcome", { name: user?.full_name?.split(" ")[0] || "" })}
        description={t("subMember")}
        actions={
          <Button asChild variant="outline" className="gap-2">
            <Link href="/dashboard/social-aid">
              <Plus className="h-4 w-4" />
              {t("newRequest")}
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label={t("myContributionsCard")} value="—" icon={Wallet} accent="emerald" />
        <StatCard label={t("upcomingMeetings")} value={upcoming.length} icon={Calendar} accent="sky" />
        <StatCard label={tNav("myLoans")} value="—" icon={HandCoins} accent="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{t("myMeetings")}</CardTitle>
              <CardDescription>{t("myMeetingsDesc")}</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/dashboard/meetings" className="gap-1">
                {t("viewAll")} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {upcoming.length === 0 ? (
              <EmptyState icon={Calendar} title={t("noMeetings")} description={t("noMeetingsDesc")} />
            ) : (
              <div className="space-y-2">
                {upcoming.slice(0, 5).map((m) => (
                  <Link
                    key={m.id}
                    href={`/dashboard/meetings/${m.id}`}
                    className="flex items-center gap-3 rounded-lg border border-border/40 bg-muted/30 px-3 py-2.5 text-sm transition-colors hover:bg-accent/50"
                  >
                    <div className="flex h-9 w-9 shrink-0 flex-col items-center justify-center rounded-md bg-primary/10 text-primary">
                      <span className="text-xs font-bold leading-none">
                        {fmt.dayMonth(m.scheduled_on).day}
                      </span>
                      <span className="text-[9px] uppercase tracking-wide">
                        {fmt.dayMonth(m.scheduled_on).month}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{m.title}</p>
                      {m.location && (
                        <p className="truncate text-xs text-muted-foreground">{m.location}</p>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("myAssociations")}</CardTitle>
            <CardDescription>{t("myAssociationsDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            {associations.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">{tCommon("noData")}</p>
            ) : (
              <div className="space-y-2">
                {associations.map((a) => (
                  <div
                    key={a.id}
                    className="rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-sm"
                  >
                    <p className="truncate font-medium">{a.name}</p>
                    {a.description && (
                      <p className="truncate text-xs text-muted-foreground">{a.description}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("myRequests")}</CardTitle>
          <CardDescription>{t("myRequestsDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
            <Link href="/dashboard/loans">
              <HandCoins className="h-4 w-4" />
              {tNav("myLoans")}
            </Link>
          </Button>
          <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
            <Link href="/dashboard/social-aid">
              <HeartHandshake className="h-4 w-4" />
              {tNav("socialAid")}
            </Link>
          </Button>
          <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
            <Link href="/dashboard/finance">
              <Wallet className="h-4 w-4" />
              {tNav("myContributions")}
            </Link>
          </Button>
          <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
            <Link href="/dashboard/documents">
              <FileText className="h-4 w-4" />
              {tNav("documents")}
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
