"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Pencil,
  Power,
  PowerOff,
  Loader2,
  Users,
  Calendar,
  MapPin,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { CurrencySelect } from "@/components/common/currency-select";
import { AssociationMembersTab } from "./association-members-tab";
import { AssociationSettings } from "./association-settings";
import { associationsApi, membersApi, meetingsApi } from "@/lib/api";
import type { Association, Meeting, Membership } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";
import { detectRole } from "@/lib/roles";

interface AssociationDetailProps {
  associationId: string;
  backHref?: string;
}

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export function AssociationDetail({ associationId, backHref }: AssociationDetailProps) {
  const t = useTranslations("association");
  const tCommon = useTranslations("common");
  const fmt = useFormatters();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const role = detectRole(user);
  // Super-admin and groupement/association admins may edit & suspend.
  const canManage = role === "super_admin" || role === "groupement_admin" || role === "association_admin";

  const detailKey = ["association", associationId];

  const { data: association, isLoading } = useQuery<Association>({
    queryKey: detailKey,
    queryFn: () => associationsApi.get(associationId),
  });

  const { data: memberships = [] } = useQuery<Membership[]>({
    queryKey: ["memberships", associationId],
    queryFn: () => membersApi.list(associationId),
  });

  const { data: meetings = [] } = useQuery<Meeting[]>({
    queryKey: ["meetings", associationId],
    queryFn: () => meetingsApi.list({ association_id: associationId }),
  });

  const statusMutation = useMutation({
    mutationFn: (isActive: boolean) => associationsApi.update(associationId, { is_active: isActive }),
    onSuccess: () => {
      toast.success(t("statusUpdated"));
      queryClient.invalidateQueries({ queryKey: detailKey });
      queryClient.invalidateQueries({ queryKey: ["associations"] });
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });

  if (isLoading || !association) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {backHref && (
        <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
          <Link href={backHref}>
            <ArrowLeft className="h-4 w-4" />
            {tCommon("back")}
          </Link>
        </Button>
      )}

      <PageHeader
        title={association.name}
        description={t("detailSubtitle")}
        actions={
          canManage && (
            <div className="flex items-center gap-2">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" className="gap-2">
                    {statusMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : association.is_active ? (
                      <PowerOff className="h-4 w-4 text-destructive" />
                    ) : (
                      <Power className="h-4 w-4 text-emerald-600" />
                    )}
                    {association.is_active ? t("suspend") : t("activate")}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      {association.is_active ? t("suspend") : t("activate")}
                    </AlertDialogTitle>
                    <AlertDialogDescription>{association.name}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                    <AlertDialogAction onClick={() => statusMutation.mutate(!association.is_active)}>
                      {association.is_active ? t("suspend") : t("activate")}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <EditAssociationDialog association={association} />
            </div>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        {association.is_active ? (
          <Badge variant="success">{tCommon("active")}</Badge>
        ) : (
          <Badge variant="destructive">{tCommon("inactive")}</Badge>
        )}
        <Badge variant="outline" className="font-mono">{association.slug}</Badge>
        <Badge variant="outline">{association.currency}</Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatRow icon={Users} label={t("membersCount", { count: memberships.length })} />
        <StatRow icon={Calendar} label={t("meetingsCount", { count: meetings.length })} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">{t("tabOverview")}</TabsTrigger>
          <TabsTrigger value="members">{t("tabMembers")}</TabsTrigger>
          <TabsTrigger value="meetings">{t("tabMeetings")}</TabsTrigger>
          <TabsTrigger value="settings">{t("tabSettings")}</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("generalInfo")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-0">
                <InfoRow label={t("fieldName")} value={association.name} />
                <InfoRow label={t("fieldSlug")} value={association.slug} mono />
                <InfoRow label={t("fieldDescription")} value={association.description} />
                <InfoRow label={t("fieldCreatedAt")} value={fmt.date(association.created_at)} last />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("localisation")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-0">
                <InfoRow label={t("fieldCurrency")} value={association.currency} />
                <InfoRow label={t("fieldTimezone")} value={association.timezone} />
                <InfoRow label={t("fieldAddress")} value={association.address} icon={MapPin} />
                <InfoRow
                  label={t("fieldCity")}
                  value={association.city}
                  last
                />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Members */}
        <TabsContent value="members" className="mt-4">
          <AssociationMembersTab associationId={associationId} canManage={canManage} />
        </TabsContent>

        {/* Meetings */}
        <TabsContent value="meetings" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle>{t("tabMeetings")}</CardTitle>
                <CardDescription>{t("meetingsCount", { count: meetings.length })}</CardDescription>
              </div>
              <Button asChild variant="ghost" size="sm">
                <Link href="/dashboard/meetings" className="gap-1">
                  {t("viewMeetings")} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {meetings.length === 0 ? (
                <EmptyState icon={Calendar} title={t("meetingsCount", { count: 0 })} />
              ) : (
                <div className="space-y-2">
                  {meetings.slice(0, 8).map((m) => (
                    <Link
                      key={m.id}
                      href={`/dashboard/meetings/${m.id}`}
                      className="flex items-center gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5 text-sm transition-colors hover:bg-accent/50"
                    >
                      <Calendar className="h-4 w-4 shrink-0 text-primary" />
                      <span className="min-w-0 flex-1 truncate font-medium">{m.title}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {fmt.date(m.scheduled_on)}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Settings — full configuration */}
        <TabsContent value="settings" className="mt-4">
          <AssociationSettings association={association} canManage={canManage} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Edit dialog ────────────────────────────────────────────────────────────

function EditAssociationDialog({ association }: { association: Association }) {
  const t = useTranslations("association");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: association.name,
    description: association.description ?? "",
    address: association.address ?? "",
    city: association.city ?? "",
    currency: association.currency,
    primary_color: association.primary_color,
  });
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const saveMutation = useMutation({
    mutationFn: () =>
      associationsApi.update(association.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        address: form.address.trim() || null,
        city: form.city.trim() || null,
        currency: form.currency.trim() || "XAF",
        primary_color: form.primary_color,
      }),
    onSuccess: () => {
      toast.success(t("saved"));
      queryClient.invalidateQueries({ queryKey: ["association", association.id] });
      queryClient.invalidateQueries({ queryKey: ["associations"] });
      setOpen(false);
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Pencil className="h-4 w-4" />
          {t("edit")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("editTitle")}</DialogTitle>
          <DialogDescription>{association.name}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.name.trim().length >= 2) saveMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="ea-name">{t("fieldName")}</Label>
            <Input id="ea-name" value={form.name} onChange={(e) => set("name", e.target.value)} required minLength={2} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ea-desc">{t("fieldDescription")}</Label>
            <Textarea id="ea-desc" rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ea-address">{t("fieldAddress")}</Label>
              <Input id="ea-address" value={form.address} onChange={(e) => set("address", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ea-city">{t("fieldCity")}</Label>
              <Input id="ea-city" value={form.city} onChange={(e) => set("city", e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ea-currency">{t("fieldCurrency")}</Label>
              <CurrencySelect
                id="ea-currency"
                value={form.currency}
                onValueChange={(v) => set("currency", v)}
                disabled={association.currency_locked}
              />
              {association.currency_locked && (
                <p className="text-xs text-muted-foreground">{t("currencyLockedHint")}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ea-color">{t("fieldColor")}</Label>
              <div className="flex items-center gap-2">
                <input
                  id="ea-color"
                  type="color"
                  value={form.primary_color}
                  onChange={(e) => set("primary_color", e.target.value)}
                  className="h-9 w-14 cursor-pointer rounded border border-input bg-background"
                />
                <Input value={form.primary_color} onChange={(e) => set("primary_color", e.target.value)} className="font-mono" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
              {saveMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Bits ───────────────────────────────────────────────────────────────────

function StatRow({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium">{label}</p>
    </div>
  );
}

function InfoRow({
  label,
  value,
  icon: Icon,
  mono,
  last,
}: {
  label: string;
  value?: string | null;
  icon?: React.ElementType;
  mono?: boolean;
  last?: boolean;
}) {
  const t = useTranslations("association");
  return (
    <div className={`flex items-start justify-between gap-4 py-2.5 ${last ? "" : "border-b border-border/50"}`}>
      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </span>
      <span
        className={`text-right text-sm font-medium ${mono ? "font-mono" : ""} ${
          !value ? "font-normal italic text-muted-foreground" : ""
        }`}
      >
        {value || t("notSet")}
      </span>
    </div>
  );
}
