"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, AlertCircle, Eye, EyeOff, Sparkles, Copy, Check } from "lucide-react";

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
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [revealDemoPasswords, setRevealDemoPasswords] = useState(false);

  const demoAccounts = [
    { label: "Super Admin", email: "admin@tchoucti.cm", password: "admin123", accent: "from-violet-500 to-fuchsia-500" },
    { label: "Admin Groupement", email: "admin@demo.tchoucti.cm", password: "groupement123", accent: "from-sky-500 to-cyan-500" },
    { label: "Admin Association", email: "secretaire@demo.tchoucti.cm", password: "assoc123", accent: "from-emerald-500 to-teal-500" },
    { label: "Membre", email: "membre@demo.tchoucti.cm", password: "membre123", accent: "from-amber-500 to-orange-500" },
  ];

  const fillDemo = (i: number) => {
    const a = demoAccounts[i];
    setEmail(a.email);
    setPassword(a.password);
    setError("");
    setCopiedIdx(i);
    setTimeout(() => setCopiedIdx(null), 1500);
  };


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

        {/* Demo accounts panel */}
        <div className="mt-6 rounded-xl border border-border/60 bg-card/50 p-4 backdrop-blur-sm">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300">
              <Sparkles className="h-3.5 w-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-tight">{t("demoTitle")}</p>
              <p className="text-xs text-muted-foreground">{t("demoSubtitle")}</p>
            </div>
            <button
              type="button"
              onClick={() => setRevealDemoPasswords((v) => !v)}
              className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              aria-pressed={revealDemoPasswords}
            >
              {revealDemoPasswords ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              {revealDemoPasswords ? t("hidePasswords") : t("revealPasswords")}
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {demoAccounts.map((a, i) => (
              <button
                key={a.email}
                type="button"
                onClick={() => fillDemo(i)}
                disabled={isLoading}
                className="group relative flex flex-col items-start gap-1 overflow-hidden rounded-lg border border-border/60 bg-background/70 p-3 text-left transition-all hover:border-brand-300 hover:shadow-md disabled:opacity-50 dark:hover:border-brand-700"
              >
                <span className={`absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r ${a.accent}`} />
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-semibold">{a.label}</span>
                  {copiedIdx === i ? (
                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                </div>
                <div className="flex w-full flex-col gap-0.5 text-[11px] text-muted-foreground">
                  <span className="truncate font-mono">{a.email}</span>
                  <span className="font-mono">
                    {revealDemoPasswords ? a.password : t("passwordHidden")}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

