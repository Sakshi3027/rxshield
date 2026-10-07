import { NextResponse } from "next/server";
import { API_URL, TOKEN_COOKIE } from "@/lib/api";

export async function POST(request: Request) {
  const { userId, password } = await request.json();
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, password }),
    cache: "no-store",
  });
  if (!response.ok) {
    return NextResponse.json({ error: "Invalid user or password." }, { status: 401 });
  }
  const { access_token, expires_in } = await response.json();
  const result = NextResponse.json({ ok: true });
  result.cookies.set(TOKEN_COOKIE, access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: expires_in,
  });
  return result;
}
