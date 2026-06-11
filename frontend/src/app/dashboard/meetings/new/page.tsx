"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Calendar, MapPin, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { meetingsApi, associationsApi } from "@/lib/api";
import type { Association, Meeting } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canDoBureauActions } from "@/lib/roles";

export default function NewMeetingPage() {
  const router = useRouter();
  const t = useTranslations("meeting");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isBureau = canDoBureauActions(user);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });

  const [associationId, setAssociationId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scheduledOn, setScheduledOn] = useState(() => new Date().toISOString().split("T")[0]);
  const [location, setLocation] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!associationId && associations.length > 0) {
      setAssociationId(associations[0].id);
    }
  }, [associations, associationId]);

  const createMutation = useMutation<Meeting, unknown, Record<string, unknown>>({
    mutationFn: (payload) => meetingsApi.create(payload),
    onSuccess: (meeting) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      router.push(`/dashboard/meetings/${meeting.id}`);
    },
    onError: (err) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? t("createError"));
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !associationId || !scheduledOn) {
      setError(t("requiredFields"));
      return;
    }
    setError("");
    createMutation.mutate({
      association_id: associationId,
      title: title.trim(),
      description: description.trim() || undefined,
      scheduled_on: scheduledOn,
      location: location.trim() || undefined,
    });
  }

  if (!isBureau) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("bureauOnly")}</p>
        <Button asChild variant="ghost" className="mt-4 gap-1.5">
          <Link href="/dashboard/meetings">
            <ArrowLeft className="h-4 w-4" />
            {t("backToList")}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
          <Link href="/dashboard/meetings">
            <ArrowLeft className="h-4 w-4" />
            {t("title")}
          </Link>
        </Button>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">{t("newMeetingTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("newMeetingSubtitle")}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-primary" />
              {t("sectionGeneral")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {associations.length > 1 && (
              <div className="space-y-1.5">
                <Label htmlFor="association">{t("association")}</Label>
                <Select value={associationId} onValueChange={setAssociationId}>
                  <SelectTrigger id="association">
                    <SelectValue placeholder={t("association")} />
                  </SelectTrigger>
                  <SelectContent>
                    {associations.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        {a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="title">
                {t("meetingTitle")} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("meetingTitlePlaceholder")}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">{t("descriptionLabel")}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("descriptionPlaceholder")}
                rows={3}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Calendar className="h-4 w-4 text-primary" />
              {t("sectionDateLocation")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="date">
                {t("meetingDate")} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="date"
                type="date"
                min={new Date().toISOString().split("T")[0]}
                value={scheduledOn}
                onChange={(e) => setScheduledOn(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="location">{t("location")}</Label>
              <div className="relative">
                <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="location"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder={t("locationPlaceholder")}
                  className="pl-9"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          <Button asChild variant="ghost">
            <Link href="/dashboard/meetings">{tCommon("cancel")}</Link>
          </Button>
          <Button type="submit" disabled={createMutation.isPending} className="gap-2">
            {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {t("create")}
          </Button>
        </div>
      </form>
    </div>
  );
}
