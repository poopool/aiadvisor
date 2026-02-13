"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/analyst", label: "Analyst" },
  { href: "/approval-queue", label: "Queue" },
  { href: "/watchtower", label: "Watchtower" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col min-h-screen">
      <div className="p-4 border-b border-slate-700">
        <h1 className="font-semibold text-slate-100 text-lg">AI Advisor</h1>
        <p className="text-xs text-slate-400 mt-0.5">Command Center</p>
      </div>
      <nav className="p-3 flex flex-col gap-1">
        {nav.map(({ href, label }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-slate-700 text-white"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
