"use client";

import { useQuery } from "@tanstack/react-query";
import { Users, MoreHorizontal } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export default function AdminUsers() {
  const tCommon = useTranslations("common");
  const tRoles = useTranslations("roles");
  const tNav = useTranslations("nav");

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ["admin_users"],
    queryFn: async () => (await api.get("/users")).data,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={tNav("users")}
        description="Liste complète des utilisateurs enregistrés sur la plateforme."
      />

      <Card>
        <CardHeader>
          <CardTitle>Tous les utilisateurs</CardTitle>
          <CardDescription>
            Vue d&apos;ensemble de tous les membres, admins de groupements et super admins.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : users.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Aucun utilisateur"
              description="Aucun utilisateur n'est encore inscrit sur la plateforme."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Nom complet</th>
                    <th className="px-4 py-3 font-medium">{tCommon("email")}</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">{tCommon("status")}</th>
                    <th className="px-4 py-3 font-medium">{tCommon("actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {users.map((u) => (
                    <tr key={u.id} className="transition-colors hover:bg-muted/50">
                      <td className="px-4 py-3 font-medium">{u.full_name}</td>
                      <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" className="text-xs">
                          {u.is_platform_admin ? tRoles("super_admin") : tRoles("member")}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        {u.is_active ? (
                          <Badge variant="success">{tCommon("active")}</Badge>
                        ) : (
                          <Badge variant="secondary">{tCommon("inactive")}</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
