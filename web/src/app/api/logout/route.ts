import { NextResponse } from "next/server";
import { TOKEN_COOKIE } from "@/lib/api";

export async function POST(request: Request) {
  const result = NextResponse.redirect(new URL("/login", request.url), 303);
  result.cookies.delete(TOKEN_COOKIE);
  return result;
}
