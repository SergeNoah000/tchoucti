"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  UserPlus,
  Loader2,
  Mail,
  MoreHorizontal,
  Power,
  PowerOff,
  Copy,
  Check,
  Clock,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { membersApi } from "@/lib/api";
import type { MemberCategory, Membership } from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { initials } from "@/lib/utils";

/** Roles assignable to a member, in display order. */
const ASSIGNABLE_ROLES = [
  "member",
  "association_admin",
  "association_manager",
  "treasurer",
  "censor",
] as const;

/** Member categories, in display order. */
const MEMBER_CATEGORIES: MemberCategory[] = ["active", "honorary", "founder", "suspended"];

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

interface AssociationMembersTabProps {
  associationId: string;
  canManage: boolean;
}

export function AssociationMembersTab({ associationId, canManage }: AssociationMembersTabProps) {
  const t = useTranslations("member");
  const tCommon = useTranslations("common");
  const tRoles = useTranslations("roles");
  const tCat = useTranslations("memberCategory");
  const fmt = useFormatters();
  const queryClient = useQueryClient();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [lastLink, setLastLink] = useState<string | null>(null);
  const [suspendTarget, setSuspendTarget] = useState<Membership | null>(null);

  const membersKey = ["memberships", associationId];

  const { data: members = [], isLoading } = useQuery<Membership[]>({
    queryKey: membersKey,
    queryFn: () => membersApi.list(associationId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: membersKey });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "active" | "suspended" }) =>
      membersApi.update(id, { status }),
    onSuccess: (_d, vars) => {
      toast.success(vars.status === "active" ? t("reactivated") : t("suspended"));
      setSuspendTarget(null);
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  const categoryMutation = useMutation({
    mutationFn: ({ id, category }: { id: string; category: MemberCategory }) =>
      membersApi.update(id, { category }),
    onSuccess: () => {
      toast.success(t("categoryUpdated"));
      refresh();
    },
    onError: (err) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>{t("title")}</CardTitle>
            <CardDescription>{t("subtitle")}</CardDescription>
          </div>
          {canManage && (
            <Dialog
              open={inviteOpen}
              onOpenChange={(v) => {
                setInviteOpen(v);
                if (!v) setLastLink(null);
              }}
            >
              <DialogTrigger asChild>
                <Button className="gap-2">
                  <UserPlus className="h-4 w-4" />
                  {t("invite")}
                </Button>
              </DialogTrigger>
              <InviteMemberDialog
                associationId={associationId}
                lastLink={lastLink}
                onInvited={(link) => {
                  setLastLink(link);
                  refresh();
                }}
              />
            </Dialog>
          )}
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : members.length === 0 ? (
            <EmptyState
              icon={UserPlus}
              title={t("empty")}
              description={canManage ? t("emptyDesc") : undefined}
            />
          ) : (
            <div className="space-y-2">
              {members.map((m) => {
                const pending = !m.user.is_active;
                return (
                  <div
                    key={m.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                        {initials(m.user.full_name)}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{m.user.full_name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {m.user.email} · {t("joinedOn", { date: fmt.date(m.joined_at) })}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {m.roles.slice(0, 2).map((r) => (
                        <Badge key={r.id} variant="outline" className="hidden sm:inline-flex text-[10px]">
                          {tRolesSafe(tRoles, r.code)}
                        </Badge>
                      ))}
                      {!pending && (
                        <Badge variant="brand" className="hidden sm:inline-flex text-[10px]">
                          {tCat(m.category)}
                        </Badge>
                      )}
                      {pending ? (
                        <Badge variant="warning" className="gap-1">
                          <Clock className="h-3 w-3" />
                          {t("pending")}
                        </Badge>
                      ) : m.status === "active" ? (
                        <Badge variant="success">{t("statusActive")}</Badge>
                      ) : m.status === "suspended" ? (
                        <Badge variant="destructive">{t("statusSuspended")}</Badge>
                      ) : (
                        <Badge variant="secondary">{t("statusResigned")}</Badge>
                      )}
                      {canManage && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {m.status === "active" ? (
                              <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                onClick={() => setSuspendTarget(m)}
                              >
                                <PowerOff className="mr-2 h-4 w-4" />
                                {t("suspend")}
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem
                                onClick={() => statusMutation.mutate({ id: m.id, status: "active" })}
                              >
                                <Power className="mr-2 h-4 w-4 text-emerald-600" />
                                {t("reactivate")}
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel className="text-xs text-muted-foreground">
                              {t("category")}
                            </DropdownMenuLabel>
                            {MEMBER_CATEGORIES.map((cat) => (
                              <DropdownMenuItem
                                key={cat}
                                disabled={m.category === cat}
                                onClick={() => categoryMutation.mutate({ id: m.id, category: cat })}
                              >
                                <Check
                                  className={`mr-2 h-4 w-4 ${m.category === cat ? "opacity-100" : "opacity-0"}`}
                                />
                                {tCat(cat)}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {lastLink && <ActivationLinkBox link={lastLink} />}
        </CardContent>
      </Card>

      <AlertDialog open={!!suspendTarget} onOpenChange={(v) => !v && setSuspendTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("suspendConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("suspendConfirmDesc", { name: suspendTarget?.user.full_name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                suspendTarget && statusMutation.mutate({ id: suspendTarget.id, status: "suspended" })
              }
              disabled={statusMutation.isPending}
            >
              {statusMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("suspend")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ── Invite dialog ──────────────────────────────────────────────────────────

function InviteMemberDialog({
  associationId,
  lastLink,
  onInvited,
}: {
  associationId: string;
  lastLink: string | null;
  onInvited: (link: string) => void;
}) {
  const t = useTranslations("member");
  const tRoles = useTranslations("roles");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<string>("member");

  const inviteMutation = useMutation({
    mutationFn: () =>
      membersApi.create({
        association_id: associationId,
        email: email.trim(),
        full_name: fullName.trim(),
        role_codes: [role],
      }),
    onSuccess: (membership: Membership) => {
      toast.success(t("sent"));
      setEmail("");
      setFullName("");
      setRole("member");
      onInvited(membership.activation_url ?? "");
    },
    onError: (err) => toast.error(extractError(err) ?? t("error")),
  });

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{t("inviteTitle")}</DialogTitle>
        <DialogDescription>{t("inviteDesc")}</DialogDescription>
      </DialogHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (email.trim() && fullName.trim()) inviteMutation.mutate();
        }}
        className="space-y-4 py-2"
      >
        <div className="space-y-1.5">
          <Label htmlFor="im-email">{t("email")}</Label>
          <Input
            id="im-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="membre@exemple.cm"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="im-name">{t("fullName")}</Label>
          <Input
            id="im-name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Marie Kamga"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="im-role">{t("role")}</Label>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger id="im-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASSIGNABLE_ROLES.map((code) => (
                <SelectItem key={code} value={code}>
                  {tRolesSafe(tRoles, code)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {lastLink && <ActivationLinkBox link={lastLink} />}

        <DialogFooter>
          <Button
            type="submit"
            disabled={inviteMutation.isPending || !email.trim() || !fullName.trim()}
            className="gap-2"
          >
            {inviteMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Mail className="h-4 w-4" />
            )}
            {t("send")}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

// ── Activation link box ────────────────────────────────────────────────────

function ActivationLinkBox({ link }: { link: string }) {
  const t = useTranslations("member");
  const [copied, setCopied] = useState(false);

  if (!link) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      toast.success(t("linkCopied"));
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-dashed border-border bg-muted/40 p-3">
      <p className="text-xs font-semibold">{t("activationLink")}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{t("activationLinkDesc")}</p>
      <div className="mt-2 flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-background px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
          {link}
        </code>
        <Button type="button" variant="outline" size="sm" className="shrink-0 gap-1.5" onClick={copy}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          {t("copyLink")}
        </Button>
      </div>
    </div>
  );
}

/** Translate a role code, falling back to the raw code for unknown ones. */
function tRolesSafe(tRoles: (k: string) => string, code: string): string {
  try {
    return tRoles(code);
  } catch {
    return code;
  }
}
