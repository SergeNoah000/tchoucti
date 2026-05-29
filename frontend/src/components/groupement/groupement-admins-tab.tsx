"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crown,
  UserPlus,
  Mail,
  MoreHorizontal,
  RotateCw,
  XCircle,
  Trash2,
  ArrowLeftRight,
  Copy,
  Check,
  Loader2,
  Clock,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  DropdownMenuTrigger,
  DropdownMenuSeparator,
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
import { groupementsApi, invitationsApi } from "@/lib/api";
import type { GroupementAdmin, Invitation, InvitationCreated } from "@/lib/types";
import { useFormatters } from "@/lib/format";
import { initials } from "@/lib/utils";

interface AdminsTabProps {
  groupementId: string;
  /** Whether the current viewer may invite/remove admins & transfer ownership. */
  canManage: boolean;
}

export function GroupementAdminsTab({ groupementId, canManage }: AdminsTabProps) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");
  const fmt = useFormatters();
  const queryClient = useQueryClient();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<GroupementAdmin | null>(null);
  const [transferTarget, setTransferTarget] = useState<GroupementAdmin | null>(null);
  const [lastLink, setLastLink] = useState<string | null>(null);

  const adminsKey = ["groupement-admins", groupementId];
  const invitationsKey = ["groupement-invitations", groupementId];

  const { data: admins = [], isLoading: adminsLoading } = useQuery<GroupementAdmin[]>({
    queryKey: adminsKey,
    queryFn: () => groupementsApi.listAdmins(groupementId),
  });

  const { data: invitations = [] } = useQuery<Invitation[]>({
    queryKey: invitationsKey,
    queryFn: () => groupementsApi.listInvitations(groupementId, true),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: adminsKey });
    queryClient.invalidateQueries({ queryKey: invitationsKey });
  };

  const removeMutation = useMutation({
    mutationFn: (userId: string) => groupementsApi.removeAdmin(groupementId, userId),
    onSuccess: () => {
      toast.success(t("adminRemoved"));
      setRemoveTarget(null);
      refresh();
    },
    onError: (err: unknown) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  const transferMutation = useMutation({
    mutationFn: (userId: string) => groupementsApi.transferOwnership(groupementId, userId),
    onSuccess: () => {
      toast.success(t("transferDone"));
      setTransferTarget(null);
      refresh();
    },
    onError: (err: unknown) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  const resendMutation = useMutation({
    mutationFn: (invitationId: string) => invitationsApi.resend(invitationId),
    onSuccess: (data: InvitationCreated) => {
      toast.success(t("resent"));
      setLastLink(data.activation_url);
      refresh();
    },
    onError: (err: unknown) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  const revokeMutation = useMutation({
    mutationFn: (invitationId: string) => invitationsApi.revoke(invitationId),
    onSuccess: () => {
      toast.success(t("revoked"));
      refresh();
    },
    onError: (err: unknown) => toast.error(extractError(err) ?? tCommon("noData")),
  });

  return (
    <div className="space-y-6">
      {/* Admins list */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>{t("adminsTitle")}</CardTitle>
            <CardDescription>{t("adminsDesc")}</CardDescription>
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
                  {t("inviteAdmin")}
                </Button>
              </DialogTrigger>
              <InviteAdminDialog
                groupementId={groupementId}
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
          {adminsLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : admins.length === 0 ? (
            <EmptyState icon={Crown} title={t("noAdmins")} />
          ) : (
            <div className="space-y-2">
              {admins.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                      {initials(a.user_full_name)}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{a.user_full_name ?? "—"}</p>
                      <p className="truncate text-xs text-muted-foreground">{a.user_email}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {a.is_owner ? (
                      <Badge variant="warning" className="gap-1">
                        <Crown className="h-3 w-3" />
                        {t("owner")}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">{t("coAdmin")}</Badge>
                    )}
                    {canManage && !a.is_owner && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setTransferTarget(a)}>
                            <ArrowLeftRight className="mr-2 h-4 w-4" />
                            {t("transferOwnership")}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => setRemoveTarget(a)}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {t("removeAdmin")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pending invitations */}
      <Card>
        <CardHeader>
          <CardTitle>{t("pendingInvitations")}</CardTitle>
          <CardDescription>{t("inviteAdminDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          {invitations.length === 0 ? (
            <EmptyState icon={Mail} title={t("noPendingInvitations")} />
          ) : (
            <div className="space-y-2">
              {invitations.map((inv) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                      <Clock className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {inv.full_name || inv.email}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {inv.email} · {t("expiresOn", { date: fmt.date(inv.expires_at) })}
                        {inv.resent_count > 0 && ` · ${t("resentTimes", { count: inv.resent_count })}`}
                      </p>
                    </div>
                  </div>
                  {canManage && (
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1.5"
                        disabled={resendMutation.isPending}
                        onClick={() => resendMutation.mutate(inv.id)}
                      >
                        <RotateCw className="h-3.5 w-3.5" />
                        {t("resend")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1.5 text-destructive hover:text-destructive"
                        disabled={revokeMutation.isPending}
                        onClick={() => revokeMutation.mutate(inv.id)}
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        {t("revoke")}
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {lastLink && (
            <ActivationLinkBox link={lastLink} />
          )}
        </CardContent>
      </Card>

      {/* Remove admin confirm */}
      <AlertDialog open={!!removeTarget} onOpenChange={(v) => !v && setRemoveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("removeAdminConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("removeAdminConfirmDesc")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => removeTarget && removeMutation.mutate(removeTarget.user_id)}
              disabled={removeMutation.isPending}
            >
              {removeMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("removeAdmin")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Transfer ownership confirm */}
      <AlertDialog open={!!transferTarget} onOpenChange={(v) => !v && setTransferTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("transferConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("transferConfirmDesc", { name: transferTarget?.user_full_name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => transferTarget && transferMutation.mutate(transferTarget.user_id)}
              disabled={transferMutation.isPending}
            >
              {transferMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("transferOwnership")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ── Invite dialog ──────────────────────────────────────────────────────────

function InviteAdminDialog({
  groupementId,
  lastLink,
  onInvited,
}: {
  groupementId: string;
  lastLink: string | null;
  onInvited: (link: string) => void;
}) {
  const t = useTranslations("groupement");
  const tCommon = useTranslations("common");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [message, setMessage] = useState("");

  const inviteMutation = useMutation({
    mutationFn: () =>
      groupementsApi.inviteAdmin(groupementId, {
        email: email.trim(),
        full_name: fullName.trim() || undefined,
        message: message.trim() || undefined,
      }),
    onSuccess: (data: InvitationCreated) => {
      toast.success(t("inviteSent"));
      setEmail("");
      setFullName("");
      setMessage("");
      onInvited(data.activation_url);
    },
    onError: (err: unknown) => toast.error(extractError(err) ?? t("inviteError")),
  });

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{t("inviteAdminTitle")}</DialogTitle>
        <DialogDescription>{t("inviteAdminDesc")}</DialogDescription>
      </DialogHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (email.trim()) inviteMutation.mutate();
        }}
        className="min-w-0 space-y-4 py-2"
      >
        <div className="space-y-1.5">
          <Label htmlFor="inv-email">{t("inviteEmail")}</Label>
          <Input
            id="inv-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@exemple.cm"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="inv-name">{t("inviteName")}</Label>
          <Input
            id="inv-name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jean Dupont"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="inv-msg">{t("inviteMessage")}</Label>
          <Textarea
            id="inv-msg"
            rows={2}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </div>

        {lastLink && <ActivationLinkBox link={lastLink} />}

        <DialogFooter>
          <Button type="submit" disabled={inviteMutation.isPending || !email.trim()} className="gap-2">
            {inviteMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Mail className="h-4 w-4" />
            )}
            {t("inviteSend")}
          </Button>
        </DialogFooter>
      </form>
      <p className="sr-only">{tCommon("loading")}</p>
    </DialogContent>
  );
}

// ── Activation link box (copy fallback) ────────────────────────────────────

function ActivationLinkBox({ link }: { link: string }) {
  const t = useTranslations("groupement");
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      toast.success(t("linkCopied"));
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Clipboard");
    }
  };

  return (
    <div className="mt-3 min-w-0 rounded-lg border border-dashed border-border bg-muted/40 p-3">
      <p className="text-xs font-semibold">{t("inviteLinkTitle")}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{t("inviteLinkDesc")}</p>
      <div className="mt-2 flex min-w-0 items-center gap-2">
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

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}
