import type { Metadata } from "next";
import { headers } from "next/headers";
import { notFound } from "next/navigation";

import { BrandedLogin } from "@/components/auth/branded-login";
import { fetchAssociationBranding } from "@/lib/branding";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ g?: string }>;
};

/** Resolve the groupement from the subdomain (x-tenant-slug set by middleware)
 *  or, for local dev without subdomains, from the `?g=` query param. */
async function resolve(params: Props["params"], searchParams: Props["searchParams"]) {
  const { slug } = await params;
  const { g } = await searchParams;
  const groupement = (await headers()).get("x-tenant-slug") || g || "";
  if (!groupement || !slug) return null;
  return fetchAssociationBranding(groupement, slug);
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const branding = await resolve(params, searchParams);
  if (!branding) return { title: "Connexion" };
  const { association } = branding;
  const images = association.logo_url ? [association.logo_url] : undefined;
  return {
    title: `${association.name} — Connexion`,
    description: `Espace membre de ${association.name}.`,
    openGraph: {
      title: association.name,
      description: `Espace membre de ${association.name}.`,
      images,
    },
    twitter: {
      card: "summary",
      title: association.name,
      description: `Espace membre de ${association.name}.`,
      images,
    },
  };
}

export default async function BrandedLoginPage({ params, searchParams }: Props) {
  const branding = await resolve(params, searchParams);
  if (!branding) notFound();
  return <BrandedLogin branding={branding} />;
}
