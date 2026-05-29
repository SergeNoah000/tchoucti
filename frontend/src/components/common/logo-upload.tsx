"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { setupApi } from "@/lib/api";

const MAX_BYTES = 5 * 1024 * 1024;

export function LogoUpload({
  associationId,
  currentLogoUrl,
  onUploaded,
  disabled,
}: {
  associationId: string;
  currentLogoUrl?: string | null;
  onUploaded?: (url: string) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("common");
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(currentLogoUrl ?? null);

  const upload = useMutation({
    mutationFn: (file: File) => setupApi.uploadLogo(associationId, file),
    onSuccess: (res) => {
      setPreview(res.logo_url);
      toast.success(t("logoUploaded"));
      queryClient.invalidateQueries({ queryKey: ["associations"] });
      queryClient.invalidateQueries({ queryKey: ["association", associationId] });
      onUploaded?.(res.logo_url);
    },
    onError: () => toast.error(t("logoError")),
  });

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) return toast.error(t("logoInvalid"));
    if (file.size > MAX_BYTES) return toast.error(t("logoTooLarge"));
    upload.mutate(file);
  };

  return (
    <div className="flex items-center gap-4">
      <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/30">
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" className="h-full w-full object-cover" />
        ) : (
          <ImagePlus className="h-6 w-6 text-muted-foreground" />
        )}
      </div>
      <div className="space-y-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-2"
          disabled={disabled || upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
          {preview ? t("logoChange") : t("logoUpload")}
        </Button>
        <p className="text-xs text-muted-foreground">{t("logoHint")}</p>
      </div>
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={onPick} />
    </div>
  );
}
