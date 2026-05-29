"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { associationsApi, setupApi } from "@/lib/api";
import type { Association } from "@/lib/types";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";

interface Doc {
  id: string;
  title: string;
  kind: string;
  file_url: string;
  file_name: string;
  file_size: number;
}

const KINDS = ["statuts", "roi", "recepisse", "autre"] as const;

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canManage = canConfigureAssociation(user);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const associationId = associations[0]?.id;

  const { data: docs = [], isLoading } = useQuery<Doc[]>({
    queryKey: ["documents", associationId],
    queryFn: () => setupApi.listDocuments(associationId!),
    enabled: !!associationId,
  });

  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<string>("statuts");
  const [file, setFile] = useState<File | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["documents", associationId] });

  const upload = useMutation({
    mutationFn: () => setupApi.uploadDocument(associationId!, file!, title.trim(), kind),
    onSuccess: () => {
      toast.success(t("uploaded"));
      setTitle("");
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      refresh();
    },
    onError: () => toast.error(tCommon("error")),
  });

  const remove = useMutation({
    mutationFn: (id: string) => setupApi.deleteDocument(associationId!, id),
    onSuccess: () => {
      toast.success(t("deleted"));
      refresh();
    },
    onError: () => toast.error(tCommon("error")),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || title.trim().length < 2) {
      toast.error(t("missingFields"));
      return;
    }
    upload.mutate();
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : docs.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={FileText}
              title={t("empty")}
              description={canManage ? t("emptyDesc") : undefined}
            />
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {docs.map((d) => (
            <li
              key={d.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3"
            >
              <a
                href={d.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-w-0 items-center gap-3 hover:underline"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{d.title}</span>
                    <Badge variant="outline" className="text-[10px]">{t(`kind_${d.kind}`)}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {d.file_name} · {Math.max(1, Math.round(d.file_size / 1024))} KB
                  </span>
                </div>
              </a>
              {canManage && (
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => remove.mutate(d.id)}
                  disabled={remove.isPending}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canManage && associationId && (
        <Card>
          <CardContent className="p-4">
            <form
              onSubmit={submit}
              className="grid grid-cols-1 gap-3 sm:grid-cols-[180px_1fr_auto] sm:items-end"
            >
              <div className="space-y-1.5">
                <Label>{t("kind")}</Label>
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KINDS.map((k) => (
                      <SelectItem key={k} value={k}>{t(`kind_${k}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="doc-title">{t("docTitle")}</Label>
                <Input
                  id="doc-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t("docTitlePlaceholder")}
                />
                <input
                  ref={inputRef}
                  type="file"
                  className="mt-1 block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/10 file:px-3 file:py-1.5 file:text-primary"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </div>
              <Button type="submit" disabled={upload.isPending} className="gap-2">
                {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {t("add")}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
