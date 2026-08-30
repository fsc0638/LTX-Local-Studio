"use client";
/* eslint-disable next/no-html-link-for-pages -- A fresh document clears in-memory session and CSRF state at the authentication boundary. */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { LogOut, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { readSession, serviceFetch, type ServiceSession } from '@/lib/service-session';

const AccountContext = createContext<ServiceSession | null>(null);

export function AccountGate({children}: {children: ReactNode}) {
  const [session, setSession] = useState<ServiceSession | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    const expired = () => { setSession(null); location.replace('/auth/login'); };
    window.addEventListener('ltx-session-expired', expired);
    readSession().then(value => {
      if (!active) return;
      if (value.required && !value.authenticated) expired();
      else setSession(value);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; window.removeEventListener('ltx-session-expired', expired); };
  }, []);
  if (!session) return <main className="grid min-h-screen place-items-center bg-background p-8"><div className="max-w-md border border-border bg-white p-8"><p className="text-xs font-extrabold tracking-[0.2em]">LTX LOCAL STUDIO</p><output className="mt-4 block text-sm leading-7 text-muted-foreground">{failed ? '帳號服務暫時無法連線 / Account service unavailable / 接続できません' : '確認登入狀態 / Checking your session / ログイン状態を確認中'}</output>{failed && <a href="/auth/login" className="mt-6 inline-block text-xs text-[#e85578] underline">登入 / Sign in / ログイン</a>}</div></main>;
  return <AccountContext.Provider value={session}>{children}</AccountContext.Provider>;
}

export function AccountMenu({locale}: {locale: 'zh-TW' | 'en' | 'ja'}) {
  const session = useContext(AccountContext);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  if (!session?.user) return null;
  const label = locale === 'zh-TW' ? '登出' : locale === 'en' ? 'Sign out' : 'ログアウト';
  const logout = async () => {
    setBusy(true); setError(false);
    try {
      const response = await serviceFetch('/api/auth/logout', {method: 'POST'});
      if (!response.ok) throw new Error();
      location.replace('/auth/login');
    } catch { setError(true); setBusy(false); }
  };
  return <div className="flex items-center gap-2 border-l border-border pl-3 text-[10px]">
    {session.auth_mode === 'internal' && <span className="border border-[#efc4d0] bg-[#fff3f6] px-2 py-1 text-[#a32e4a]">{locale === 'zh-TW' ? '內部測試' : locale === 'en' ? 'Internal test' : '内部テスト'}</span>}
    <span className="hidden max-w-32 truncate sm:block" title={session.user.email}><ShieldCheck className="mr-1 inline size-3 text-[#159c8f]" />{session.user.name}</span>
    <Button variant="ghost" disabled={busy} onClick={logout} aria-label={label} className="rounded-none text-[10px]"><LogOut className="size-3" /><span className="hidden md:inline">{label}</span></Button>
    {error && <span role="alert" className="text-red-700">{locale === 'zh-TW' ? '登出失敗，請重試' : locale === 'en' ? 'Sign-out failed' : 'ログアウト失敗'}</span>}
  </div>;
}
