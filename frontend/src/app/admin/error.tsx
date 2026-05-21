"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errors");

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
        <AlertTriangle className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold">{t("oops")}</h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">{t("generic")}</p>
      <Button onClick={reset} className="mt-5 gap-2">
        <RotateCw className="h-4 w-4" />
        {t("tryAgain")}
      </Button>
    </div>
  );
}
