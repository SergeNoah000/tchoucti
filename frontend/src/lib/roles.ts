import type { User } from "./types";

/**
 * 4 espaces fonctionnels, déduits du profil utilisateur.
 * `association_admin` n'est pas encore détectable côté API → fallback `member`.
 */
export type AppRole =
  | "super_admin"
  | "groupement_admin"
  | "association_admin"
  | "member";

export function detectRole(
  user:
    | Pick<User, "is_platform_admin" | "is_groupement_admin" | "is_association_admin">
    | null
    | undefined,
): AppRole {
  if (!user) return "member";
  if (user.is_platform_admin) return "super_admin";
  if (user.is_groupement_admin) return "groupement_admin";
  if (user.is_association_admin) return "association_admin";
  return "member";
}

export interface RoleTheme {
  /** dataset value applied on the shell root, used by globals.css to swap --primary */
  dataRole: AppRole;
  /** Tailwind palette base (e.g. "violet"). Used only via the explicit `roleClasses` map below. */
  palette: "violet" | "sky" | "emerald" | "brand";
  /** translation key under `roles.*` */
  i18nKey:
    | "super_admin"
    | "groupement_admin"
    | "association_admin"
    | "member";
  /** translation key under `shell.contexts.*` */
  contextKey: "platform" | "groupement" | "association" | "member";
}

export const ROLE_THEMES: Record<AppRole, RoleTheme> = {
  super_admin: { dataRole: "super_admin", palette: "violet", i18nKey: "super_admin", contextKey: "platform" },
  groupement_admin: { dataRole: "groupement_admin", palette: "sky", i18nKey: "groupement_admin", contextKey: "groupement" },
  association_admin: { dataRole: "association_admin", palette: "emerald", i18nKey: "association_admin", contextKey: "association" },
  member: { dataRole: "member", palette: "brand", i18nKey: "member", contextKey: "member" },
};

/**
 * Static class lookup so Tailwind JIT actually generates these utilities.
 * Never use template-string Tailwind classes built from `palette` at runtime.
 */
export const ROLE_CLASSES: Record<
  AppRole,
  {
    pillBg: string;
    pillText: string;
    pillRing: string;
    iconBg: string;
    iconText: string;
    dotBg: string;
  }
> = {
  super_admin: {
    pillBg: "bg-violet-100 dark:bg-violet-900/30",
    pillText: "text-violet-700 dark:text-violet-300",
    pillRing: "ring-violet-200 dark:ring-violet-800",
    iconBg: "bg-violet-100 dark:bg-violet-900/40",
    iconText: "text-violet-700 dark:text-violet-300",
    dotBg: "bg-violet-500",
  },
  groupement_admin: {
    pillBg: "bg-sky-100 dark:bg-sky-900/30",
    pillText: "text-sky-700 dark:text-sky-300",
    pillRing: "ring-sky-200 dark:ring-sky-800",
    iconBg: "bg-sky-100 dark:bg-sky-900/40",
    iconText: "text-sky-700 dark:text-sky-300",
    dotBg: "bg-sky-500",
  },
  association_admin: {
    pillBg: "bg-emerald-100 dark:bg-emerald-900/30",
    pillText: "text-emerald-700 dark:text-emerald-300",
    pillRing: "ring-emerald-200 dark:ring-emerald-800",
    iconBg: "bg-emerald-100 dark:bg-emerald-900/40",
    iconText: "text-emerald-700 dark:text-emerald-300",
    dotBg: "bg-emerald-500",
  },
  member: {
    pillBg: "bg-brand-100 dark:bg-brand-900/30",
    pillText: "text-brand-700 dark:text-brand-300",
    pillRing: "ring-brand-200 dark:ring-brand-800",
    iconBg: "bg-brand-100 dark:bg-brand-900/40",
    iconText: "text-brand-700 dark:text-brand-300",
    dotBg: "bg-brand-500",
  },
};
