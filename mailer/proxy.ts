// Next 16 renamed the `middleware` convention to `proxy`. This refreshes the
// Supabase session on every request (tokens expire; without this you get
// random logouts) and keeps signed-out visitors on /login.

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    }
  );

  // getUser() revalidates against Supabase; getSession() trusts the cookie.
  const { data } = await supabase.auth.getUser();

  const isLogin = request.nextUrl.pathname.startsWith("/login");
  if (!data.user && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (data.user && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  // Everything except static assets -- without this the redirect would also
  // swallow CSS and JS requests.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
