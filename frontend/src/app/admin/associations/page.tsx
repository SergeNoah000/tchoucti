"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { AssociationsList } from "@/components/association/associations-list";
import { groupementsApi } from "@/lib/api";
import type { Groupement } from "@/lib/types";

export default function AdminAssociationsPage() {
  const t = useTranslations("association");

  const { data: groupements = [] } = useQuery<Groupement[]>({
    queryKey: ["groupements"],
    queryFn: groupementsApi.list,
  });

  return (
    <AssociationsList
      title={t("listTitleSuper")}
      subtitle={t("listSubtitleSuper")}
      detailHrefBase="/admin/associations"
      createGroupements={groupements}
      canCreate={groupements.length > 0}
    />
  );
}
