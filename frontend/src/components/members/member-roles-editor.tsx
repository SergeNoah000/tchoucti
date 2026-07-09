"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { membersApi } from "@/lib/api";

/** Rôles de bureau attribuables à un membre (le rôle « member » est la base et
 *  reste toujours présent). Le trésorier est celui qui valide les sorties
 *  d'argent (décaissements de prêts, versements…). */
const ASSIGNABLE = [
  { code: "treasurer", key: "treasurer" },
  { code: "censor", key: "censor" },
  { code: "association_manager", key: "association_manager" },
  { code: "association_admin", key: "association_admin" },
] as const;

function extractError(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}

export function MemberRolesEditor({
  membershipId,
  currentCodes,
}: {
  membershipId: string;
  currentCodes: string[];
}) {
  const t = useTranslations("memberDetail");
  const tRoles = useTranslations("roles");
  const qc = useQueryClient();

  const initial = useMemo(
    () => new Set(currentCodes.filter((c) => c !== "member")),
    [currentCodes],
  );
  const [selected, setSelected] = useState<Set<string>>(initial);

  const dirty = useMemo(() => {
    if (selected.size !== initial.size) return true;
    for (const c of selected) if (!initial.has(c)) return true;
    return false;
  }, [selected, initial]);

  const toggle = (code: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  const save = useMutation({
    mutationFn: () =>
      membersApi.update(membershipId, {
        // On conserve toujours le rôle de base « member » + les fonctions choisies.
        role_codes: ["member", ...Array.from(selected)],
      }),
    onSuccess: () => {
      toast.success(t("rolesSaved"));
      qc.invalidateQueries({ queryKey: ["membership", membershipId] });
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => toast.error(extractError(e) || t("rolesError")),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4" /> {t("rolesTitle")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t("rolesHint")}</p>
        <div className="space-y-2.5">
          {ASSIGNABLE.map((r) => (
            <label
              key={r.code}
              className="flex items-center justify-between gap-3 rounded-lg border border-border/50 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{tRoles(r.key)}</p>
                {r.code === "treasurer" && (
                  <p className="text-xs text-muted-foreground">{t("treasurerHint")}</p>
                )}
              </div>
              <Switch
                checked={selected.has(r.code)}
                onCheckedChange={() => toggle(r.code)}
              />
            </label>
          ))}
        </div>
        <div className="flex justify-end">
          <Button size="sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("rolesSave")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
