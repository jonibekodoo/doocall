import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import "./globals.css";

import { Providers } from "@/components/Providers";

// Inter for UI; Space Grotesk is the display face reserved for the landing.
const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
});
const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "dooCall",
  description: "dooCall — qo'ng'iroqlarni yozib olish va nazorat qilish SaaS",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();
  return (
    // suppressHydrationWarning: the inline script below sets data-theme on
    // <html> BEFORE React hydrates (no-flash theme restore), so the client
    // attribute legitimately differs from the server HTML. Standard pattern
    // (next-themes does the same); it silences attribute diffs on this one
    // element only, not on children.
    <html
      lang={locale}
      className={`${inter.variable} ${display.variable}`}
      suppressHydrationWarning
    >
      <body>
        <script
          // Restore theme before first paint (no flash).
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('doocall_theme');if(t)document.documentElement.dataset.theme=t}catch(e){}",
          }}
        />
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
