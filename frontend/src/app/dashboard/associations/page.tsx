"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { AssociationsList } from "@/components/association/associations-list";
import { groupementsApi } from "@/lib/api";
import type { Groupement } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";

export default function DashboardAssociationsPage() {
  const t = useTranslations("association");
  const { user } = useAuthStore();
  const role = detectRole(user);

  // Only a groupement admin creates associations (in their own groupement).
  const canCreate = role === "groupement_admin";

  const { data: myGroupement } = useQuery<Groupement>({
    queryKey: ["my-groupement"],
    queryFn: groupementsApi.getMine,
    enabled: canCreate,
  });

  const isMember = role === "member";

  return (
    <AssociationsList
      title={isMember ? t("listTitleMember") : t("listTitleGroupement")}
      subtitle={isMember ? t("listSubtitleMember") : t("listSubtitleGroupement")}
      detailHrefBase="/dashboard/associations"
      createGroupementId={myGroupement?.id}
      canCreate={canCreate && !!myGroupement?.id}
    />
  );
}
