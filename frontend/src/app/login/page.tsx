"use client";

import { Loader2, LockKeyhole, Wrench } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { defaultRouteFor, useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { safeReturnPath } from "@/lib/auth";
import { getApiErrorMessage } from "@/lib/api/errors";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const auth = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const intended = safeReturnPath(searchParams.get("next"));

  useEffect(() => {
    if (auth.status === "authenticated" && auth.user) {
      router.replace(intended ?? defaultRouteFor(auth.user));
    }
  }, [auth.status, auth.user, intended, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const user = await auth.login({ identifier, password });
      router.replace(intended ?? defaultRouteFor(user));
    } catch (cause) {
      setError(getApiErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="mb-3 flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Wrench className="size-5" aria-hidden="true" />
          </div>
          <CardTitle>Đăng nhập AI Maintenance Copilot</CardTitle>
          <p className="text-sm text-muted-foreground">
            Sử dụng tài khoản nội bộ được quản trị viên cấp.
          </p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={submit}>
            <div className="space-y-1.5">
              <Label htmlFor="identifier">Username hoặc email</Label>
              <Input
                id="identifier"
                autoComplete="username"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Mật khẩu</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            {error && (
              <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-950">
                {error}
              </div>
            )}
            <Button className="w-full" type="submit" disabled={pending}>
              {pending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <LockKeyhole aria-hidden="true" />}
              Đăng nhập
            </Button>
          </form>
          <p className="mt-5 border-t pt-4 text-xs leading-5 text-muted-foreground">
            Đây là lớp hỗ trợ quyết định. Quản lý và kỹ thuật viên vẫn chịu trách nhiệm cho kiểm tra an toàn và quyết định cuối cùng.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
