"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { associationsApi, setupApi } from "@/lib/api";
import type { Association } from "@/lib/types";

/**
 * Redirects the association admin to /dashboard/onboarding when their
 * association still has `setup_complete=false`. Other roles pass through
 * untouched. While on /dashboard/onboarding the gate stays out of the way
 * so the wizard can render.
 */
export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, hasHydrated } = useAuthStore();
  const isAdmin = canConfigureAssociation(user);
  // Only the strict association_admin gets the wizard. Super/groupement admins
  // already manage many associations and don't need the per-asso onboarding push.
  const isAssocAdminOnly = !!user?.is_association_admin && !user?.is_platform_admin && !user?.is_groupement_admin;

  const { data: associations } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
    enabled: isAssocAdminOnly && hasHydrated,
  });
  const association = associations?.[0];

  const { data: setupState } = useQuery<{ setup_complete: boolean; setup_step: number }>({
    queryKey: ["setup-state", association?.id],
    queryFn: () => setupApi.getState(association!.id),
    enabled: !!association?.id && isAssocAdminOnly,
  });

  useEffect(() => {
    if (!hasHydrated || !isAssocAdminOnly || !setupState) return;
    if (setupState.setup_complete) return;
    if (pathname?.startsWith("/dashboard/onboarding")) return;
    router.replace("/dashboard/onboarding");
  }, [hasHydrated, isAssocAdminOnly, setupState, pathname, router]);

  // Avoid flashing the dashboard before the redirect fires.
  if (
    isAssocAdminOnly &&
    setupState &&
    !setupState.setup_complete &&
    !pathname?.startsWith("/dashboard/onboarding")
  ) {
    return null;
  }

  // Non-admins or super-admins shouldn't see the wizard route — bounce them.
  if (pathname?.startsWith("/dashboard/onboarding") && isAdmin === false) {
    if (typeof window !== "undefined") router.replace("/dashboard");
    return null;
  }

  return <>{children}</>;
}
