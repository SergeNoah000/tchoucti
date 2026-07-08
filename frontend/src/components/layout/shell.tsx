"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ForcePasswordChange } from "@/components/auth/force-password-change";
import {
  LayoutDashboard,
  Users,
  Calendar,
  Wallet,
  Banknote,
  Repeat,
  HeartHandshake,
  FolderKanban,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  Building2,
  Check,
  CreditCard,
  ShieldCheck,
  ScrollText,
  FileUp,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { BrandMark } from "@/components/common/brand-mark";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { LanguageToggle } from "@/components/common/language-toggle";
import { NotificationBell } from "@/components/layout/notification-bell";
import { useAuthStore, usePermissionStore } from "@/lib/store";
import {
  authApi,
  associationsApi,
  getCurrentAssociationId,
  setCurrentAssociationId,
} from "@/lib/api";
import { cn, initials } from "@/lib/utils";
import { detectRole, ROLE_THEMES, ROLE_CLASSES, type AppRole } from "@/lib/roles";
import { useRoleFavicon } from "@/lib/use-role-favicon";

interface NavItem {
  href: string;
  icon: LucideIcon;
  key: string; // i18n key under "nav.*"
}

interface NavSection {
  /** i18n key under `nav.sections.*`, or `null` to render items without a heading */
  label: string | null;
  items: NavItem[];
}

const PLATFORM_NAV: NavSection[] = [
  {
    label: null,
    items: [
      { href: "/admin", icon: LayoutDashboard, key: "dashboard" },
      { href: "/admin/groupements", icon: Building2, key: "groupements" },
      { href: "/admin/associations", icon: FolderKanban, key: "associations" },
      { href: "/admin/users", icon: Users, key: "users" },
    ],
  },
  {
    label: "operations",
    items: [
      { href: "/admin/billing", icon: CreditCard, key: "billing" },
      { href: "/admin/audit", icon: ScrollText, key: "audit" },
      { href: "/admin/settings", icon: Settings, key: "settings" },
    ],
  },
];

const GROUPEMENT_NAV: NavSection[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", icon: LayoutDashboard, key: "dashboard" },
      { href: "/dashboard/groupement", icon: Building2, key: "myGroupement" },
      { href: "/dashboard/associations", icon: FolderKanban, key: "associations" },
      { href: "/dashboard/meetings", icon: Calendar, key: "meetings" },
      { href: "/dashboard/members", icon: Users, key: "members" },
    ],
  },
  {
    label: "finance",
    items: [
      { href: "/dashboard/finance", icon: Wallet, key: "finance" },
      { href: "/dashboard/loans", icon: Banknote, key: "loans" },
      { href: "/dashboard/tontines", icon: Repeat, key: "tontines" },
    ],
  },
  {
    label: "programs",
    items: [
      { href: "/dashboard/social-aid", icon: HeartHandshake, key: "socialAid" },
      { href: "/dashboard/projects", icon: FolderKanban, key: "projects" },
    ],
  },
  {
    label: "tools",
    items: [
      { href: "/dashboard/documents", icon: FileText, key: "documents" },
      { href: "/dashboard/reports", icon: BarChart3, key: "reports" },
      { href: "/dashboard/settings", icon: Settings, key: "settings" },
    ],
  },
];

const ASSOCIATION_NAV: NavSection[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", icon: LayoutDashboard, key: "dashboard" },
      { href: "/dashboard/my-association", icon: Building2, key: "myAssociation" },
      { href: "/dashboard/meetings", icon: Calendar, key: "meetings" },
      { href: "/dashboard/members", icon: Users, key: "members" },
    ],
  },
  {
    label: "finance",
    items: [
      { href: "/dashboard/finance", icon: Wallet, key: "finance" },
      { href: "/dashboard/finance/validations", icon: ShieldCheck, key: "payoutValidations" },
      { href: "/dashboard/loans", icon: Banknote, key: "loans" },
      { href: "/dashboard/tontines", icon: Repeat, key: "tontines" },
      { href: "/dashboard/social-aid", icon: HeartHandshake, key: "socialAid" },
    ],
  },
  {
    label: "config",
    items: [
      // Tontines are created/managed from the operational "Tontines" page above
      // (no separate type/instance split like loans & aids), so no duplicate here.
      { href: "/dashboard/config/caisses", icon: Wallet, key: "configCaisses" },
      { href: "/dashboard/config/loans", icon: Banknote, key: "configLoans" },
      { href: "/dashboard/config/aids", icon: HeartHandshake, key: "configAids" },
    ],
  },
  {
    label: "tools",
    items: [
      { href: "/dashboard/import", icon: FileUp, key: "import" },
      { href: "/dashboard/documents", icon: FileText, key: "documents" },
      { href: "/dashboard/settings", icon: Settings, key: "settings" },
    ],
  },
];

