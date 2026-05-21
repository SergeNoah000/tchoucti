"use client";

import { useTranslations } from "next-intl";
import {
  Users,
  Wallet,
  Banknote,
  Repeat,
  HeartHandshake,
  FolderKanban,
  FileText,
  BarChart3,
  Settings,
  CreditCard,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ComingSoon } from "./coming-soon";
import { PageHeader } from "./page-header";

type PlaceholderNs =
  | "members"
  | "finance"
  | "loans"
  | "tontines"
  | "socialAid"
  | "projects"
  | "documents"
  | "reports"
  | "settings"
  | "myContributions"
  | "myLoans"
  | "billing"
  | "audit"
  | "adminSettings";

/** Map of ns → icon so server-rendered pages can pass a string-only prop. */
const ICONS: Record<PlaceholderNs, LucideIcon> = {
  members: Users,
  finance: Wallet,
  loans: Banknote,
  tontines: Repeat,
  socialAid: HeartHandshake,
  projects: FolderKanban,
  documents: FileText,
  reports: BarChart3,
  settings: Settings,
  myContributions: Wallet,
  myLoans: Banknote,
  billing: CreditCard,
  audit: ScrollText,
  adminSettings: Settings,
};

interface PlaceholderPageProps {
  ns: PlaceholderNs;
}

export function PlaceholderPage({ ns }: PlaceholderPageProps) {
  const t = useTranslations("placeholder");
  const Icon = ICONS[ns];

  return (
    <div className="space-y-6">
      <PageHeader
        title={t(`${ns}.title`)}
        description={t(`${ns}.description`)}
        badge={t("comingSoon")}
      />
      <Card>
        <CardContent className="p-0">
          <ComingSoon
            icon={Icon}
            title={t(`${ns}.title`)}
            description={t(`${ns}.description`)}
            sprintLabel={t("sprintLabel")}
          />
        </CardContent>
      </Card>
    </div>
  );
}
