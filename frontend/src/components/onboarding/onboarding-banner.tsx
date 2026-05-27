"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Bannière "Retour au wizard d'onboarding" affichée seulement quand
 * la page est ouverte avec `?from=onboarding` (par les liens du wizard).
 * Permet à l'admin de revenir au flow guidé après avoir configuré une
 * section précise.
 */
export function OnboardingBanner() {
  const t = useTranslations("onboarding");
  const search = useSearchParams();
  const from = search?.get("from");
  if (from !== "onboarding") return null;

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5">
      <p className="flex items-center gap-2 text-sm text-foreground">
        <Sparkles className="h-4 w-4 text-primary" />
        {t("inWizardHint")}
      </p>
      <Button asChild variant="outline" size="sm" className="gap-1.5">
        <Link href="/dashboard/onboarding">
          <ArrowLeft className="h-3.5 w-3.5" />
          {t("backToWizard")}
        </Link>
      </Button>
    </div>
  );
}
