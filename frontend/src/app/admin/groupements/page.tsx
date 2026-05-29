"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Building2, Plus, MoreHorizontal, Eye, Power, PowerOff } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/common/empty-state";
import { groupementsApi } from "@/lib/api";
import type { Groupement } from "@/lib/types";
import { groupementHost } from "@/lib/utils";

const createSchema = z.object({
  name: z.string().min(2, "Nom trop court"),
  slug: z.string().min(2, "Slug trop court").regex(/^[a-z0-9-]+$/, "Format invalide (a-z, 0-9, -)"),
  description: z.string().optional(),
  admin_name: z.string().min(2, "Nom trop court"),
  admin_email: z.string().email("Email invalide"),
  admin_password: z.string().min(8, "Mot de passe de 8 caractères min."),
});
type CreateFormValues = z.infer<typeof createSchema>;

interface UpdatePayload {
  is_active?: boolean;
  name?: string;
  description?: string;
}

export default function GroupementsPage() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: groupements = [], isLoading } = useQuery<Groupement[]>({
    queryKey: ["groupements"],
    queryFn: groupementsApi.list,
  });

  const createMutation = useMutation({
    mutationFn: groupementsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["groupements"] });
      toast.success("Groupement créé avec succès");
      setOpen(false);
      reset();
    },
    onError: (err: unknown) => {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(msg || "Erreur de création");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdatePayload }) =>
      groupementsApi.update(id, data as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["groupements"] });
      toast.success("Groupement mis à jour");
    },
    onError: () => toast.error("Erreur de mise à jour"),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateFormValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      name: "",
      slug: "",
      description: "",
      admin_name: "",
      admin_email: "",
      admin_password: "",
    },
  });

  const toggleStatus = (id: string, currentStatus: boolean) =>
    updateMutation.mutate({ id, data: { is_active: !currentStatus } });

  const onSubmit = (values: CreateFormValues) => createMutation.mutate(values);

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("groupements")}
        description="Liste de tous les groupements hébergés sur la plateforme."
        actions={
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
                Nouveau groupement
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Nouveau Groupement</DialogTitle>
                <DialogDescription>
                  Créez un nouveau groupement (locataire) sur la plateforme.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
                <div className="space-y-4">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    Informations du Groupement
                  </h3>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="name">{tCommon("name")}</Label>
                      <Input id="name" {...register("name")} placeholder="Ex : Famille Bamileke" />
                      {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="slug">Sous-domaine (slug)</Label>
                      <Input id="slug" {...register("slug")} placeholder="Ex : bamileke" />
                      {errors.slug && <p className="text-xs text-destructive">{errors.slug.message}</p>}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="description">Description (optionnelle)</Label>
                    <Input
                      id="description"
                      {...register("description")}
                      placeholder="Ex : Mutuelle des membres…"
                    />
                  </div>
                </div>

                <div className="space-y-4 border-t pt-4">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    Compte Administrateur
                  </h3>
                  <div className="space-y-1.5">
                    <Label htmlFor="admin_name">Nom complet</Label>
                    <Input id="admin_name" {...register("admin_name")} placeholder="Ex : Jean Dupont" />
                    {errors.admin_name && (
                      <p className="text-xs text-destructive">{errors.admin_name.message}</p>
                    )}
                  </div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="admin_email">Email</Label>
                      <Input
                        id="admin_email"
                        type="email"
                        {...register("admin_email")}
                        placeholder="Ex : admin@bamileke.cm"
                      />
                      {errors.admin_email && (
                        <p className="text-xs text-destructive">{errors.admin_email.message}</p>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="admin_password">Mot de passe</Label>
                      <Input
                        id="admin_password"
                        type="password"
                        {...register("admin_password")}
                        placeholder="••••••••"
                      />
                      {errors.admin_password && (
                        <p className="text-xs text-destructive">{errors.admin_password.message}</p>
                      )}
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                    {tCommon("cancel")}
                  </Button>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? tCommon("saving") : tCommon("save")}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>{t("groupements")}</CardTitle>
          <CardDescription>Vue d&apos;ensemble des locataires actifs et suspendus.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : groupements.length === 0 ? (
            <EmptyState
              icon={Building2}
              title={t("empty")}
              description={t("emptyDesc")}
              action={
                <Button onClick={() => setOpen(true)} className="gap-2">
                  <Plus className="h-4 w-4" />
                  {tCommon("create")}
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{tCommon("name")}</th>
                    <th className="px-4 py-3 font-medium">Domaine</th>
                    <th className="px-4 py-3 font-medium">{tCommon("status")}</th>
                    <th className="px-4 py-3 font-medium">{tCommon("actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {groupements.map((g) => (
                    <tr key={g.id} className="transition-colors hover:bg-muted/50">
                      <td className="px-4 py-3 font-medium">{g.name}</td>
                      <td className="px-4 py-3 font-mono text-xs">{groupementHost(g)}</td>
                      <td className="px-4 py-3">
                        {g.is_active ? (
                          <Badge variant="success">{tCommon("active")}</Badge>
                        ) : (
                          <Badge variant="secondary">{tCommon("inactive")}</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/admin/groupements/${g.id}`} className="cursor-pointer">
                                <Eye className="mr-2 h-4 w-4" />
                                Voir les détails
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="cursor-pointer"
                              onClick={() => toggleStatus(g.id, g.is_active)}
                            >
                              {g.is_active ? (
                                <PowerOff className="mr-2 h-4 w-4 text-red-500" />
                              ) : (
                                <Power className="mr-2 h-4 w-4 text-emerald-500" />
                              )}
                              {g.is_active ? "Désactiver" : "Activer"}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
