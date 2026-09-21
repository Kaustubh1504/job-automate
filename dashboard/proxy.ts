// Next 16 renamed the `middleware` convention to `proxy`. This refreshes the
// Supabase session (tokens expire; without this you get random logouts) and
// keeps signed-out visitors on /login.
//
// Only the mailer is gated. The job views and /config are open, as they have
// always been -- the matcher below is what keeps them that way.

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
    url.pathname = "/mailer";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  // The mailer only. The /api/mailer/* routes guard themselves with
  // requireUser(), so they do not need to be listed here -- and listing the
  // job views would put the whole dashboard behind a login.
  matcher: ["/mailer/:path*", "/login"],
};
