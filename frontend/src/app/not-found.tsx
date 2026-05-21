"use client";

import { useTranslations } from "next-intl";
import { FileQuestion, Home } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const t = useTranslations("errors");

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <div className="flex max-w-md flex-col items-center text-center">
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <FileQuestion className="h-8 w-8" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("notFound")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("notFoundDesc")}</p>
        <Button asChild className="mt-6 gap-2">
          <Link href="/">
            <Home className="h-4 w-4" />
            {t("goHome")}
          </Link>
        </Button>
      </div>
    </div>
  );
}
