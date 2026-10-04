import type { Metadata, Viewport } from "next";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Meeting Intelligence Indonesia",
  description: "Transkripsi rapat Bahasa Indonesia dan PDF ke audiobook, berjalan di CPU.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>
        <Nav />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
