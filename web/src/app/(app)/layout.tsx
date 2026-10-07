import Link from "next/link";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Nav, NavFallback } from "./nav";

type Me = { user_id: string; display_name: string; role: string; tenant_name: string };

async function Identity() {
  let me: Me;
  try {
    me = await api<Me>("/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      redirect("/login");
    }
    throw error;
  }
  const role = me.role.charAt(0).toUpperCase() + me.role.slice(1);
  return (
    <p className="text-sm text-muted">
      <span className="font-medium text-ink">{me.display_name}</span>, {role} at {me.tenant_name}
    </p>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-rule bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-4 py-4 sm:px-6">
          <Link href="/ask" className="text-lg font-semibold tracking-tight">
            RxShield
          </Link>
          <Suspense fallback={<NavFallback />}>
            <Nav />
          </Suspense>
          <div className="ml-auto flex items-center gap-4">
            <Suspense fallback={<span className="block h-4 w-56 rounded bg-rule motion-safe:animate-pulse" />}>
              <Identity />
            </Suspense>
            <form action="/api/logout" method="post">
              <button className="rounded-md border border-rule px-3 py-1.5 text-sm hover:border-ink">
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}
