"use client";
/* eslint-disable next/no-html-link-for-pages -- Full document navigation intentionally clears verification tokens and account form state. */

import { useEffect, useState, type SubmitEvent } from "react";
import { ArrowRight, Check, Eye, EyeOff, LockKeyhole, Mail, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Mode = "login" | "register" | "verify" | "forgot" | "reset" | "resend";
type Locale = "zh-TW" | "en" | "ja";
const copy = {
  "zh-TW": {
    title: "讓靈感，\n在此生成。", intro: "一個帳號，連接本機媒體引擎。你的提示詞、參照素材與生成作品，留在這台主機。",
    login: "登入工作室", register: "建立服務帳號", verify: "驗證電子郵件", forgot: "忘記密碼", reset: "設定新密碼", resend: "重寄驗證信",
    name: "姓名", username: "帳號", email: "電子郵件", password: "密碼", confirm: "再次輸入密碼",
    passwordHint: "8–128 個字元，英數即可，不強制特殊符號；也可使用較長的密語。", usernameHint: "3–32 個英文字母、數字、底線、點或連字號。",
    showPassword: "顯示密碼", hidePassword: "隱藏密碼",
    cloudflareNote: "註冊後會自動同步信箱至 Cloudflare 允許名單。外部登入時由 Cloudflare 寄出登入碼，驗證同一信箱後，再輸入本機帳密。本機不代寄驗證信。",
    cloudflareCreated: "帳號已建立，信箱已同步至 Cloudflare。請前往驗證，使用註冊時的信箱取得登入碼，再登入本機服務。",
    cloudflarePending: "帳號已建立，Cloudflare 名單同步暫未完成，系統會重試尚未送出的請求。請勿重複註冊；稍後再開啟外部入口，或聯絡管理者。",
    cloudflareReview: "帳號已建立，但 Cloudflare 同步結果需要管理者確認。為保留撤權設定，不會重複加入；請勿重新註冊。",
    cloudflareContinue: "前往 Cloudflare 驗證信箱",
    loginNote: "已完成 Email 驗證？請使用帳號與密碼重新登入。", registerNote: "完成註冊後，開啟信箱中的驗證連結，再回到此處登入。",
    verifyNote: "按下確認後完成信箱驗證。不會自動登入，請再輸入帳號與密碼。", resetNote: "更新密碼後，所有既有登入都會失效。請重新登入。",
    emailNote: "輸入註冊時使用的電子郵件。我們會在符合條件時寄送連結。", sent: "如資料符合條件，驗證／重設連結將寄至信箱。也請檢查垃圾郵件；重寄需間隔至少 60 秒。",
    verified: "電子郵件驗證完成。請重新登入後開始生成。", resetDone: "密碼已更新。請使用新密碼登入。", waiting: "處理中…", submitEmail: "寄送連結", confirmVerify: "確認驗證",
    back: "返回登入", noAccount: "還沒有帳號？", hasAccount: "已經有帳號？", toRegister: "建立帳號", toLogin: "登入", mismatch: "兩次密碼不一致。",
    unavailable: "註冊目前尚未開放，或寄信服務尚未完成設定。請聯絡主機管理者。", tokenMissing: "缺少驗證連結，或頁面已重新整理。請從信箱重新開啟連結，或申請重寄。",
    network: "無法連接帳號服務，請稍後重試。", privacy: "密碼加鹽雜湊 · 個人素材隔離 · 驗證後重新登入", steps: ["建立帳號", "信箱驗證", "重新登入", "開始生成"],
    footer: "通用媒體服務入口 / LOCAL-FIRST MEDIA SERVICE", language: "介面語言",
    internalBadge: "內部測試模式 · 暫不使用郵件驗證",
    internalLoginNote: "使用本機已註冊的帳號與密碼登入，不需信箱驗證。",
    internalRegisterNote: "姓名、帳號、密碼與 Email 會保存在本機。註冊後即可返回登入，不寄送驗證信。",
    internalCreated: "帳號已建立。請返回登入，輸入剛設定的帳號與密碼後開始使用。",
    internalPrivacy: "密碼加鹽雜湊 · 個人素材隔離 · Email 尚未驗證所有權",
    internalSteps: ["建立帳號", "帳號密碼登入", "開始生成"],
    internalEmailDisabled: "內部測試期間不寄信，驗證及郵件重設功能暫停。忘記密碼請聯絡主機管理者；不要重新註冊同一帳號。",
    emailUnavailable: "郵件功能尚未就緒，請聯絡主機管理者。",
  },
  en: {
    title: "Make room\nfor your next idea.", intro: "One account for your local media engine. Prompts, references and generated work stay on this host.",
    login: "Sign in to the studio", register: "Create a service account", verify: "Verify your email", forgot: "Forgot password", reset: "Set a new password", resend: "Resend verification",
    name: "Name", username: "Username", email: "Email", password: "Password", confirm: "Confirm password",
    passwordHint: "8–128 characters. Letters and numbers are enough; special characters are optional. Longer passphrases are welcome.", usernameHint: "3–32 letters, numbers, underscores, dots or hyphens.",
    showPassword: "Show password", hidePassword: "Hide password",
    cloudflareNote: "Registration syncs your email to the Cloudflare allowlist. Cloudflare sends a login code when you open the external site; verify the same email, then sign in with your local credentials. This host does not send the code.",
    cloudflareCreated: "Account created and email synced to Cloudflare. Continue to verify your registered email with a login code, then sign in to the local service.",
    cloudflarePending: "Account created; Cloudflare sync is pending. Requests not yet sent will retry. Do not register again. Try the external entry later or contact the administrator.",
    cloudflareReview: "Account created, but the administrator must check the Cloudflare sync result. To respect revoked access, it will not append again. Do not register again.",
    cloudflareContinue: "Verify email with Cloudflare",
    loginNote: "Email verified? Sign in again with your username and password.", registerNote: "Register, open the verification link in your inbox, then return to sign in.",
    verifyNote: "Confirm email ownership below. Verification does not sign you in automatically.", resetNote: "Changing your password ends all existing sessions. Sign in again afterwards.",
    emailNote: "Enter your registered email. Eligible accounts will receive a link.", sent: "If the details are eligible, a verification/reset link will arrive. Check spam too; allow at least 60 seconds before resending.",
    verified: "Email verified. Sign in again to start generating.", resetDone: "Password updated. Sign in with your new password.", waiting: "Working…", submitEmail: "Send link", confirmVerify: "Confirm verification",
    back: "Back to sign in", noAccount: "New here?", hasAccount: "Already registered?", toRegister: "Create an account", toLogin: "Sign in", mismatch: "Passwords do not match.",
    unavailable: "Registration is closed or email delivery is not configured. Contact the host administrator.", tokenMissing: "The link is missing or the page was refreshed. Open it again from your inbox or request another link.",
    network: "Cannot reach the account service. Please try again.", privacy: "Salted password hashes · Private assets · Fresh sign-in after verification", steps: ["Register", "Verify email", "Sign in again", "Generate"],
    footer: "LOCAL-FIRST MEDIA SERVICE / ONE SERVICE, MANY PROJECTS", language: "Language",
    internalBadge: "INTERNAL TESTING · EMAIL VERIFICATION PAUSED",
    internalLoginNote: "Sign in with an account registered on this host. Email verification is not required for internal testing.",
    internalRegisterNote: "Your name, username, password hash and email are stored locally. Register, then sign in; no verification email is sent.",
    internalCreated: "Account created. Return to sign in with your new username and password.",
    internalPrivacy: "Salted password hashes · Private assets · Email ownership not verified",
    internalSteps: ["Register", "Sign in", "Generate"],
    internalEmailDisabled: "Internal testing does not send email. Verification and email password resets are paused. Contact the host administrator if you forget your password; do not register the same account again.",
    emailUnavailable: "Email features are not ready. Contact the host administrator.",
  },
  ja: {
    title: "次のひらめきを、\nここから。", intro: "一つのアカウントでローカルのメディアエンジンへ。プロンプト、参照素材、作品はこのホストに保存されます。",
    login: "スタジオにログイン", register: "アカウントを作成", verify: "メールアドレスを確認", forgot: "パスワードを忘れた", reset: "新しいパスワード", resend: "確認メールを再送",
    name: "氏名", username: "ユーザー名", email: "メールアドレス", password: "パスワード", confirm: "パスワードを再入力",
    passwordHint: "8～128文字。英数字で設定でき、記号は任意です。長いパスフレーズも使えます。", usernameHint: "3～32文字の英数字、アンダースコア、ドット、ハイフン。",
    showPassword: "パスワードを表示", hidePassword: "パスワードを隠す",
    cloudflareNote: "登録後、メールアドレスを Cloudflare の許可リストへ自動同期します。外部サイトで Cloudflare のログインコードを受け取り、同じメールを確認してからローカルのアカウントでログインします。本機からコードは送信しません。",
    cloudflareCreated: "アカウントを作成し、Cloudflare に同期しました。登録したメールアドレスをログインコードで確認してから、ローカルサービスにログインしてください。",
    cloudflarePending: "アカウントは作成済みですが、同期は保留中です。未送信の要求は再試行します。再登録せず、後で外部サイトを開くか管理者に連絡してください。",
    cloudflareReview: "アカウントは作成済みですが、Cloudflare の同期結果を管理者が確認する必要があります。権限の取り消しを尊重し、再追加は行いません。再登録しないでください。",
    cloudflareContinue: "Cloudflare でメールを確認",
    loginNote: "メール確認後、ユーザー名とパスワードで再ログインしてください。", registerNote: "登録後、受信した確認リンクを開き、ログイン画面へ戻ってください。",
    verifyNote: "下のボタンでメールを確認します。自動ではログインしません。", resetNote: "更新すると既存のログインはすべて無効になります。再ログインしてください。",
    emailNote: "登録したメールアドレスを入力してください。条件を満たす場合にリンクを送ります。", sent: "条件を満たす場合、確認・再設定リンクが届きます。迷惑メールも確認し、再送は60秒以上お待ちください。",
    verified: "メール確認が完了しました。再ログインして生成を開始できます。", resetDone: "パスワードを更新しました。新しいパスワードでログインしてください。", waiting: "処理中…", submitEmail: "リンクを送信", confirmVerify: "確認する",
    back: "ログインへ戻る", noAccount: "初めての方", hasAccount: "登録済みの方", toRegister: "アカウント作成", toLogin: "ログイン", mismatch: "パスワードが一致しません。",
    unavailable: "登録は停止中、またはメール設定が未完了です。管理者にお問い合わせください。", tokenMissing: "リンクがないか、ページが更新されました。メールから再度開くか、再送を申請してください。",
    network: "アカウントサービスに接続できません。再試行してください。", privacy: "ソルト付きハッシュ · 個人素材の分離 · 確認後に再ログイン", steps: ["登録", "メール確認", "再ログイン", "生成"],
    footer: "LOCAL-FIRST MEDIA SERVICE / 共通のメディアサービス", language: "表示言語",
    internalBadge: "内部テストモード · メール確認は一時停止中",
    internalLoginNote: "このホストに登録したユーザー名とパスワードでログインできます。メール確認は不要です。",
    internalRegisterNote: "氏名、ユーザー名、パスワードのハッシュ、メールアドレスをローカルに保存します。確認メールは送信せず、登録後にログインできます。",
    internalCreated: "アカウントを作成しました。新しいユーザー名とパスワードでログインしてください。",
    internalPrivacy: "ソルト付きハッシュ · 個人素材の分離 · メール所有権は未確認",
    internalSteps: ["登録", "ログイン", "生成"],
    internalEmailDisabled: "内部テスト中はメール送信、確認、メールによるパスワード再設定を停止しています。パスワードを忘れた場合は管理者に連絡してください。同じアカウントを再登録しないでください。",
    emailUnavailable: "メール機能はまだ利用できません。管理者にお問い合わせください。",
  },
};
const errors: Record<string, [string, string, string]> = {
  invalid_credentials: ["帳號或密碼不正確。", "Invalid username or password.", "ユーザー名またはパスワードが違います。"],
  email_not_verified: ["請先完成 Email 驗證，再重新登入。", "Verify your email before signing in.", "メール確認後にログインしてください。"],
  invalid_name: ["請填寫 1–80 字的姓名。", "Name must contain 1–80 characters.", "氏名は1～80文字で入力してください。"],
  invalid_username: ["帳號格式不正確，請依欄位說明輸入。", "Use the username format shown below the field.", "ユーザー名の形式を確認してください。"],
  invalid_email: ["請輸入有效的電子郵件。", "Enter a valid email address.", "有効なメールアドレスを入力してください。"],
  invalid_password: ["密碼長度需為 8–128 字元。", "Password must contain 8–128 characters.", "パスワードは8～128文字です。"],
  invalid_or_expired_token: ["連結無效或已過期，請重新申請。", "The link is invalid or expired. Request another.", "リンクが無効または期限切れです。再申請してください。"],
  rate_limited: ["操作過於頻繁，請稍後再試。", "Too many attempts. Try again later.", "試行回数が多すぎます。しばらくお待ちください。"],
  email_delivery_failed: ["寄信暫時失敗，請稍後重寄或聯絡管理者。", "Email delivery failed. Retry later or contact the administrator.", "メール送信に失敗しました。再送するか管理者に連絡してください。"],
  account_unavailable: ["帳號或電子郵件已被使用。若已註冊，請使用原密碼登入；忘記密碼請聯絡管理者。", "Username or email is already in use. Sign in with your existing password, or contact the administrator.", "ユーザー名またはメールアドレスは使用済みです。既存のパスワードでログインするか、管理者に連絡してください。"],
  email_disabled_in_internal_mode: ["內部測試模式不使用郵件功能。請返回登入或聯絡管理者。", "Email features are disabled for internal testing. Sign in or contact the administrator.", "内部テスト中はメール機能を利用できません。ログインするか管理者に連絡してください。"],
  cloudflare_email_mismatch: ["Cloudflare 驗證信箱與此帳號不同，請使用註冊時的同一信箱通過 Cloudflare。", "Cloudflare email does not match this account. Authenticate with the registered email.", "Cloudflare と登録アカウントのメールアドレスが異なります。同じメールで認証してください。"],
  cloudflare_login_required: ["請先通過 Cloudflare 信箱驗證，再登入本機服務。", "Authenticate with Cloudflare before signing in to the local service.", "先に Cloudflare で認証してください。"],
  cloudflare_identity_invalid: ["Cloudflare 驗證已失效或無法確認，請重新通過外層登入。", "Cloudflare authentication expired or could not be verified. Sign in to Cloudflare again.", "Cloudflare 認証を確認できません。再度認証してください。"],
};

export function AccountScreen({ mode }: { mode: Mode }) {
  const [locale, setLocale] = useState<Locale>("zh-TW");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [authMode, setAuthMode] = useState("verified_email");
  const [emailReady, setEmailReady] = useState(false);
  const [configLoaded, setConfigLoaded] = useState(false);
  const [configFailed, setConfigFailed] = useState(false);
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, boolean>>({});
  const [cloudflareEnabled, setCloudflareEnabled] = useState(false);
  const [verificationUrl, setVerificationUrl] = useState("");
  const text = copy[locale];
  const internal = authMode === "internal";
  const emailAvailable = configLoaded && emailReady && !internal;
  const emailMode = ["verify", "reset", "resend", "forgot"].includes(mode);
  const steps = internal ? text.internalSteps : text.steps;
  const currentStep = mode === "register" ? 0 : internal ? 1 : mode === "verify" ? 1 : 2;
  useEffect(() => {
    const saved = localStorage.getItem("ltx-studio-locale");
    // eslint-disable-next-line react/react-compiler -- Hydrate browser-only preferences after the server render.
    if (saved === "zh-TW" || saved === "en" || saved === "ja") setLocale(saved);
    const value = new URLSearchParams(location.hash.slice(1)).get("token") || "";
    setToken(value);
    if (location.hash) history.replaceState(null, "", location.pathname);
    fetch("/api/auth/config", {credentials: "same-origin", cache: "no-store"}).then(r => {
      if (!r.ok) throw new Error("Account settings unavailable");
      return r.json() as Promise<{registration_open?: boolean; auth_mode?: string; email_ready?: boolean; cloudflare_sync_enabled?: boolean; cloudflare_verification_url?: string}>;
    }).then(data => {
      setRegistrationOpen(Boolean(data.registration_open));
      setAuthMode(data.auth_mode || "verified_email");
      setEmailReady(Boolean(data.email_ready));
      setCloudflareEnabled(Boolean(data.cloudflare_sync_enabled));
      if (data.cloudflare_verification_url?.startsWith("https://")) setVerificationUrl(data.cloudflare_verification_url);
      setConfigLoaded(true);
    }).catch(() => setConfigFailed(true));
  }, []);
  const changeLocale = (value: string | null) => {
    if (value === "zh-TW" || value === "en" || value === "ja") {
      setLocale(value); localStorage.setItem("ltx-studio-locale", value); document.documentElement.lang = value;
    }
  };
  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(""); setNotice("");
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    if ((mode === "register" || mode === "reset") && fields.password !== fields.confirm) { setError(text.mismatch); return; }
    delete fields.confirm;
    setVisiblePasswords({});
    setBusy(true);
    try {
      const response = await fetch(`/api/auth/${mode}`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify(mode === "verify" ? {token} : mode === "reset" ? {token, password: fields.password} : fields)});
      const result = await response.json() as {code: string; verification_required?: boolean; cloudflare_sync_status?: string};
      if (!response.ok) {
        const index = locale === "zh-TW" ? 0 : locale === "en" ? 1 : 2;
        throw new Error(errors[result.code]?.[index] || (["email_not_configured", "registration_closed", "auth_unavailable"].includes(result.code) ? text.unavailable : text.network));
      }
      if (mode === "login") { location.assign("/"); return; }
      if (mode === "register" && result.cloudflare_sync_status) {
        setNotice(result.cloudflare_sync_status === "synced" ? text.cloudflareCreated : result.cloudflare_sync_status === "pending" ? text.cloudflarePending : text.cloudflareReview);
        return;
      }
      setNotice(mode === "register" && result.verification_required === false ? text.internalCreated : mode === "verify" ? text.verified : mode === "reset" ? text.resetDone : text.sent);
    } catch (issue) { setError(issue instanceof Error ? issue.message : text.network); }
    finally { setBusy(false); }
  };
  const note = internal ? mode === "login" ? text.internalLoginNote : mode === "register" ? text.internalRegisterNote : text.internalEmailDisabled : mode === "login" ? text.loginNote : mode === "register" ? text.registerNote : mode === "verify" ? text.verifyNote : mode === "reset" ? text.resetNote : text.emailNote;
  const formField = (name: string, label: string, type = "text", hint?: string) => <div className="space-y-2" key={name}>
    <Label htmlFor={name} className="text-[11px] font-bold tracking-[0.12em]">{label}</Label>
    <div className="relative">
      <Input id={name} name={name} type={type === "password" && visiblePasswords[name] ? "text" : type} required autoComplete={name === "password" ? mode === "login" ? "current-password" : "new-password" : name === "confirm" ? "new-password" : name}
        minLength={type === "password" && mode !== "login" ? 8 : undefined} maxLength={type === "password" ? 128 : name === "name" ? 80 : name === "username" ? 32 : 254}
        aria-describedby={hint ? `${name}-hint` : undefined}
        className={`h-12 rounded-none border-[#deded9] bg-[#fafaf8] px-3 text-sm shadow-none focus-visible:ring-2 focus-visible:ring-[#ff6f91]/20 ${type === "password" ? "pr-12" : ""}`} />
      {type === "password" && <Button type="button" variant="ghost" size="icon"
        aria-label={`${visiblePasswords[name] ? text.hidePassword : text.showPassword} (${label})`}
        aria-pressed={Boolean(visiblePasswords[name])} aria-controls={name}
        title={visiblePasswords[name] ? text.hidePassword : text.showPassword}
        onClick={() => setVisiblePasswords(current => ({...current, [name]: !current[name]}))}
        className="absolute inset-y-0 right-0 my-auto size-11 rounded-none text-muted-foreground hover:bg-[#fff3f6] hover:text-[#c53d60] focus-visible:ring-2 focus-visible:ring-[#ff6f91]/30">
        {visiblePasswords[name] ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
      </Button>}
    </div>
    {hint && <p id={`${name}-hint`} className="text-[10px] leading-5 text-muted-foreground">{hint}</p>}
  </div>;
  return <main className="min-h-screen bg-background text-foreground">
    <div className="border-b border-border bg-[#f7f7f5] p-2 text-center text-[9px] font-semibold tracking-[0.18em] text-muted-foreground">{internal ? text.internalBadge : "LOCAL GENERATION / YOUR PRIVATE WORKSPACE"}</div>
    <header className="flex items-center justify-between gap-5 border-b border-border bg-white px-6 py-5 lg:px-12">
      <a href="/auth/login" className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-full bg-foreground text-background"><Video className="size-4" /></span><span className="text-sm font-extrabold tracking-[0.13em]">LTX LOCAL STUDIO</span></a>
      <Select value={locale} onValueChange={changeLocale}><SelectTrigger aria-label={text.language} className="w-32"><SelectValue /></SelectTrigger><SelectContent align="end"><SelectItem value="zh-TW">繁體中文</SelectItem><SelectItem value="en">English</SelectItem><SelectItem value="ja">日本語</SelectItem></SelectContent></Select>
    </header>
    <div className="mx-auto grid max-w-[1320px] gap-10 px-6 py-12 md:grid-cols-[1fr_1fr] lg:gap-24 lg:px-12 lg:py-20">
      <section className="flex flex-col justify-between border-l border-border pl-6 lg:pl-10">
        <div><p className="mb-6 text-[10px] font-bold tracking-[0.24em] text-[#e85578]">01 / SERVICE ACCESS</p><h1 className="whitespace-pre-line text-4xl font-extrabold leading-[1.3] tracking-[0.03em] lg:text-5xl">{text.title}</h1><p className="mt-6 max-w-md text-sm leading-7 text-muted-foreground">{text.intro}</p></div>
        <ol className="mt-10 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-border pt-7">{steps.map((step, index) => <li key={step} className="flex items-center gap-3 text-[11px] font-semibold"><span className={`grid size-7 shrink-0 place-items-center border text-[10px] ${index === currentStep ? "border-[#e85578] bg-[#fff3f6] text-[#c53d60]" : "border-border text-muted-foreground"}`}>0{index + 1}</span>{step}</li>)}</ol>
      </section>
      <section className="border border-border bg-white">
        <div className="grid grid-cols-2 border-b border-border text-center text-[11px] font-bold tracking-[0.15em]">{(["login", "register"] as const).map(item => <a key={item} href={`/auth/${item}`} className={`border-b-2 px-4 py-4 ${mode === item ? "border-[#ff6f91] bg-[#fff8fa]" : "border-transparent text-muted-foreground hover:bg-muted"}`}>{text[item]}</a>)}</div>
        <div className="p-6 lg:p-9"><div className="mb-6"><span className="mb-4 inline-flex size-9 items-center justify-center border border-border">{mode === "login" ? <LockKeyhole className="size-4 text-[#e85578]" /> : <Mail className="size-4 text-[#159c8f]" />}</span><h2 className="text-xl font-extrabold tracking-[0.05em]">{text[mode]}</h2><p className="mt-3 text-xs leading-6 text-muted-foreground">{note}</p></div>
          {cloudflareEnabled && !emailMode && <p className="mb-5 border-l-2 border-[#159c8f] bg-[#f0fbf9] p-3 text-xs leading-6 text-[#11786f]">{text.cloudflareNote}</p>}
          {cloudflareEnabled && verificationUrl && notice && <a href={verificationUrl} className="mb-5 block border border-[#159c8f] bg-[#f0fbf9] p-4 text-center text-xs font-bold text-[#11786f]">{text.cloudflareContinue}<ArrowRight className="ml-2 inline size-4" aria-hidden="true" /></a>}
          {mode === "register" && !registrationOpen && <output className="mb-5 block border-l-2 border-[#e85578] bg-[#fff8fa] p-3 text-xs leading-6">{configFailed ? text.network : configLoaded ? text.unavailable : text.waiting}</output>}
          {emailMode && !emailAvailable ? <output className="block border-l-2 border-[#e85578] bg-[#fff8fa] p-3 text-xs leading-6">{configFailed ? text.network : !configLoaded ? text.waiting : internal ? text.internalEmailDisabled : text.emailUnavailable}</output> : notice ? <div aria-live="polite" className="space-y-5"><p className="border border-[#bfe8e3] bg-[#f0fbf9] p-4 text-sm leading-7 text-[#11786f]"><Check className="mb-2 size-5" />{notice}</p><a href="/auth/login" className="block bg-foreground p-4 text-center text-xs font-bold text-background">{text.back}</a>{emailAvailable && <a href="/auth/resend" className="block text-center text-xs text-muted-foreground underline underline-offset-4">{text.resend}</a>}</div> : <form onSubmit={submit} className="space-y-5">
            {mode === "register" && formField("name", text.name)}
            {(mode === "login" || mode === "register") && formField("username", text.username, "text", mode === "register" ? text.usernameHint : undefined)}
            {["register", "forgot", "resend"].includes(mode) && formField("email", text.email, "email")}
            {["login", "register", "reset"].includes(mode) && formField("password", text.password, "password", mode === "login" ? undefined : text.passwordHint)}
            {["register", "reset"].includes(mode) && formField("confirm", text.confirm, "password")}
            {["verify", "reset"].includes(mode) && !token && <p role="alert" className="text-xs leading-6 text-red-700">{text.tokenMissing}</p>}
            {error && <p role="alert" className="border border-red-200 bg-red-50 p-3 text-xs leading-6 text-red-700">{error}</p>}
            <Button type="submit" disabled={busy || (mode === "register" && !registrationOpen) || (["verify", "reset"].includes(mode) && !token)} className="h-12 w-full rounded-none text-xs font-bold tracking-[0.12em] hover:bg-[#e85578]">{busy ? text.waiting : mode === "forgot" || mode === "resend" ? text.submitEmail : mode === "verify" ? text.confirmVerify : text[mode]}<ArrowRight className="size-4" /></Button>
          </form>}
          <div className="mt-6 flex flex-wrap justify-between gap-4 text-[11px] text-muted-foreground">{emailAvailable && <><a href="/auth/forgot" className="underline underline-offset-4">{text.forgot}</a><a href="/auth/resend" className="underline underline-offset-4">{text.resend}</a></>}{mode !== "login" && <a href="/auth/login" className="underline underline-offset-4">{text.back}</a>}</div>
          {internal && !emailMode && <p className="mt-4 text-[10px] leading-5 text-muted-foreground">{text.internalEmailDisabled}</p>}
        </div><p className="border-t border-border px-6 py-4 text-center text-[9px] leading-5 tracking-[0.04em] text-muted-foreground">{internal ? text.internalPrivacy : text.privacy}</p>
      </section>
    </div><footer className="border-t border-border px-6 py-5 text-center text-[9px] font-semibold tracking-[0.14em] text-muted-foreground">{text.footer}</footer>
  </main>;
}
