"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Users, Clock } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, membersApi } from "@/lib/api";
import type { Association, Membership } from "@/lib/types";
import { initials } from "@/lib/utils";
import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";

const ALL = "__all__";

export default function MembersPage() {
  const t = useTranslations("member");
  const tCommon = useTranslations("common");
  const tRoles = useTranslations("roles");
  const { user } = useAuthStore();
  const role = detectRole(user);
  const isGroupementLevel = role === "groupement_admin" || role === "super_admin";

  const [filter, setFilter] = useState<string>(ALL);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });

  // Aggregate members across every visible association — works for all roles.
  const { data: members = [], isLoading } = useQuery<Membership[]>({
    queryKey: ["members-consolidated", associations.map((a) => a.id).join(",")],
    queryFn: async () => {
      if (associations.length === 0) return [];
      const byAssoc = await Promise.all(
        associations.map(async (a) => {
          const list: Membership[] = await membersApi.list(a.id);
          return list.map((m) => ({ ...m, association_name: a.name }));
        })
      );
      return byAssoc.flat();
    },
    enabled: associations.length > 0,
  });

  const filtered = filter === ALL ? members : members.filter((m) => m.association_id === filter);

  return (
    <div className="space-y-6">
      <PageHeader
        title={isGroupementLevel ? t("centralTitle") : t("title")}
        description={isGroupementLevel ? t("centralSubtitle") : t("subtitle")}
        actions={
          associations.length > 1 ? (
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder={t("filterAssociation")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t("allAssociations")}</SelectItem>
                {associations.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={Users} title={t("empty")} />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{tCommon("name")}</th>
                  <th className="px-4 py-3 font-medium">{tCommon("email")}</th>
                  <th className="px-4 py-3 font-medium">{tCommon("description")}</th>
                  <th className="px-4 py-3 font-medium">{t("role")}</th>
                  <th className="px-4 py-3 font-medium">{tCommon("status")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((m) => (
                  <tr key={m.id} className="transition-colors hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                          {initials(m.user.full_name)}
                        </div>
                        <span className="font-medium">{m.user.full_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{m.user.email}</td>
                    <td className="px-4 py-3 text-muted-foreground">{m.association_name ?? "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {m.roles.length === 0 ? (
                          <span className="text-xs text-muted-foreground">{tRoles("member")}</span>
                        ) : (
                          m.roles.map((r) => (
                            <Badge key={r.id} variant="outline" className="text-[10px]">
                              {roleLabel(tRoles, r.code)}
                            </Badge>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {!m.user.is_active ? (
                        <Badge variant="warning" className="gap-1">
                          <Clock className="h-3 w-3" />
                          {t("pending")}
                        </Badge>
                      ) : m.status === "active" ? (
                        <Badge variant="success">{t("statusActive")}</Badge>
                      ) : m.status === "suspended" ? (
                        <Badge variant="destructive">{t("statusSuspended")}</Badge>
                      ) : (
                        <Badge variant="secondary">{t("statusResigned")}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function roleLabel(tRoles: (k: string) => string, code: string): string {
  try {
    return tRoles(code);
  } catch {
    return code;
  }
}
