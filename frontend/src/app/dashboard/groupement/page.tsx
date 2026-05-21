"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { AlertCircle } from "lucide-react";

import { GroupementDetail } from "@/components/groupement/groupement-detail";
import { Skeleton } from "@/components/ui/skeleton";
import { groupementsApi } from "@/lib/api";
import type { Groupement } from "@/lib/types";

export default function MyGroupementPage() {
  const tCommon = useTranslations("common");

  const { data: groupement, isLoading, isError } = useQuery<Groupement>({
    queryKey: ["my-groupement"],
    queryFn: groupementsApi.getMine,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !groupement) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <AlertCircle className="mb-4 h-12 w-12 text-muted-foreground" />
        <p className="text-lg font-semibold">{tCommon("noData")}</p>
      </div>
    );
  }

  // No back button — this is the admin's home base for their groupement.
  return <GroupementDetail groupementId={groupement.id} />;
}
