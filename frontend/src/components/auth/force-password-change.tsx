"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Loader2, KeyRound, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

function extractError(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}

/**
 * Écran bloquant affiché tant que `user.must_change_password` est vrai : oblige
 * le membre (compte créé avec un mot de passe par défaut) à définir son propre
 * mot de passe avant d'accéder à l'application.
 */
export function ForcePasswordChange() {
  const t = useTranslations("forcePassword");
  const { setUser } = useAuthStore();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      await authApi.changePassword({ current_password: current, new_password: next });
      // Rafraîchit /me : must_change_password repasse à false → débloque l'app.
      const fresh = await authApi.getMe();
      setUser(fresh);
    },
    onSuccess: () => toast.success(t("done")),
    onError: (err) => setError(extractError(err) ?? t("error")),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (next.length < 6) {
      setError(t("tooShort"));
      return;
    }
    if (next !== confirm) {
      setError(t("mismatch"));
      return;
    }
    mutation.mutate();
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <KeyRound className="h-5 w-5" />
          </div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="fp-current">{t("current")}</Label>
              <div className="relative">
                <Input
                  id="fp-current"
                  type={show ? "text" : "password"}
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShow((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                  tabIndex={-1}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fp-new">{t("new")}</Label>
              <Input
                id="fp-new"
                type={show ? "text" : "password"}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fp-confirm">{t("confirm")}</Label>
              <Input
                id="fp-confirm"
                type={show ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>

            {error && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" disabled={mutation.isPending} className="w-full gap-2">
              {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
