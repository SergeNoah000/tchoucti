"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * Barre de progression fine en haut de page pendant les changements de page
 * (façon Facebook/YouTube). Sans dépendance : démarre au clic sur un lien
 * interne (ou retour/avant navigateur), avance par paliers, puis se termine
 * quand la nouvelle route est rendue. Fonctionne en dev ET en prod.
 *
 * NB : le log `[Fast Refresh] rebuilding/done` est propre au mode dev (HMR de
 * Turbopack) et n'existe pas en production ; cette barre suit la navigation
 * réelle entre pages, ce qui couvre le ressenti de « page qui change ».
 */
export function NavProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);
  const trickle = useRef<number | null>(null);
  const timers = useRef<number[]>([]);
  const firstRender = useRef(true);

  const clearAll = () => {
    if (trickle.current) {
      window.clearInterval(trickle.current);
      trickle.current = null;
    }
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const start = () => {
    clearAll();
    setVisible(true);
    setWidth(8);
    trickle.current = window.setInterval(() => {
      setWidth((w) => (w < 90 ? w + Math.max(0.4, (90 - w) * 0.08) : w));
    }, 220);
    // Filet de sécurité : termine après un délai même si la route ne change pas
    // (ex. navigation annulée ou changement de query string seul).
    timers.current.push(window.setTimeout(() => done(), 8000));
  };

  const done = () => {
    clearAll();
    setWidth(100);
    timers.current.push(window.setTimeout(() => setVisible(false), 220));
    timers.current.push(window.setTimeout(() => setWidth(0), 450));
  };

  // Démarrage : clic sur un lien interne + retour/avant navigateur.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement | null)?.closest?.("a");
      if (!a) return;
      const href = a.getAttribute("href");
      if (!href || a.target === "_blank" || a.hasAttribute("download")) return;
      if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      let url: URL;
      try {
        url = new URL(href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      // Même page exacte → pas de navigation.
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      start();
    };
    const onPop = () => start();
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", onPop);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", onPop);
    };
  }, []);

  // Fin : la route a changé (nouvelle page rendue).
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    done();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, searchParams]);

  useEffect(() => clearAll, []);

  if (!visible && width === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[200] h-0.5">
      <div
        className="h-full rounded-r-full bg-primary transition-[width,opacity] duration-200 ease-out"
        style={{
          width: `${width}%`,
          opacity: visible ? 1 : 0,
          boxShadow: "0 0 8px 0 hsl(var(--primary)), 0 0 4px 0 hsl(var(--primary))",
        }}
      />
    </div>
  );
}
