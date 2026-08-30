import { AccountScreen } from "@/components/account-screen";
import { notFound } from "next/navigation";

export default async function AccountPage({params}: {params: Promise<{mode: string}>}) {
  const {mode} = await params;
  if (mode !== "login" && mode !== "register" && mode !== "verify" && mode !== "forgot" && mode !== "reset" && mode !== "resend") notFound();
  return <AccountScreen mode={mode} />;
}
