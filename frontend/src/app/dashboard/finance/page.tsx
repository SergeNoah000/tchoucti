"use client";

import { useAuthStore } from "@/lib/store";
import { detectRole } from "@/lib/roles";
import { PlaceholderPage } from "@/components/common/placeholder-page";

export default function FinancePage() {
  const { user } = useAuthStore();
  const role = detectRole(user);
  return <PlaceholderPage ns={role === "member" ? "myContributions" : "finance"} />;
}
