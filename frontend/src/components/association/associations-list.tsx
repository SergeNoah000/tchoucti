"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronRight } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { CreateAssociationDialog } from "./create-association-dialog";
import { associationsApi } from "@/lib/api";
import type { Association, Groupement } from "@/lib/types";

interface AssociationsListProps {
  title: string;
  subtitle: string;
  /** Base path for detail links, e.g. "/dashboard/associations". */
  detailHrefBase: string;
  /** When set, create is scoped to this groupement. */
  createGroupementId?: string;
  /** When set (and createGroupementId absent), create shows a groupement picker. */
  createGroupements?: Groupement[];
  /** Whether the create button is shown. */
  canCreate: boolean;
}

export function AssociationsList({
  title,
  subtitle,
  detailHrefBase,
  createGroupementId,
  createGroupements,
  canCreate,
}: AssociationsListProps) {
  const tCommon = useTranslations("common");
  const t = useTranslations("association");

  const { data: associations = [], isLoading } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description={subtitle}
        actions={
          canCreate && (
            <CreateAssociationDialog
              groupementId={createGroupementId}
              groupements={createGroupements}
            />
          )
        }
      />

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : associations.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Building2}
              title={t("empty")}
              description={canCreate ? t("emptyDesc") : undefined}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {associations.map((a) => (
            <Link
              key={a.id}
              href={`${detailHrefBase}/${a.id}`}
              className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Building2 className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate font-semibold leading-tight">{a.name}</p>
                  {a.description ? (
                    <p className="truncate text-xs text-muted-foreground">{a.description}</p>
                  ) : (
                    <p className="truncate font-mono text-xs text-muted-foreground">{a.slug}</p>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {a.is_active ? (
                  <Badge variant="success">{tCommon("active")}</Badge>
                ) : (
                  <Badge variant="secondary">{tCommon("inactive")}</Badge>
                )}
                <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
