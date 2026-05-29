"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { LanguageToggle } from "@/components/common/language-toggle";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import type { AssociationBranding, User } from "@/lib/types";

export function BrandedLogin({ branding }: { branding: AssociationBranding }) {
  const router = useRouter();
  const t = useTranslations("login");
  const { login } = useAuthStore();
  const { association } = branding;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const tokens = await authApi.login(email, password);
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      const user: User = await authApi.getMe();
      login(user, tokens.access_token, tokens.refresh_token);
      router.push(user.is_platform_admin ? "/admin" : "/dashboard");
    } catch (err) {
      const e2 = err as { response?: { data?: { detail?: string } } };
      setError(e2.response?.data?.detail || t("invalidCredentials"));
    } finally {
      setIsLoading(false);
    }
  };

  const accent = association.primary_color;

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-background p-4">
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div
            className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl border border-border bg-card shadow-sm"
            style={{ borderColor: `${accent}40` }}
          >
            {association.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={association.logo_url} alt={association.name} className="h-full w-full object-cover" />
            ) : (
              <span className="text-2xl font-bold" style={{ color: accent }}>
                {association.name.charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          <div>
            <h1 className="text-xl font-bold leading-tight">{association.name}</h1>
            <p className="text-sm text-muted-foreground">{branding.groupement.name}</p>
          </div>
        </div>

        <Card className="border-border/60 shadow-xl">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">{t("title")}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">{t("email")}</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  disabled={isLoading}
                  placeholder="vous@exemple.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">{t("password")}</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    disabled={isLoading}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                size="lg"
                className="w-full text-white"
                style={{ backgroundColor: accent }}
                disabled={isLoading}
              >
                {isLoading ? t("loggingIn") : t("submit")}
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-muted-foreground">
              {t("noAccount")} <span className="text-foreground/80">{t("contactAdmin")}</span>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
