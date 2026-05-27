import { Shell } from "@/components/layout/shell";
import { OnboardingGate } from "@/components/onboarding/onboarding-gate";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <Shell>
      <OnboardingGate>{children}</OnboardingGate>
    </Shell>
  );
}
