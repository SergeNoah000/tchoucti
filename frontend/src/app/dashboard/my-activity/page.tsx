"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { MemberActivityView } from "@/components/members/member-activity-view";
import { associationsApi, membersApi } from "@/lib/api";
import type { Association, Membership } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { UserCircle2 } from "lucide-react";

export default function MyActivityPage() {
  const t = useTranslations("memberActivity");
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  // Résout l'adhésion du membre courant dans l'association active.
  const { data: memberships = [], isLoading } = useQuery<Membership[]>({
    queryKey: ["memberships", association?.id],
    queryFn: () => membersApi.list(association!.id),
    enabled: !!association?.id,
  });
  const mine = memberships.find((m) => m.user?.id === user?.id);

  return (
    <div className="space-y-6">
      <PageHeader title={t("myTitle")} description={t("mySubtitle")} />
      {isLoading || !association ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : !mine ? (
        <EmptyState icon={UserCircle2} title={t("noMembership")} />
      ) : (
        <MemberActivityView membershipId={mine.id} currency={association.currency} />
      )}
    </div>
  );
}
