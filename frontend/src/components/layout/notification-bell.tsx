"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { notificationsApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AppNotification } from "@/lib/types";

export function NotificationBell() {
  const t = useTranslations("notifications");
  const router = useRouter();
  const queryClient = useQueryClient();
  const fmt = useFormatters();

  const { data: countData } = useQuery<{ unread: number }>({
    queryKey: ["notif-unread"],
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 60_000, // poll toutes les minutes
    refetchOnWindowFocus: true,
  });
  const unread = countData?.unread ?? 0;

  const { data: items = [] } = useQuery<AppNotification[]>({
    queryKey: ["notif-list"],
    queryFn: () => notificationsApi.list({ limit: 15 }),
    refetchInterval: 60_000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notif-unread"] });
    queryClient.invalidateQueries({ queryKey: ["notif-list"] });
  };

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: invalidate,
  });
  const markAll = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: invalidate,
  });

  const onItemClick = (n: AppNotification) => {
    if (!n.read_at) markRead.mutate(n.id);
    if (n.action_url) {
      // action_url est une URL absolue (FRONTEND_URL/...) ou un chemin.
      try {
        const url = new URL(n.action_url);
        router.push(url.pathname + url.search);
      } catch {
        router.push(n.action_url);
      }
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-9 w-9" aria-label={t("title")}>
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-sm font-semibold">{t("title")}</p>
          {unread > 0 && (
            <button
              type="button"
              onClick={() => markAll.mutate()}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              {t("markAllRead")}
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">{t("empty")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => onItemClick(n)}
                    className={cn(
                      "flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-accent/50",
                      !n.read_at && "bg-primary/5",
                    )}
                  >
                    <div className="flex w-full items-start gap-2">
                      {!n.read_at && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                      <span className={cn("text-sm leading-tight", !n.read_at ? "font-semibold" : "font-medium")}>
                        {n.title}
                      </span>
                    </div>
                    {n.body && <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>}
                    <span className="text-[11px] text-muted-foreground">{fmt.date(n.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