const MEMBER_NAV: NavSection[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", icon: LayoutDashboard, key: "dashboard" },
      { href: "/dashboard/meetings", icon: Calendar, key: "meetings" },
    ],
  },
  {
    label: "personal",
    items: [
      { href: "/dashboard/finance", icon: Wallet, key: "myContributions" },
      { href: "/dashboard/loans", icon: Banknote, key: "myLoans" },
      { href: "/dashboard/documents", icon: FileText, key: "documents" },
      { href: "/dashboard/settings", icon: Settings, key: "settings" },
    ],
  },
];

function navForRole(role: AppRole): NavSection[] {
  switch (role) {
    case "super_admin":
      return PLATFORM_NAV;
    case "groupement_admin":
      return GROUPEMENT_NAV;
    case "association_admin":
      return ASSOCIATION_NAV;
    case "member":
      return MEMBER_NAV;
  }
}

/** Un trésorier (ou secrétaire/manager) est routé comme rôle « member » dans la
 *  nav (is_association_admin est strict). On lui ajoute alors dynamiquement
 *  l'accès à la file de validation des sorties d'argent. Les admins l'ont déjà
 *  en statique ; les simples membres ne le voient pas. */
function navWithBureauExtras(sections: NavSection[], isBureau: boolean): NavSection[] {
  if (!isBureau) return sections;
  const already = sections.some((s) =>
    s.items.some((i) => i.href === "/dashboard/finance/validations"),
  );
  if (already) return sections;
  const item: NavItem = {
    href: "/dashboard/finance/validations",
    icon: ShieldCheck,
    key: "payoutValidations",
  };
  const financeIdx = sections.findIndex((s) => s.label === "finance" || s.label === "personal");
  if (financeIdx >= 0) {
    const next = [...sections];
    next[financeIdx] = {
      ...next[financeIdx],
      items: [...next[financeIdx].items, item],
    };
    return next;
  }
  return [...sections, { label: "finance", items: [item] }];
}

interface ShellProps {
  children: React.ReactNode;
  /** Force a specific role context (e.g. "/admin" pages should always use platform nav) */
  forceRole?: AppRole;
  /** Where the logo links to */
  homeHref?: string;
}

