"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import {
  Users,
  Wallet,
  Banknote,
  Repeat,
  HeartHandshake,
  Building2,
  ShieldCheck,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BrandMark } from "@/components/common/brand-mark";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { LanguageToggle } from "@/components/common/language-toggle";

export default function LandingPage() {
  const t = useTranslations("landing");
  const tRoles = useTranslations("roles");

  const features = [
    { icon: Users, titleKey: "feature1Title", descKey: "feature1Desc", accent: "from-brand-500/20 to-brand-700/5" },
    { icon: Wallet, titleKey: "feature2Title", descKey: "feature2Desc", accent: "from-emerald-500/20 to-emerald-700/5" },
    { icon: Banknote, titleKey: "feature3Title", descKey: "feature3Desc", accent: "from-amber-500/20 to-amber-700/5" },
    { icon: Repeat, titleKey: "feature4Title", descKey: "feature4Desc", accent: "from-sky-500/20 to-sky-700/5" },
    { icon: HeartHandshake, titleKey: "feature5Title", descKey: "feature5Desc", accent: "from-rose-500/20 to-rose-700/5" },
    { icon: Building2, titleKey: "feature6Title", descKey: "feature6Desc", accent: "from-violet-500/20 to-violet-700/5" },
  ];

  const roles = [
    "president", "vice_president", "secretary", "treasurer", "censor", "manager", "member",
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-brand-50/30 to-background dark:from-background dark:via-brand-950/10 dark:to-background">
      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-border/40">
        <div className="container mx-auto flex h-16 items-center justify-between">
          <BrandMark />
          <div className="flex items-center gap-3">
            <LanguageToggle />
            <ThemeToggle />
            <Button variant="ghost" size="sm" asChild className="hidden md:inline-flex">
              <Link href="/login">{t("proSpace")}</Link>
            </Button>
            <Button size="sm" variant="brand" asChild>
              <Link href="/login" className="gap-2">
                <span className="md:hidden">{t("proSpace")}</span>
                <span className="hidden md:inline">{t("ctaPrimary")}</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-0 left-1/2 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-brand-500/10 blur-3xl" />
        </div>
        <div className="container mx-auto py-20 lg:py-28">
          <div className="mx-auto max-w-3xl text-center animate-slide-up">
            <Badge variant="brand" className="mb-6 inline-flex gap-1.5 px-3 py-1">
              <Sparkles className="h-3.5 w-3.5" />
              {t("featuresSubtitle")}
            </Badge>
            <h1 className="text-balance text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
              {t("heroTitle")}
              <span className="text-gradient-brand">{t("heroHighlight")}</span>
            </h1>
            <p className="mt-6 text-balance text-lg leading-relaxed text-muted-foreground">
              {t("heroSubtitle")}
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button size="xl" variant="brand" asChild className="w-full sm:w-auto">
                <Link href="/login" className="gap-2">
                  {t("ctaPrimary")}
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="xl" variant="outline" asChild className="w-full sm:w-auto">
                <Link href="#features">{t("ctaSecondary")}</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20">
        <div className="container mx-auto">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
              {t("featuresTitle")}
            </h2>
            <p className="mt-4 text-balance text-muted-foreground">{t("featuresSubtitle")}</p>
          </div>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {features.map(({ icon: Icon, titleKey, descKey, accent }) => (
              <Card key={titleKey} className="group relative overflow-hidden transition-all hover:-translate-y-1 hover:shadow-lg">
                <div className={`absolute inset-0 bg-gradient-to-br ${accent} opacity-0 transition-opacity group-hover:opacity-100`} />
                <CardContent className="relative p-6">
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300">
                    <Icon className="h-6 w-6" />
                  </div>
                  <h3 className="mb-2 text-lg font-semibold">{t(titleKey)}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{t(descKey)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Roles */}
      <section className="py-20 bg-muted/30">
        <div className="container mx-auto">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("rolesTitle")}</h2>
            <p className="mt-4 text-muted-foreground">{t("rolesSubtitle")}</p>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            {roles.map((r) => (
              <Badge key={r} variant="outline" className="px-4 py-2 text-sm font-medium">
                <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
                {tRoles(r)}
              </Badge>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/40 py-12">
        <div className="container mx-auto">
          <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
            <BrandMark size="sm" />
            <p className="text-center text-sm text-muted-foreground">
              {t("footer", { year: new Date().getFullYear() })}
            </p>
            <p className="text-xs italic text-muted-foreground">{t("footerTagline")}</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
