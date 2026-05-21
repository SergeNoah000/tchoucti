import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { defaultLocale, locales, type Locale } from "./config";

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const localeCookie = cookieStore.get("NEXT_LOCALE");
  let locale: Locale = defaultLocale;

  if (localeCookie?.value && locales.includes(localeCookie.value as Locale)) {
    locale = localeCookie.value as Locale;
  } else {
    const headerStore = await headers();
    const acceptLang = headerStore.get("accept-language") || "";
    const browserLang = acceptLang.split(",")[0]?.split("-")[0]?.toLowerCase();
    if (browserLang && locales.includes(browserLang as Locale)) {
      locale = browserLang as Locale;
    }
  }

  return {
    locale,
    messages: (await import(`./locales/${locale}.json`)).default,
  };
});
