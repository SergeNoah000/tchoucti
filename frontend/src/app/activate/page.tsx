"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, AlertCircle, Eye, EyeOff, Loader2, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BrandMark } from "@/components/common/brand-mark";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { LanguageToggle } from "@/components/common/language-toggle";
import { invitationsApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import type { InvitationPeek } from "@/lib/types";

export default function ActivatePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations("activate");
  const tRoles = useTranslations("roles");
  const fmt = useFormatters();

  const token = searchParams.get("token") || "";

  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [fullName, setFullName] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  // Peek the invitation to render context (who invited, role, groupement).
  const { data: peek, isLoading: peeking, isError: peekError } = useQuery<InvitationPeek>({
    queryKey: ["invitation-peek", token],
    queryFn: () => invitationsApi.peek(token),
    enabled: !!token,
    retry: false,
  });

  useEffect(() => {
    if (peek?.full_name) setFullName(peek.full_name);
  }, [peek?.full_name]);

  const roleLabel = (kind?: string) => {
    if (kind === "groupement_admin") return tRoles("groupement_admin");
    if (kind === "association_admin") return tRoles("association_admin");
    if (kind === "association_member") return tRoles("member");
    return "";
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (pwd !== pwd2) return setError(t("passwordMismatch"));
    if (pwd.length < 8) return setError(t("passwordTooShort"));
    setLoading(true);
    try {
      await invitationsApi.accept({ token, password: pwd, full_name: fullName.trim() || undefined });
      setDone(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      const e2 = err as { response?: { data?: { detail?: string } } };
      setError(e2.response?.data?.detail || t("tokenInvalid"));
    } finally {
      setLoading(false);
    }
  };

  const invalidToken = !token || peekError;

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-brand-50/40 to-background p-4 dark:via-brand-950/10">
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <BrandMark size="lg" />
        </div>
        <Card className="border-border/60 shadow-xl">
          <CardHeader className="text-center">
            <CardTitle>{done ? t("successTitle") : t("title")}</CardTitle>
            <CardDescription>{done ? t("successMessage") : t("subtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            {done ? (
              <div className="flex flex-col items-center py-4 text-center">
                <CheckCircle2 className="h-14 w-14 text-emerald-500" />
              </div>
            ) : peeking ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin" />
                <p className="text-sm">{t("checking")}</p>
              </div>
            ) : invalidToken ? (
              <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {t("tokenInvalid")}
              </div>
            ) : (
              <form onSubmit={submit} className="space-y-4">
                {/* Invitation context */}
                {peek && (
                  <div className="rounded-lg border border-brand-200 bg-brand-50/60 px-3 py-2.5 text-sm dark:border-brand-900/50 dark:bg-brand-950/30">
                    <p className="flex items-center gap-1.5 font-medium text-brand-800 dark:text-brand-200">
                      <Mail className="h-3.5 w-3.5 shrink-0" />
                      {peek.invited_by_name
                        ? t("invitedBy", { inviter: peek.invited_by_name })
                        : t("invitedTo")}{" "}
                      {peek.groupement_name && <strong>{peek.groupement_name}</strong>}
                    </p>
                    <p className="mt-0.5 text-xs text-brand-700/80 dark:text-brand-300/80">
                      {peek.email} · {t("asRole", { role: roleLabel(peek.kind) })}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {t("expiresOn", { date: fmt.date(peek.expires_at) })}
                    </p>
                  </div>
                )}

                {error && (
                  <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {error}
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="fullName">{t("fullName")}</Label>
                  <Input
                    id="fullName"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    disabled={loading}
                    placeholder="Jean Dupont"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="pwd">{t("newPassword")}</Label>
                  <div className="relative">
                    <Input
                      id="pwd"
                      type={show ? "text" : "password"}
                      required
                      disabled={loading}
                      value={pwd}
                      onChange={(e) => setPwd(e.target.value)}
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShow((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="pwd2">{t("confirmPassword")}</Label>
                  <Input
                    id="pwd2"
                    type={show ? "text" : "password"}
                    required
                    disabled={loading}
                    value={pwd2}
                    onChange={(e) => setPwd2(e.target.value)}
                  />
                </div>

                <Button type="submit" size="lg" className="w-full gap-2" disabled={loading}>
                  {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {loading ? t("activating") : t("activate")}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
