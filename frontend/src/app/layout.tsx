import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ShopSessionProvider } from "@/context/ShopSessionContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "مساعد التسوق الذكي | AI for E-Commerce",
  description:
    "Arabic-first RTL shopping advisor comparing verified Top-3 Noon and Amazon offers across Egypt, Saudi Arabia, and UAE.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className="min-h-screen antialiased">
        <ShopSessionProvider>{children}</ShopSessionProvider>
      </body>
    </html>
  );
}
