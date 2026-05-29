import type { AssociationBranding } from "@/lib/types";

/** Server-side fetch of public association branding (used by the branded login
 *  route for SSR + Open Graph). Uses the internal API base when running inside
 *  the container, falling back to the public one. Returns null on 404/error. */
export async function fetchAssociationBranding(
  groupement: string,
  association: string,
): Promise<AssociationBranding | null> {
  const base =
    process.env.API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:18000/api";
  try {
    const res = await fetch(
      `${base}/public/association-branding?groupement=${encodeURIComponent(groupement)}&association=${encodeURIComponent(association)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as AssociationBranding;
  } catch {
    return null;
  }
}
