"use client";

import { useEffect } from "react";
import type { AppRole } from "./roles";

/**
 * Hex colors matching the role primary defined in globals.css.
 * Kept in sync manually — change both when retuning the palette.
 */
const ROLE_PRIMARY_HEX: Record<AppRole, string> = {
  super_admin: "#7c3aed",        // violet-600
  groupement_admin: "#0ea5e9",   // sky-500
  association_admin: "#0d9488",  // emerald-700 (close enough at 32% L)
  member: "#0d9488",             // brand teal (matches the default --primary)
};

/**
 * Inline SVG matching the `Users` lucide icon, with a rounded square
 * background filled with the role primary color. Encoded as a data URI.
 */
function buildFavicon(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
    <rect width="32" height="32" rx="7" fill="${color}"/>
    <g fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" transform="translate(4 4)">
      <path d="M16 19v-2a4 4 0 0 0-4-4H4a4 4 0 0 0-4 4v2"/>
      <circle cx="8" cy="5" r="4"/>
      <path d="M22 19v-2a4 4 0 0 0-3-3.87"/>
      <path d="M15 1.13a4 4 0 0 1 0 7.75"/>
    </g>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

/**
 * Swaps the `<link rel="icon">` href to a role-tinted favicon. Tracks the
 * link element it injected so it doesn't leak across role changes.
 */
export function useRoleFavicon(role: AppRole) {
  useEffect(() => {
    if (typeof document === "undefined") return;
    const href = buildFavicon(ROLE_PRIMARY_HEX[role]);

    // Remove any existing <link rel="icon"> so the browser definitely picks ours up.
    const existing = document.querySelectorAll<HTMLLinkElement>("link[rel~='icon']");
    existing.forEach((el) => el.parentNode?.removeChild(el));

    const link = document.createElement("link");
    link.rel = "icon";
    link.type = "image/svg+xml";
    link.href = href;
    document.head.appendChild(link);

    return () => {
      // On unmount (e.g. logout), restore the static favicon.
      link.parentNode?.removeChild(link);
      const fallback = document.createElement("link");
      fallback.rel = "icon";
      fallback.type = "image/svg+xml";
      fallback.href = "/icon.svg";
      document.head.appendChild(fallback);
    };
  }, [role]);
}
