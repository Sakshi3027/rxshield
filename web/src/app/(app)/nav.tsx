"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/ask", label: "Ask" },
  { href: "/scenarios", label: "Scenarios" },
  { href: "/memos", label: "Memos" },
];

function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Main" className="flex gap-6 text-sm">
      {LINKS.map((link) => {
        const active = pathname?.startsWith(link.href) ?? false;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "font-medium text-ink underline decoration-public decoration-2 underline-offset-[6px]"
                : "text-muted hover:text-ink"
            }
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Nav() {
  return <NavLinks pathname={usePathname()} />;
}

export function NavFallback() {
  return <NavLinks pathname={null} />;
}
