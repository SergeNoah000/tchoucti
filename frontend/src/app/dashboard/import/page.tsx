"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Download, Upload, Loader2, CheckCircle2, AlertTriangle, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import {
  associationsApi,
  importsApi,
  type ImportEntity,
  type ImportPreview,
} from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { canConfigureAssociation } from "@/lib/roles";
import { cn } from "@/lib/utils";
import type { Association } from "@/lib/types";

export default function ImportPage() {
  const t = useTranslations("imports");
  const { user } = useAuthStore();
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: associations = [] } = useQuery<Association[]>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
  });
  const association = associations[0];

  const { data: entities = [] } = useQuery<ImportEntity[]>({
    queryKey: ["import-entities"],
    queryFn: () => importsApi.entities(),
  });

  const [entity, setEntity] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState<"download" | "preview" | "commit" | null>(null);

  useEffect(() => {
    if (!entity && entities.length > 0) setEntity(entities[0].entity);
  }, [entities, entity]);

  const selected = entities.find((e) => e.entity === entity);

  const reset = () => {
    setFile(null);
    setPreview(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  if (!canConfigureAssociation(user)) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-muted-foreground">{t("notAdmin")}</p>
      </div>
    );
  }
  if (!association) {
    return (
      <div className="space-y-4 py-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  const onDownload = async () => {
    if (!entity) return;
    setBusy("download");
    try {
      await importsApi.downloadTemplate(entity, association.id);
    } catch {
      toast.error(t("downloadError"));
    } finally {
      setBusy(null);
    }
  };

  const onPick = async (f: File | null) => {
    setFile(f);
    setPreview(null);
    if (!f || !entity) return;
    setBusy("preview");
    try {
      const res = await importsApi.preview(entity, association.id, f);
      setPreview(res);
    } catch (err) {
      toast.error(extractErr(err) ?? t("previewError"));
    } finally {
      setBusy(null);
    }
  };

  const onCommit = async () => {
    if (!file || !entity) return;
    setBusy("commit");
    try {
      const res = await importsApi.commit(entity, association.id, file);
      if (res.created > 0) toast.success(t("commitDone", { created: res.created }));
      if (res.failed > 0) toast.warning(t("commitPartial", { failed: res.failed }));
      if (res.created === 0 && res.failed === 0) toast.info(t("commitEmpty"));
      reset();
    } catch (err) {
      toast.error(extractErr(err) ?? t("commitError"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Étape 1 — choix de l'entité + téléchargement du template */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">1</span>
            {t("step1Title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("entityLabel")}</label>
              <Select value={entity} onValueChange={(v) => { setEntity(v); reset(); }}>
                <SelectTrigger>
                  <SelectValue placeholder={t("entityPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {entities.map((e) => (
                    <SelectItem key={e.entity} value={e.entity}>{e.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={onDownload} disabled={!entity || busy !== null} variant="outline" className="gap-2">
              {busy === "download" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {t("downloadTemplate")}
            </Button>
          </div>
          {selected && <p className="text-sm text-muted-foreground">{selected.description}</p>}
        </CardContent>
      </Card>

      {/* Étape 2 — upload + aperçu */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">2</span>
            {t("step2Title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={!entity || busy !== null}
            className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-muted/20 px-4 py-8 text-center transition hover:bg-muted/40 disabled:opacity-50"
          >
            {busy === "preview" ? (
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            ) : (
              <FileSpreadsheet className="h-8 w-8 text-muted-foreground" />
            )}
            <span className="text-sm font-medium">{file ? file.name : t("dropHint")}</span>
            <span className="text-xs text-muted-foreground">{t("dropSub")}</span>
          </button>

          {preview && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="secondary">{t("rowsTotal", { n: preview.total })}</Badge>
                <Badge variant="success" className="gap-1">
                  <CheckCircle2 className="h-3 w-3" /> {t("rowsValid", { n: preview.valid })}
                </Badge>
                {preview.invalid > 0 && (
                  <Badge variant="destructive" className="gap-1">
                    <AlertTriangle className="h-3 w-3" /> {t("rowsInvalid", { n: preview.invalid })}
                  </Badge>
                )}
              </div>

              {preview.total === 0 ? (
                <EmptyState icon={AlertTriangle} title={t("noRows")} />
              ) : (
                <div className="max-h-[420px] overflow-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 font-medium">#</th>
                        <th className="px-3 py-2 font-medium">{t("statusCol")}</th>
                        {preview.columns.map((c) => (
                          <th key={c.key} className="px-3 py-2 font-medium whitespace-nowrap">{c.header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {preview.rows.map((r) => (
                        <tr key={r.index} className={cn(!r.ok && "bg-destructive/5")}>
                          <td className="px-3 py-2 text-muted-foreground">{r.index}</td>
                          <td className="px-3 py-2">
                            {r.ok ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            ) : (
                              <span title={r.errors.join(" ")} className="flex items-center gap-1 text-destructive">
                                <AlertTriangle className="h-4 w-4 shrink-0" />
                                <span className="text-xs">{r.errors.join(" ")}</span>
                              </span>
                            )}
                          </td>
                          {preview.columns.map((c) => (
                            <td key={c.key} className="px-3 py-2 whitespace-nowrap">
                              {String(r.values[c.key] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex items-center justify-between gap-3 pt-1">
                <p className="text-xs text-muted-foreground">{t("commitHint")}</p>
                <Button onClick={onCommit} disabled={preview.valid === 0 || busy !== null} className="gap-2">
                  {busy === "commit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                  {t("commitButton", { n: preview.valid })}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function extractErr(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}
