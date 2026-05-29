"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Building2, Users, BarChart3, ArrowRight, Plus, FolderKanban } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { api, groupementsApi } from "@/lib/api";
import type { Groupement, User } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { groupementHost } from "@/lib/utils";

export function SuperAdminDashboard() {
  const t = useTranslations("dashboard");
  const tCommon = useTranslations("common");
  const tNav = useTranslations("nav");
  const { user } = useAuthStore();

  const { data: groupements = [] } = useQuery<Groupement[]>({
    queryKey: ["groupements"],
    queryFn: groupementsApi.list,
  });

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ["admin_users"],
    queryFn: async () => (await api.get("/users")).data,
  });

  const activeGroupements = groupements.filter((g) => g.is_active).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("welcome", { name: user?.full_name?.split(" ")[0] || "" })}
        description={t("subSuperAdmin")}
        actions={
          <Button asChild className="gap-2">
            <Link href="/admin/groupements">
              <Plus className="h-4 w-4" />
              {t("createGroupement")}
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("totalGroupements")} value={groupements.length} icon={Building2} accent="brand" />
        <StatCard label={t("totalUsers")} value={users.length} icon={Users} accent="sky" />
        <StatCard label={t("associationsCount")} value={activeGroupements} icon={FolderKanban} accent="emerald" />
        <StatCard label={t("monthlySignups")} value="—" icon={BarChart3} accent="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{tNav("groupements")}</CardTitle>
              <CardDescription>{t("platformOverviewDesc")}</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/admin/groupements" className="gap-1">
                {t("viewAll")} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {groupements.length === 0 ? (
              <EmptyState
                icon={Building2}
                title={t("noAssociationsYet")}
                description={t("noAssociationsYetDesc")}
              />
            ) : (
              <div className="space-y-2">
                {groupements.slice(0, 5).map((g) => (
                  <Link
                    key={g.id}
                    href={`/admin/groupements/${g.id}`}
                    className="flex items-center justify-between rounded-lg border border-border/40 bg-muted/30 px-3 py-2.5 text-sm transition-colors hover:bg-accent/50"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <Building2 className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{g.name}</p>
                        <p className="truncate font-mono text-xs text-muted-foreground">{groupementHost(g)}</p>
                      </div>
                    </div>
                    {g.is_active ? (
                      <Badge variant="success">{tCommon("active")}</Badge>
                    ) : (
                      <Badge variant="secondary">{tCommon("inactive")}</Badge>
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
              <Link href="/admin/groupements">
                <Building2 className="h-4 w-4" />
                {tNav("groupements")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/admin/users">
                <Users className="h-4 w-4" />
                {tNav("users")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/admin/audit">
                <BarChart3 className="h-4 w-4" />
                {tNav("audit")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
