import { NextResponse, type NextRequest } from "next/server";

/** Server-side portal guard (A.1).
 *
 * The `doocall_portal` cookie is a ROUTING HINT set at login (admin |
 * partner | cabinet) — real security lives in the API's role guards (403).
 * Wrong-portal navigation renders the 403 page instead of a broken shell.
 */
export function middleware(request: NextRequest) {
  const portal = request.cookies.get("doocall_portal")?.value;
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/admin") && portal !== "admin") {
    return NextResponse.rewrite(new URL("/403", request.url));
  }
  if (pathname.startsWith("/partner") && portal !== "partner") {
    return NextResponse.rewrite(new URL("/403", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/partner/:path*"],
};
