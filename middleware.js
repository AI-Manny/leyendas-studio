// Simple site-wide login gate (HTTP Basic Auth).
// The browser shows a native username/password prompt.
// Credentials are read from Vercel environment variables SITE_USER / SITE_PASS,
// so they are NEVER stored in this (public) repository.
// If either variable is unset, the gate is disabled (so you can't lock yourself out).

export const config = { matcher: '/:path*' };

export default function middleware(request) {
  const expectedUser = process.env.SITE_USER;
  const expectedPass = process.env.SITE_PASS;

  if (!expectedUser || !expectedPass) {
    return; // no credentials configured -> allow through
  }

  const header = request.headers.get('authorization') || '';
  if (header.startsWith('Basic ')) {
    let decoded = '';
    try { decoded = atob(header.slice(6)); } catch (e) { decoded = ''; }
    const i = decoded.indexOf(':');
    const user = decoded.slice(0, i);
    const pass = decoded.slice(i + 1);
    if (user === expectedUser && pass === expectedPass) {
      return; // authenticated -> continue to the app
    }
  }

  return new Response('Authentication required.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Leyendas Studio"' },
  });
}
