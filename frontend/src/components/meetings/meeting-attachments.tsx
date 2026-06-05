"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Paperclip, Loader2, FileText, Image as ImageIcon, Download } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { setupApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";

interface DocumentRow {
  id: string;
  title: string;
  file_url: string;
  file_name: string;
  file_mime: string;
  file_size: number;
  meeting_id?: string | null;
  membership_id?: string | null;
  created_at: string;
}

const MAX_BYTES = 20 * 1024 * 1024; // 20 MB (aligné backend)

/**
 * Liste + uploader de pièces jointes pour une séance (au niveau séance ou
 * par membre). Les fichiers vont dans Documents (kind = "seance" / "membre").
 * `canUpload` gate la possibilité d'ajouter ; tout le monde voit la liste.
 */
export function MeetingAttachments({
  associationId,
  meetingId,
  membershipId,
  canUpload,
  compact,
}: {
  associationId: string;
  meetingId: string;
  membershipId?: string;
  canUpload: boolean;
  compact?: boolean;
}) {
  const t = useTranslations("meeting");
  const fmt = useFormatters();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const queryKey = ["documents", associationId, meetingId, membershipId ?? "general"];
  const { data: docs = [] } = useQuery<DocumentRow[]>({
    queryKey,
    queryFn: () =>
      setupApi.listDocuments(associationId, {
        meeting_id: meetingId,
        membership_id: membershipId,
      }),
  });

  const uploadMut = useMutation({
    mutationFn: async (file: File) => {
      const kind = membershipId ? "membre" : "seance";
      const title = file.name;
      return setupApi.uploadDocument(associationId, file, title, kind, {
        meeting_id: meetingId,
        membership_id: membershipId,
      });
    },
    onSuccess: () => {
      toast.success(t("attachUploaded"));
      queryClient.invalidateQueries({ queryKey });
    },
    onError: () => toast.error(t("attachError")),
  });

  const onPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    e.target.value = "";
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        if (f.size > MAX_BYTES) {
          toast.error(t("attachTooLarge", { name: f.name }));
          continue;
        }
        await uploadMut.mutateAsync(f);
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-2">
      {!compact && (
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Paperclip className="h-3.5 w-3.5" />
          {membershipId ? t("attachMemberTitle") : t("attachMeetingTitle")}
        </p>
      )}
      {docs.length === 0 && !canUpload ? (
        <p className="text-xs text-muted-foreground">{t("attachEmpty")}</p>
      ) : (
        <ul className="space-y-1">
          {docs.map((d) => {
            const isImage = (d.file_mime ?? "").startsWith("image/");
            return (
              <li
                key={d.id}
                className="flex items-center justify-between gap-2 rounded-md border border-border/40 bg-muted/30 px-2.5 py-1.5 text-sm"
              >
                <div className="flex min-w-0 items-center gap-2">
                  {isImage ? <ImageIcon className="h-4 w-4 shrink-0 text-muted-foreground" /> : <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />}
                  <a
                    href={d.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate font-medium hover:underline"
                  >
                    {d.title}
                  </a>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                  <span className="tabular-nums">{Math.round(d.file_size / 1024)} kB</span>
                  <span>·</span>
                  <span>{fmt.date(d.created_at)}</span>
                  <a
                    href={d.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-1 inline-flex items-center text-muted-foreground hover:text-foreground"
                    title={t("attachDownload")}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {canUpload && (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
            {t("attachAdd")}
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={onPick}
            accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv"
          />
        </div>
      )}
    </div>
  );
}