export function Shell({ children, forceRole, homeHref }: ShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const tNav = useTranslations("nav");
  const tShell = useTranslations("shell");
  const tCommon = useTranslations("common");
  const tRoles = useTranslations("roles");
  const { user, hasHydrated, isAuthenticated, logout, setUser } = useAuthStore();
  const { clear: clearPerms } = usePermissionStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const detectedRole = detectRole(user);
  const role: AppRole = forceRole ?? detectedRole;
  const theme = ROLE_THEMES[role];
  const classes = ROLE_CLASSES[role];

  const nav = useMemo(
    () => navWithBureauExtras(navForRole(role), !!user?.has_bureau_role),
    [role, user?.has_bureau_role],
  );

  // Associations de l'utilisateur (pour le verrou/sélecteur de session).
  // Réservé aux utilisateurs réguliers : un admin plateforme n'a pas de
  // « mon association ». La liste remonte déjà l'association courante en [0].
  const { data: myAssociations } = useQuery<Array<{ id: string; name: string }>>({
    queryKey: ["associations"],
    queryFn: () => associationsApi.list(),
    enabled: hasHydrated && isAuthenticated && !!user && !user.is_platform_admin,
  });
  const associations = myAssociations ?? [];
  const currentAssocId = getCurrentAssociationId();
  const currentAssoc =
    associations.find((a) => a.id === currentAssocId) ?? associations[0];

  const switchAssociation = (id: string) => {
    if (id === currentAssoc?.id) return;
    setCurrentAssociationId(id);
    // Rechargement dur : toutes les requêtes se re-scopent sur la nouvelle
    // association (désormais en [0]) proprement.
    window.location.assign("/dashboard");
  };

  useRoleFavicon(role);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) router.replace("/login");
  }, [hasHydrated, isAuthenticated, router]);

  // Refresh the persisted user once on mount — keeps role flags in sync after
  // backend schema changes (a stale localStorage user would mis-route the UI).
  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;
    authApi
      .getMe()
      .then((fresh) => setUser(fresh))
      .catch(() => {
        /* 401 handled by the axios interceptor */
      });
  }, [hasHydrated, isAuthenticated, setUser]);

  // Block /admin to non-platform admins
  useEffect(() => {
    if (!hasHydrated || !user) return;
    if (forceRole === "super_admin" && !user.is_platform_admin) {
      router.replace("/dashboard");
    }
  }, [hasHydrated, user, forceRole, router]);

  if (!hasHydrated || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  // Compte créé avec un mot de passe par défaut → changement obligatoire avant
  // tout accès à l'application.
  if (user.must_change_password) {
    return <ForcePasswordChange />;
  }

  // Verrou de session : un utilisateur régulier appartenant à plusieurs
  // associations doit en CHOISIR une avant d'accéder à l'app. Le choix scope
  // toute la session (l'association devient [0] partout). Modifiable ensuite
  // depuis le menu profil.
  if (myAssociations && associations.length > 1 && !currentAssocId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-brand-50/40 to-background p-4 dark:via-brand-950/10">
        <div className="w-full max-w-md rounded-xl border border-border/60 bg-card p-6 shadow-xl">
          <div className="mb-1 flex items-center gap-2">
            <Building2 className={cn("h-5 w-5", classes.iconText)} />
            <h1 className="text-lg font-semibold">{tShell("chooseAssociationTitle")}</h1>
          </div>
          <p className="mb-5 text-sm text-muted-foreground">
            {tShell("chooseAssociationHint")}
          </p>
          <div className="space-y-2">
            {associations.map((a) => (
              <button
                key={a.id}
                onClick={() => switchAssociation(a.id)}
                className="flex w-full items-center gap-3 rounded-lg border border-border/60 px-4 py-3 text-left transition-colors hover:border-brand-400 hover:bg-brand-50/50 dark:hover:bg-brand-950/20"
              >
                <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate font-medium">{a.name}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore — clear local state regardless
    }
    logout();
    clearPerms();
    // Libère le verrou d'association : l'utilisateur suivant sur ce navigateur
    // ne doit pas hériter du choix du précédent.
    setCurrentAssociationId(null);
    // Navigation DURE (et non router.push) : détruit tout l'état React et les
    // requêtes en vol (poll des notifications, etc.). Sans ça, une requête qui
    // se termine en 401 après le logout déclenchait la redirection « dure » de
    // l'intercepteur axios, en conflit avec la navigation soft → page blanche.
    window.location.assign("/login");
  };

  const resolvedHome = homeHref ?? (role === "super_admin" ? "/admin" : "/dashboard");

  return (
    <div data-role={theme.dataRole} className="flex h-screen overflow-hidden bg-muted/30">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-sidebar text-sidebar-foreground transition-transform lg:relative lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center border-b border-sidebar-border px-6">
          <Link href={resolvedHome} className="flex items-center">
            <BrandMark size="sm" variant="primary" />
          </Link>
        </div>

        {/* Role context banner */}
        <div className="px-3 pt-3">
          <div
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-wider ring-1",
              classes.pillBg,
              classes.pillText,
              classes.pillRing
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", classes.dotBg)} />
            {tShell(`contexts.${theme.contextKey}`)}
          </div>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-3">
          {nav.map((section, idx) => (
            <div key={section.label ?? `s-${idx}`} className="space-y-0.5">
              {section.label && (
                <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {tShell(`sections.${section.label}`)}
                </p>
              )}
              {section.items.map(({ href, icon: Icon, key }) => {
                const active = pathname === href || pathname.startsWith(href + "/");
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setSidebarOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{tNav(key)}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <Separator />
        <div className="p-3">
          <div className="flex items-center gap-3 rounded-lg px-3 py-2">
            <Avatar className="h-9 w-9">
              <AvatarFallback className={cn("text-xs font-semibold", classes.iconBg, classes.iconText)}>
                {initials(user.full_name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{user.full_name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Overlay (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Topbar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur lg:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="Toggle menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
            {/* Role pill */}
            <div
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1",
                classes.pillBg,
                classes.pillText,
                classes.pillRing
              )}
            >
              {role === "super_admin" && <ShieldCheck className="h-3.5 w-3.5" />}
              {role !== "super_admin" && <span className={cn("h-1.5 w-1.5 rounded-full", classes.dotBg)} />}
              {tRoles(theme.i18nKey)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <LanguageToggle />
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full">
                  <Avatar className="h-8 w-8">
                    <AvatarFallback className={cn("text-xs font-semibold", classes.iconBg, classes.iconText)}>
                      {initials(user.full_name)}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div className="flex flex-col">
                    <span className="text-sm font-medium">{user.full_name}</span>
                    <span className="text-xs text-muted-foreground">{user.email}</span>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href={role === "super_admin" ? "/admin/settings" : "/dashboard/settings"}>
                    <Settings className="h-4 w-4" />
                    {tNav("settings")}
                  </Link>
                </DropdownMenuItem>
                {associations.length > 1 && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                      {tShell("activeAssociation")}
                    </DropdownMenuLabel>
                    {associations.map((a) => (
                      <DropdownMenuItem
                        key={a.id}
                        onClick={() => switchAssociation(a.id)}
                        className="gap-2"
                      >
                        <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="flex-1 truncate">{a.name}</span>
                        {a.id === currentAssoc?.id && (
                          <Check className="h-4 w-4 shrink-0 text-brand-600" />
                        )}
                      </DropdownMenuItem>
                    ))}
                  </>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4" />
                  {tCommon("logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="container mx-auto px-4 py-6 lg:px-6 lg:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
