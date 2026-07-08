"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, AlertCircle, Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BrandMark } from "@/components/common/brand-mark";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { LanguageToggle } from "@/components/common/language-toggle";
import { authApi } from "@/lib/api";
import { useAuthStore, usePermissionStore } from "@/lib/store";
import type { User } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations("login");
  const { login, logout } = useAuthStore();
  const { clear } = usePermissionStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [isLoading, setIsLoading] = useState(false);


  useEffect(() => {
    if (searchParams.get("expired") === "true") {
      setExpired(true);
      logout();
      clear();
      window.history.replaceState({}, "", "/login");
    }
  }, [searchParams, logout, clear]);

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

      if (user.is_platform_admin) {
        // The middleware will resolve admin.{root} for prod, but on localhost
        // we navigate to /admin directly.
        router.push("/admin");
      } else {
        router.push("/dashboard");
      }
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      // No `response` → the request never reached the API (network / CORS /
      // wrong host). Don't mislead the user with "invalid credentials".
      if (!e.response) setError(t("connectionError"));
      else setError(e.response.data?.detail || t("invalidCredentials"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-brand-50/40 to-background p-4 dark:via-brand-950/10">
      {/* Top-right controls */}
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="absolute left-4 top-4">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
          {t("backToLanding")}
        </Link>
      </div>

      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <BrandMark size="lg" />
        </div>

        <Card className="shadow-xl border-border/60">
          <CardHeader className="space-y-1 text-center">
            <CardTitle className="text-2xl">{t("title")}</CardTitle>
            <CardDescription>{t("subtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {expired && (
                <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {t("sessionExpired")}
                </div>
              )}
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

              <Button type="submit" variant="brand" size="lg" className="w-full" disabled={isLoading}>
                {isLoading ? t("loggingIn") : t("submit")}
              </Button>
            </form>

            <div className="mt-6 text-center text-sm text-muted-foreground">
              <p>{t("noAccount")} <span className="text-foreground/80">{t("contactAdmin")}</span></p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

