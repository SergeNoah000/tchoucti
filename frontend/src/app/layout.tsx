import type { Metadata } from "next";
// Polices embarquées (package `geist`) au lieu de next/font/google : le build
// Docker n'a pas besoin d'accès à fonts.gstatic.com (qui échoue sur certains
// hôtes / VPS).
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { Toaster } from "sonner";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: { default: "Tchoucti — La plateforme des associations", template: "%s · Tchoucti" },
  description:
    "Gérez vos associations, séances de réunion, cotisations, prêts et tontines en toute sérénité.",
  icons: { icon: "/icon.svg" },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className={`${GeistSans.variable} ${GeistMono.variable} font-sans antialiased`}>

        <NextIntlClientProvider messages={messages}>
          <Providers>{children}</Providers>
          <Toaster richColors position="top-right" closeButton />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
