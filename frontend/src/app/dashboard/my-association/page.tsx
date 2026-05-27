"use client";

import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { AssociationDetail } from "@/components/association/association-detail";
import { associationsApi } from "@/lib/api";
import type { Association } from "@/lib/types";

/**
 * Vue "Mon association" pour l'admin d'association — réutilise le composant
 * de détail (le même qu'à /dashboard/associations/[id]) mais sans le contexte
 * "liste de plusieurs associations" qui n'a pas de sens pour ce rôle.
 */
export default function MyAssociationPage() {
  const { data: associations = [], isLoading } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  if (isLoading || !association) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  return <AssociationDetail associationId={association.id} />;
}
