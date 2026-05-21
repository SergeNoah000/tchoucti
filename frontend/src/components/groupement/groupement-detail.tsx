"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  Pencil,
  Power,
  PowerOff,
  Loader2,
  FolderKanban,
  Globe,
  Mail,
  Phone,
  MapPin,
  CreditCard,
  ChevronRight,
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
import { GroupementAdminsTab } from "./groupement-admins-tab";
import { CreateAssociationDialog } from "@/components/association/create-association-dialog";
import { groupementsApi, associationsApi } from "@/lib/api";
import type { Association, Groupement, GroupementAdmin } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { useFormatters } from "@/lib/format";

interface GroupementDetailProps {
  groupementId: string;
  /** Back-link target. Omit to hide the back button (e.g. owner's own page). */
  backHref?: string;
}

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

export function GroupementDetail({ groupementId, backHref }: GroupementDetailProps) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");
  const fmt = useFormatters();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isSuperAdmin = !!user?.is_platform_admin;

  const groupementKey = ["groupement", groupementId];

  const { data: groupement, isLoading } = useQuery<Groupement>({
    queryKey: groupementKey,
    queryFn: () => groupementsApi.get(groupementId),
  });

  const { data: admins = [] } = useQuery<GroupementAdmin[]>({
    queryKey: ["groupement-admins", groupementId],
    queryFn: () => groupementsApi.listAdmins(groupementId),
  });

  const isOwner = admins.some((a) => a.user_id === user?.id && a.is_owner);
  const canEditInfo = isSuperAdmin || isOwner;
  const canManageTeam = isSuperAdmin || isOwner;
  const canSuspend = isSuperAdmin;

  const statusMutation = useMutation({
    mutationFn: (isActive: boolean) => groupementsApi.update(groupementId, { is_active: isActive }),
    onSuccess: () => {
      toast.success(t("statusUpdated"));
      queryClient.invalidateQueries({ queryKey: groupementKey });
      queryClient.invalidateQueries({ queryKey: ["groupements"] });
    },
    onError: (err) => toast.error(extractError(err) ?? t("saveError")),
  });

  if (isLoading || !groupement) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-72 w-full rounded-xl" />
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
        title={groupement.name}
        description={isSuperAdmin ? t("subtitleSuper") : t("subtitleOwner")}
        actions={
          <div className="flex items-center gap-2">
            {canSuspend && (
              <StatusToggle
                isActive={groupement.is_active}
                pending={statusMutation.isPending}
                onToggle={(next) => statusMutation.mutate(next)}
              />
            )}
            {canEditInfo && <EditGroupementDialog groupement={groupement} />}
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        {groupement.is_active ? (
          <Badge variant="success">{t("statusActive")}</Badge>
        ) : (
          <Badge variant="destructive">{t("statusSuspended")}</Badge>
        )}
        <Badge variant="outline" className="gap-1 font-mono">
          <Globe className="h-3 w-3" />
          {groupement.slug}.tchoucti.cm
        </Badge>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">{t("tabOverview")}</TabsTrigger>
          <TabsTrigger value="admins">{t("tabAdmins")}</TabsTrigger>
          <TabsTrigger value="associations">{t("tabAssociations")}</TabsTrigger>
          <TabsTrigger value="subscription">{t("tabSubscription")}</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("generalInfo")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-0">
                <InfoRow label={t("fieldName")} value={groupement.name} />
                <InfoRow label={t("fieldSlug")} value={groupement.slug} mono />
                <InfoRow label={t("fieldDescription")} value={groupement.description} />
                <InfoRow label={t("fieldCreatedAt")} value={fmt.date(groupement.created_at)} last />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("contactInfo")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-0">
                <InfoRow label={t("fieldEmail")} value={groupement.email} icon={Mail} />
                <InfoRow label={t("fieldPhone")} value={groupement.phone} icon={Phone} />
                <InfoRow label={t("fieldAddress")} value={groupement.address} icon={MapPin} />
                <InfoRow
                  label={t("fieldCity")}
                  value={[groupement.city, groupement.country].filter(Boolean).join(", ") || null}
                  last
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("branding")}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <span
                  className="h-10 w-10 shrink-0 rounded-lg border border-border"
                  style={{ backgroundColor: groupement.primary_color }}
                />
                <div>
                  <p className="text-sm font-medium">{t("fieldColor")}</p>
                  <p className="font-mono text-xs text-muted-foreground">{groupement.primary_color}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Admins */}
        <TabsContent value="admins" className="mt-4">
          <GroupementAdminsTab groupementId={groupementId} canManage={canManageTeam} />
        </TabsContent>

        {/* Associations */}
        <TabsContent value="associations" className="mt-4">
          <GroupementAssociationsTab
            groupementId={groupementId}
            canCreate={canManageTeam}
            detailHrefBase={isSuperAdmin ? "/admin/associations" : "/dashboard/associations"}
          />
        </TabsContent>

        {/* Subscription */}
        <TabsContent value="subscription" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("subscriptionTitle")}</CardTitle>
              <CardDescription>{t("subscriptionDesc")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-0">
              <InfoRow
                label={t("subStatus")}
                value={groupement.subscription_status}
                icon={CreditCard}
              />
              <InfoRow label={t("subMaxAssociations")} value={String(groupement.max_associations)} />
              <InfoRow label={t("subMaxUsers")} value={String(groupement.max_users)} />
              <InfoRow
                label={t("subTrialEnds")}
                value={groupement.trial_ends_at ? fmt.date(groupement.trial_ends_at) : null}
                last
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Status toggle ──────────────────────────────────────────────────────────

function StatusToggle({
  isActive,
  pending,
  onToggle,
}: {
  isActive: boolean;
  pending: boolean;
  onToggle: (next: boolean) => void;
}) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" className="gap-2">
          {pending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : isActive ? (
            <PowerOff className="h-4 w-4 text-destructive" />
          ) : (
            <Power className="h-4 w-4 text-emerald-600" />
          )}
          {isActive ? t("suspend") : t("activate")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isActive ? t("suspendConfirmTitle") : t("activateConfirmTitle")}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {isActive ? t("suspendConfirmDesc") : t("activateConfirmDesc")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className={isActive ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" : ""}
            onClick={() => onToggle(!isActive)}
          >
            {isActive ? t("suspend") : t("activate")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ── Edit dialog ────────────────────────────────────────────────────────────

function EditGroupementDialog({ groupement }: { groupement: Groupement }) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const [form, setForm] = useState({
    name: groupement.name,
    description: groupement.description ?? "",
    email: groupement.email ?? "",
    phone: groupement.phone ?? "",
    address: groupement.address ?? "",
    city: groupement.city ?? "",
    country: groupement.country ?? "",
    primary_color: groupement.primary_color,
  });

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const saveMutation = useMutation({
    mutationFn: () =>
      groupementsApi.update(groupement.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
        city: form.city.trim() || null,
        country: form.country.trim() || null,
        primary_color: form.primary_color,
      }),
    onSuccess: () => {
      toast.success(t("saved"));
      queryClient.invalidateQueries({ queryKey: ["groupement", groupement.id] });
      queryClient.invalidateQueries({ queryKey: ["groupements"] });
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
          <DialogDescription>{t("editSubtitle")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.name.trim().length >= 2) saveMutation.mutate();
          }}
          className="space-y-4 py-2"
        >
          <div className="space-y-1.5">
            <Label htmlFor="g-name">{t("fieldName")}</Label>
            <Input id="g-name" value={form.name} onChange={(e) => set("name", e.target.value)} required minLength={2} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="g-desc">{t("fieldDescription")}</Label>
            <Textarea id="g-desc" rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="g-email">{t("fieldEmail")}</Label>
              <Input id="g-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="g-phone">{t("fieldPhone")}</Label>
              <Input id="g-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="g-address">{t("fieldAddress")}</Label>
            <Input id="g-address" value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="g-city">{t("fieldCity")}</Label>
              <Input id="g-city" value={form.city} onChange={(e) => set("city", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="g-country">{t("fieldCountry")}</Label>
              <Input id="g-country" value={form.country} onChange={(e) => set("country", e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="g-color">{t("fieldColor")}</Label>
            <div className="flex items-center gap-2">
              <input
                id="g-color"
                type="color"
                value={form.primary_color}
                onChange={(e) => set("primary_color", e.target.value)}
                className="h-9 w-14 cursor-pointer rounded border border-input bg-background"
              />
              <Input
                value={form.primary_color}
                onChange={(e) => set("primary_color", e.target.value)}
                className="font-mono"
                pattern="^#[0-9A-Fa-f]{6}$"
              />
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

// ── Associations tab ───────────────────────────────────────────────────────

function GroupementAssociationsTab({
  groupementId,
  canCreate,
  detailHrefBase,
}: {
  groupementId: string;
  canCreate: boolean;
  detailHrefBase: string;
}) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");

  const { data: associations = [], isLoading } = useQuery<Association[]>({
    queryKey: ["groupement-associations", groupementId],
    queryFn: () => associationsApi.list(groupementId),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>{t("associationsTitle")}</CardTitle>
          <CardDescription>{t("associationsDesc")}</CardDescription>
        </div>
        {canCreate && <CreateAssociationDialog groupementId={groupementId} />}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : associations.length === 0 ? (
          <EmptyState icon={FolderKanban} title={t("noAssociations")} />
        ) : (
          <div className="space-y-2">
            {associations.map((a) => (
              <Link
                key={a.id}
                href={`${detailHrefBase}/${a.id}`}
                className="group flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5 transition-colors hover:bg-accent/50"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Building2 className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{a.name}</p>
                    {a.description && (
                      <p className="truncate text-xs text-muted-foreground">{a.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {a.is_active ? (
                    <Badge variant="success">{tCommon("active")}</Badge>
                  ) : (
                    <Badge variant="secondary">{tCommon("inactive")}</Badge>
                  )}
                  <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Info row ───────────────────────────────────────────────────────────────

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
  const t = useTranslations("groupement");
  return (
    <div
      className={`flex items-start justify-between gap-4 py-2.5 ${last ? "" : "border-b border-border/50"}`}
    >
      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </span>
      <span className={`text-right text-sm font-medium ${mono ? "font-mono" : ""} ${!value ? "text-muted-foreground italic font-normal" : ""}`}>
        {value || t("notSet")}
      </span>
    </div>
  );
}
