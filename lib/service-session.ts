export type ServiceUser = {id: string; name: string; username: string; email: string; email_verified: boolean};
export type ServiceSession = {required: boolean; authenticated: boolean; user: ServiceUser | null; csrf_token: string | null; auth_mode?: 'verified_email' | 'internal'; cloudflare_logout_url?: string | null};
let csrf: string | null = null;
export const sessionChangeKey = 'ltx-session-change';

export async function readSession(): Promise<ServiceSession> {
  const response = await fetch('/api/auth/session', {credentials: 'same-origin', cache: 'no-store', redirect: 'error', headers: {'X-Requested-With': 'XMLHttpRequest'}});
  if (!response.ok) throw new Error('Account service unavailable');
  const session = await response.json() as ServiceSession;
  csrf = session.csrf_token;
  return session;
}

export function csrfHeader(): Record<string, string> {
  return csrf ? {'X-CSRF-Token': csrf} : {};
}

export async function serviceFetch(path: string, options: RequestInit = {}) {
  if (!path.startsWith('/api/') || path.startsWith('//')) throw new Error('Service requests must use same-origin API paths');
  const headers = new Headers(options.headers);
  headers.set('X-Requested-With', 'XMLHttpRequest');
  if (!['GET', 'HEAD'].includes(options.method || 'GET')) {
    if (!csrf) await readSession();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  const send = () => fetch(path, {...options, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
  let response = await send();
  // Another tab can rotate the cookie while this tab still has an old CSRF
  // value. Retry once, and ONLY when the server confirms no mutation occurred.
  if (response.status === 403 && !['GET', 'HEAD'].includes(options.method || 'GET')) {
    const error = await response.clone().json().catch(() => ({})) as {code?: string};
    if (error.code === 'csrf_failed') {
      await readSession();
      if (csrf) headers.set('X-CSRF-Token', csrf); else headers.delete('X-CSRF-Token');
      response = await send();
    }
  }
  if (response.status === 401) window.dispatchEvent(new Event('ltx-session-expired'));
  return response;
}

export async function signOut(full = false): Promise<string> {
  const response = await serviceFetch('/api/auth/logout', {method: 'POST'});
  if (!response.ok) throw new Error('Sign-out failed');
  const result = await response.json() as {ok?: boolean; cloudflare_logout_url?: string | null};
  if (result.ok !== true) throw new Error('Sign-out was not confirmed');
  csrf = null;
  // No identity or token is stored here: only a notification to other tabs.
  try { localStorage.setItem(sessionChangeKey, crypto.randomUUID()); } catch { /* Storage may be disabled. */ }
  return full && result.cloudflare_logout_url === '/cdn-cgi/access/logout' ? result.cloudflare_logout_url : '/auth/login?signed_out=1';
}
