"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { OnboardingBanner } from "@/components/onboarding/onboarding-banner";
import { AidTypesManager } from "@/components/config/aid-types-manager";
import { associationsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import type { Association } from "@/lib/types";

export default function ConfigAidsPage() {
  const t = useTranslations("configAids");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { user } = useAuthStore();

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  if (!canConfigureAssociation(user)) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("notAdmin")}</p>
      </div>
    );
  }
  if (!association) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <OnboardingBanner />
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <Button variant="ghost" onClick={() => router.push("/dashboard")} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            {tCommon("back")}
          </Button>
        }
      />
      <AidTypesManager association={association} />
    </div>
  );
}
