export type ServiceUser = {id: string; name: string; username: string; email: string; email_verified: boolean};
export type ServiceSession = {required: boolean; authenticated: boolean; user: ServiceUser | null; csrf_token: string | null; auth_mode?: 'verified_email' | 'internal'};
let csrf: string | null = null;

export async function readSession(): Promise<ServiceSession> {
  const response = await fetch('/api/auth/session', {credentials: 'same-origin', cache: 'no-store'});
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
  if (!['GET', 'HEAD'].includes(options.method || 'GET')) {
    if (!csrf) await readSession();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
  if (response.status === 401) window.dispatchEvent(new Event('ltx-session-expired'));
  return response;
}
