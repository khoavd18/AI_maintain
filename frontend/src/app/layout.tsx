import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist_Mono } from "next/font/google";

import { AuthenticatedApplication, AuthProvider } from "@/components/auth-provider";
import { QueryProvider } from "@/components/query-provider";

import "./globals.css";

const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-be-vietnam-pro",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Maintenance Copilot",
  description: "Bảng điều hành hỗ trợ quyết định bảo trì bằng dữ liệu tổng hợp.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className={`${beVietnamPro.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <QueryProvider>
          <AuthProvider>
            <AuthenticatedApplication>{children}</AuthenticatedApplication>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
