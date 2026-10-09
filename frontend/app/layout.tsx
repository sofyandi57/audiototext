import type { Metadata, Viewport } from "next";
import { Nav } from "@/components/Nav";
import { PwaRegister } from "@/components/PwaRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Meeting Intelligence Indonesia",
  description: "Transkripsi rapat Bahasa Indonesia dan PDF ke audiobook, berjalan di CPU.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon.svg", apple: "/icons/icon-192.png" },
  appleWebApp: { capable: true, title: "MeetingID", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1f5fbf",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>
        <Nav />
        <main className="container">
          <PwaRegister />
          {children}
        </main>
      </body>
    </html>
  );
}
