"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard", icon: "⌂" },
  { href: "/meetings/", label: "Rapat", icon: "◉" },
  { href: "/audiobooks/", label: "Audiobook", icon: "▤" },
  { href: "/jobs/", label: "Jobs", icon: "≡" },
  { href: "/settings/", label: "Settings", icon: "⚙" },
];

export function Nav() {
  const path = usePathname() || "/";
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, "")));
  return (
    <nav className="nav" aria-label="Navigasi utama">
      <Link href="/" className="brand">
        Meeting Intelligence <span className="muted">ID</span>
      </Link>
      <ul>
        {ITEMS.map((it) => (
          <li key={it.href}>
            <Link href={it.href} aria-current={active(it.href) ? "page" : undefined}>
              <span className="nav-icon" aria-hidden>
                {it.icon}
              </span>
              <span className="nav-label">{it.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
