"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Building2, Users, BarChart3, ArrowRight, ScrollText, CreditCard, Settings } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/common/page-header";
import { api, groupementsApi } from "@/lib/api";
import type { Groupement, User } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

export default function AdminHome() {
  const t = useTranslations("admin");
  const tDash = useTranslations("dashboard");
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
        title={tDash("welcome", { name: user?.full_name?.split(" ")[0] || "" })}
        description={t("subtitle")}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("totalGroupements")} value={groupements.length} icon={Building2} accent="brand" />
        <StatCard label={tDash("associations")} value={activeGroupements} icon={Building2} accent="emerald" />
        <StatCard label={t("totalUsers")} value={users.length} icon={Users} accent="sky" />
        <StatCard label={t("monthlySignups")} value="—" icon={BarChart3} accent="amber" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{tNav("groupements")}</CardTitle>
              <CardDescription>Gérer les locataires de la plateforme.</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/admin/groupements" className="gap-1">
                {tDash("viewAll")} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {groupements.slice(0, 4).map((g) => (
              <Link
                key={g.id}
                href={`/admin/groupements/${g.id}`}
                className="flex items-center justify-between rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-sm transition-colors hover:bg-accent/50"
              >
                <span className="font-medium">{g.name}</span>
                <span className="text-xs text-muted-foreground font-mono">{g.slug}</span>
              </Link>
            ))}
            {groupements.length === 0 && (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("empty")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Accès rapide</CardTitle>
            <CardDescription>Les espaces clefs de l&apos;administration plateforme.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2">
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
              <Link href="/admin/billing">
                <CreditCard className="h-4 w-4" />
                {tNav("billing")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-2 py-3">
              <Link href="/admin/audit">
                <ScrollText className="h-4 w-4" />
                {tNav("audit")}
              </Link>
            </Button>
            <Button asChild variant="outline" className="col-span-2 h-auto justify-start gap-2 py-3">
              <Link href="/admin/settings">
                <Settings className="h-4 w-4" />
                {tNav("settings")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
