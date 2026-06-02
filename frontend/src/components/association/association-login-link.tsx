"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Copy, Link2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { associationLoginUrl } from "@/lib/utils";

/** Petit panneau « lien d'accès partageable » : URL en lecture seule + bouton
 *  Copier. À utiliser sur le détail de l'association et le dashboard admin. */
export function AssociationLoginLink({
  association,
  className,
}: {
  association: { slug: string; groupement_subdomain?: string | null };
  className?: string;
}) {
  const t = useTranslations("association");
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Construit l'URL après mount pour avoir window.location dispo.
  useEffect(() => {
    setUrl(associationLoginUrl(association));
  }, [association]);

  const onCopy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success(t("loginLinkCopied"));
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("loginLinkCopyError"));
    }
  };

  if (!url) return null;

  return (
    <div className={`rounded-lg border border-border bg-muted/30 p-3 ${className ?? ""}`}>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Link2 className="h-3.5 w-3.5" />
        {t("loginLinkTitle")}
      </p>
      <div className="flex min-w-0 items-center gap-2">
        <Input readOnly value={url} className="min-w-0 flex-1 font-mono text-xs" />
        <Button type="button" size="sm" variant="outline" className="gap-1.5 shrink-0" onClick={onCopy}>
          {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
          {t("loginLinkCopy")}
        </Button>
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{t("loginLinkHint")}</p>
    </div>
  );
}
