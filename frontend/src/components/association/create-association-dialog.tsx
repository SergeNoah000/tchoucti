"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { associationsApi } from "@/lib/api";
import type { Association, Groupement } from "@/lib/types";

function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // strip combining diacritics
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

function extractError(err: unknown): string | undefined {
  if (err && typeof err === "object" && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  }
  return undefined;
}

interface CreateAssociationDialogProps {
  /** When set, the association is created in this groupement (no picker). */
  groupementId?: string;
  /** When `groupementId` is omitted, the user picks from this list. */
  groupements?: Groupement[];
  /** Called after a successful create. */
  onCreated?: (association: Association) => void;
}

export function CreateAssociationDialog({
  groupementId,
  groupements,
  onCreated,
}: CreateAssociationDialogProps) {
  const t = useTranslations("association");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [pickedGroupement, setPickedGroupement] = useState(groupementId ?? "");
  const [error, setError] = useState("");

  const effectiveGroupement = groupementId ?? pickedGroupement;

  const reset = () => {
    setName("");
    setSlug("");
    setSlugTouched(false);
    setDescription("");
    setPickedGroupement(groupementId ?? "");
    setError("");
  };

  const createMutation = useMutation({
    mutationFn: () =>
      associationsApi.create({
        name: name.trim(),
        slug: slug.trim() || slugify(name),
        description: description.trim() || undefined,
        groupement_id: effectiveGroupement,
      }),
    onSuccess: (assoc: Association) => {
      toast.success(t("created2"));
      queryClient.invalidateQueries({ queryKey: ["associations"] });
      queryClient.invalidateQueries({ queryKey: ["groupement-associations"] });
      setOpen(false);
      reset();
      onCreated?.(assoc);
    },
    onError: (err) => setError(extractError(err) ?? t("createError")),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim().length < 2) {
      setError(t("nameRequired"));
      return;
    }
    if (!effectiveGroupement) {
      setError(t("fieldGroupement"));
      return;
    }
    setError("");
    createMutation.mutate();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          {t("create")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("createTitle")}</DialogTitle>
          <DialogDescription>{t("createDesc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          {!groupementId && groupements && (
            <div className="space-y-1.5">
              <Label htmlFor="ca-grp">{t("fieldGroupement")}</Label>
              <Select value={pickedGroupement} onValueChange={setPickedGroupement}>
                <SelectTrigger id="ca-grp">
                  <SelectValue placeholder={t("fieldGroupement")} />
                </SelectTrigger>
                <SelectContent>
                  {groupements.map((g) => (
                    <SelectItem key={g.id} value={g.id}>
                      {g.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="ca-name">{t("fieldName")}</Label>
            <Input
              id="ca-name"
              required
              minLength={2}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!slugTouched) setSlug(slugify(e.target.value));
              }}
              placeholder={t("namePlaceholder")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ca-slug">{t("fieldSlug")}</Label>
            <Input
              id="ca-slug"
              value={slug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(slugify(e.target.value));
              }}
              placeholder={t("slugPlaceholder")}
              pattern="^[a-z0-9-]+$"
            />
            <p className="text-xs text-muted-foreground">{t("slugHint")}</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ca-desc">{t("fieldDescription")}</Label>
            <Textarea
              id="ca-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" disabled={createMutation.isPending} className="gap-2">
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
