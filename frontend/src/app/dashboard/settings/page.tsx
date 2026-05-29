"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Save, KeyRound, LogOut, User as UserIcon, Palette } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import { LanguageToggle } from "@/components/common/language-toggle";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { authApi } from "@/lib/api";
import { useAuthStore, usePermissionStore } from "@/lib/store";
import type { User } from "@/lib/types";

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export default function SettingsPage() {
  const t = useTranslations("settings");
  const tCommon = useTranslations("common");
  const { user, setUser, logout } = useAuthStore();
  const { clear } = usePermissionStore();

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");

  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");

  const saveProfile = useMutation({
    mutationFn: () => authApi.updateMe({ full_name: fullName.trim(), phone: phone.trim() }),
    onSuccess: (updated: User) => {
      setUser(updated);
      toast.success(t("accountUpdated"));
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });

  const changePwd = useMutation({
    mutationFn: () =>
      authApi.changePassword({ current_password: currentPwd, new_password: newPwd }),
    onSuccess: () => {
      toast.success(t("passwordChanged"));
      setCurrentPwd("");
      setNewPwd("");
      setConfirmPwd("");
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });

  const submitPassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (newPwd.length < 8) return toast.error(t("passwordTooShort"));
    if (newPwd !== confirmPwd) return toast.error(t("passwordMismatch"));
    changePwd.mutate();
  };

  const onLogout = () => {
    logout();
    clear();
    window.location.replace("/login");
  };

  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Compte */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <UserIcon className="h-4 w-4" /> {t("account")}
          </CardTitle>
          <CardDescription>{t("accountDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="st-name">{t("fullName")}</Label>
              <Input id="st-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="st-phone">{t("phone")}</Label>
              <Input id="st-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="st-email">{t("email")}</Label>
            <Input id="st-email" value={user?.email ?? ""} disabled />
          </div>
          <div className="flex justify-end">
            <Button
              onClick={() => saveProfile.mutate()}
              disabled={saveProfile.isPending || fullName.trim().length < 1}
              className="gap-2"
            >
              {saveProfile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {tCommon("save")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Sécurité */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <KeyRound className="h-4 w-4" /> {t("security")}
          </CardTitle>
          <CardDescription>{t("securityDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submitPassword} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="st-cur">{t("currentPassword")}</Label>
              <Input
                id="st-cur"
                type="password"
                value={currentPwd}
                onChange={(e) => setCurrentPwd(e.target.value)}
                required
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="st-new">{t("newPassword")}</Label>
                <Input
                  id="st-new"
                  type="password"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="st-confirm">{t("confirmPassword")}</Label>
                <Input
                  id="st-confirm"
                  type="password"
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  required
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={changePwd.isPending || !currentPwd || !newPwd} className="gap-2">
                {changePwd.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                {t("changePassword")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Préférences */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Palette className="h-4 w-4" /> {t("preferences")}
          </CardTitle>
          <CardDescription>{t("preferencesDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-6">
          <div className="space-y-1.5">
            <Label>{t("language")}</Label>
            <LanguageToggle />
          </div>
          <div className="space-y-1.5">
            <Label>{t("theme")}</Label>
            <ThemeToggle />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button variant="outline" onClick={onLogout} className="gap-2 text-destructive">
          <LogOut className="h-4 w-4" />
          {tCommon("logout")}
        </Button>
      </div>
    </div>
  );
}
