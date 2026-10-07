import { Suspense } from "react";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";

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
  return (
    <p className="mt-1 text-sm text-neutral-500">
      {me.display_name} · {me.role} · {me.tenant_name}
    </p>
  );
}

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">RxShield</h1>
          <Suspense fallback={<p className="mt-2 h-4 w-64 animate-pulse rounded bg-neutral-800" />}>
            <Identity />
          </Suspense>
        </div>
        <form action="/api/logout" method="post">
          <button className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm">Sign out</button>
        </form>
      </div>
    </main>
  );
}
