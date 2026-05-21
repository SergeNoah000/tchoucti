"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";
import { Skeleton } from "@/components/ui/skeleton";
import { SuperAdminDashboard } from "@/components/dashboard/super-admin-dashboard";
import { GroupementAdminDashboard } from "@/components/dashboard/groupement-admin-dashboard";
import { AssociationAdminDashboard } from "@/components/dashboard/association-admin-dashboard";
import { MemberDashboard } from "@/components/dashboard/member-dashboard";

export default function DashboardPage() {
  const router = useRouter();
  const { user, hasHydrated } = useAuthStore();
  const role = detectRole(user);

  // Super-admins live under /admin; if they landed on /dashboard, redirect.
  useEffect(() => {
    if (hasHydrated && user?.is_platform_admin) {
      router.replace("/admin");
    }
  }, [hasHydrated, user, router]);

  if (!hasHydrated || !user) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  switch (role) {
    case "super_admin":
      return <SuperAdminDashboard />;
    case "groupement_admin":
      return <GroupementAdminDashboard />;
    case "association_admin":
      return <AssociationAdminDashboard />;
    case "member":
    default:
      return <MemberDashboard />;
  }
}
