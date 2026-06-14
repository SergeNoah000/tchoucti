"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, Mail, Copy, Check, Send, Loader2, ShieldCheck, UserCircle2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { membersApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";
import { useFormatters } from "@/lib/format";
import type { Membership } from "@/lib/types";

function extractError(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}

export default function MemberDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("memberDetail");
  const { user } = useAuthStore();
  const isBureau = canDoBureauActions(user);
  const fmt = useFormatters();

  const [activationUrl, setActivationUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: m, isLoading } = useQuery<Membership>({
    queryKey: ["membership", id],
    queryFn: () => membersApi.get(id),
    enabled: !!id,
  });

  const resend = useMutation({
    mutationFn: () => membersApi.resendInvitation(id),
    onSuccess: (res) => {
      setActivationUrl(res.activation_url);
      toast.success(res.sent ? t("resentSent") : t("resentLinkOnly"));
    },
    onError: (err) => toast.error(extractError(err) ?? t("resendError")),
  });

  const copy = async () => {
    if (!activationUrl) return;
    try {
      await navigator.clipboard.writeText(activationUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("copyError"));
    }
  };

  if (isLoading || !m) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </div>
    );
  }

  const isActive = m.user.is_active;
  const isPlaceholderEmail = m.user.email.endsWith(".import.local");
  const canInvite = isBureau && !isActive && !isPlaceholderEmail;

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
        <Link href="/dashboard/members">
          <ArrowLeft className="h-4 w-4" />
          {t("back")}
        </Link>
      </Button>

      <PageHeader
        title={m.user.full_name}
        description={m.member_number ? `${t("memberNumber")} : ${m.member_number}` : undefined}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={isActive ? "success" : "warning"}>
          {isActive ? t("active") : t("pending")}
        </Badge>
        <Badge variant="outline">{t(`status_${m.status}`)}</Badge>
        <Badge variant="outline">{t(`category_${m.category}`)}</Badge>
        {m.roles.map((r) => (
          <Badge key={r.id} variant="secondary" className="gap-1">
            <ShieldCheck className="h-3 w-3" />
            {r.name}
          </Badge>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Infos */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserCircle2 className="h-4 w-4" /> {t("info")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t("email")} value={isPlaceholderEmail ? t("noEmail") : m.user.email} />
            {m.user.phone && <Row label={t("phone")} value={m.user.phone} />}
            <Row label={t("joinedAt")} value={fmt.date(m.joined_at)} />
            <Row label={t("cumulative")} value={fmt.currency(m.cumulative_contributions)} />
            {m.notes && <Row label={t("notes")} value={m.notes} />}
          </CardContent>
        </Card>

        {/* Accès / invitation */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Mail className="h-4 w-4" /> {t("access")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {isActive ? (
              <p className="text-muted-foreground">{t("accessActive")}</p>
            ) : isPlaceholderEmail ? (
              <p className="text-muted-foreground">{t("accessNoEmail")}</p>
            ) : (
              <p className="text-muted-foreground">{t("accessPending")}</p>
            )}

            {canInvite && (
              <div className="space-y-3">
                <Button onClick={() => resend.mutate()} disabled={resend.isPending} className="gap-2">
                  {resend.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  {t("resend")}
                </Button>

                {activationUrl && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">{t("activationLink")}</p>
                    <div className="flex items-center gap-2">
                      <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-muted/40 px-2.5 py-1.5 text-xs">
                        {activationUrl}
                      </code>
                      <Button type="button" size="icon" variant="outline" onClick={copy} title={t("copy")}>
                        {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}
