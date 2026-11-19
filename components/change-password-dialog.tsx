'use client';

import { useState, type SubmitEvent } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { changePassword } from '@/lib/service-session';

const copy = {
  'zh-TW': {title: '修改密碼', note: '輸入舊密碼與新密碼。成功後，所有裝置都必須使用新密碼重新登入。', current: '舊密碼', next: '新密碼', confirm: '確認新密碼', hint: '8–128 個字元；新密碼不可與舊密碼相同。', show: '顯示密碼', save: '儲存新密碼', busy: '更新中…', success: '密碼已更新，請使用新密碼重新登入。', login: '重新登入', wrong: '舊密碼不正確。', mismatch: '兩次輸入的新密碼不一致。', invalid: '新密碼須為 8–128 個字元。', same: '新密碼不可與舊密碼相同。', limited: '嘗試次數過多，請稍後再試。', failed: '無法更新密碼，請重試。'},
  en: {title: 'Change password', note: 'Enter your current and new passwords. After saving, all devices must sign in again with the new password.', current: 'Current password', next: 'New password', confirm: 'Confirm new password', hint: '8–128 characters; use a different password.', show: 'Show passwords', save: 'Save new password', busy: 'Updating…', success: 'Password updated. Sign in again with your new password.', login: 'Sign in again', wrong: 'Current password is incorrect.', mismatch: 'New passwords do not match.', invalid: 'New password must be 8–128 characters.', same: 'Choose a different password.', limited: 'Too many attempts. Try again later.', failed: 'Could not update password. Please retry.'},
  ja: {title: 'パスワード変更', note: '現在と新しいパスワードを入力してください。変更後はすべての端末で再ログインが必要です。', current: '現在のパスワード', next: '新しいパスワード', confirm: '新しいパスワードの確認', hint: '8～128文字。現在とは異なるパスワードを設定してください。', show: 'パスワードを表示', save: '新しいパスワードを保存', busy: '更新中…', success: '更新しました。新しいパスワードで再ログインしてください。', login: '再ログイン', wrong: '現在のパスワードが正しくありません。', mismatch: '新しいパスワードが一致しません。', invalid: '新しいパスワードは8～128文字です。', same: '現在とは異なるパスワードを設定してください。', limited: '試行回数が多すぎます。しばらくしてからお試しください。', failed: '更新できませんでした。もう一度お試しください。'},
};

export function ChangePasswordDialog({locale, username, disabled = false}: {locale: keyof typeof copy; username: string; disabled?: boolean}) {
  const t = copy[locale];
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [values, setValues] = useState({current: '', next: '', confirm: ''});
  const onOpenChange = (value: boolean) => {
    if (busy) return;
    if (success) { location.replace('/auth/login'); return; }
    setOpen(value); setError(''); setShow(false); setValues({current: '', next: '', confirm: ''});
  };
  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    if (values.next !== values.confirm) { setError(t.mismatch); return; }
    if (values.next === values.current) { setError(t.same); return; }
    setBusy(true); setError('');
    try {
      await changePassword(values.current, values.next, values.confirm);
      setValues({current: '', next: '', confirm: ''}); setShow(false); setSuccess(true);
    } catch (reason) {
      const code = reason instanceof Error ? reason.message : '';
      const messages: Record<string, string> = {current_password_incorrect: t.wrong, password_mismatch: t.mismatch, invalid_password: t.invalid, password_unchanged: t.same, rate_limited: t.limited};
      setError(messages[code] || t.failed);
    } finally { setBusy(false); }
  };
  return <>
    <Button type="button" variant="ghost" disabled={disabled} onClick={() => onOpenChange(true)} className="rounded-none text-[10px]"><KeyRound className="size-3" />{t.title}</Button>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={!busy}>
        <DialogHeader><DialogTitle>{t.title}</DialogTitle><DialogDescription>{t.note}</DialogDescription></DialogHeader>
        {success ? <div className="space-y-4"><output className="block">{t.success}</output><Button type="button" onClick={() => location.replace('/auth/login')}>{t.login}</Button></div> :
          <form onSubmit={submit} className="space-y-4">
            <input type="text" name="username" autoComplete="username" value={username} readOnly hidden />
            {(['current', 'next', 'confirm'] as const).map(field => <div key={field} className="space-y-1">
              <label htmlFor={`change-password-${field}`} className="text-sm font-medium">{t[field]}</label>
              <Input id={`change-password-${field}`} name={field} type={show ? 'text' : 'password'} autoComplete={field === 'current' ? 'current-password' : 'new-password'}
                required minLength={field === 'current' ? undefined : 8} maxLength={128} disabled={busy} value={values[field]} onChange={event => setValues({...values, [field]: event.target.value})} />
            </div>)}
            <p className="text-xs text-muted-foreground">{t.hint}</p>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={show} disabled={busy} onChange={event => setShow(event.target.checked)} />{t.show}</label>
            {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
            <Button type="submit" disabled={busy} className="w-full">{busy ? t.busy : t.save}</Button>
          </form>}
      </DialogContent>
    </Dialog>
  </>;
}
