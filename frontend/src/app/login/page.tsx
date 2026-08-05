"use client";

import {
  CheckCircle2,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { defaultRouteFor, useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { safeReturnPath } from "@/lib/auth";
import { getApiErrorMessage } from "@/lib/api/errors";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-sidebar" />}>
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
    <main className="min-h-dvh bg-sidebar lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(440px,0.95fr)]">
      <section
        aria-label="Giới thiệu AI Maintenance Copilot"
        className="relative isolate overflow-hidden px-5 py-6 text-sidebar-foreground sm:px-8 lg:min-h-dvh lg:px-12 lg:py-10"
      >
        <div
          aria-hidden="true"
          className="absolute -right-24 -top-24 size-72 rounded-full bg-blue-500/20 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-32 -left-24 size-80 rounded-full bg-sky-300/10 blur-3xl"
        />
        <div className="relative mx-auto flex h-full max-w-2xl flex-col">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-lg bg-blue-500 text-white shadow-sm shadow-blue-950/20">
              <Wrench className="size-5" aria-hidden="true" />
            </span>
            <span>
              <span className="block text-sm font-semibold tracking-tight text-white">
                Bảo trì thiết bị
              </span>
              <span className="block text-xs text-sidebar-foreground/65">
                Maintenance Copilot
              </span>
            </span>
          </div>

          <div className="mt-10 lg:my-auto">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">
              Không gian vận hành tập trung
            </p>
            <h2 className="mt-3 max-w-xl text-2xl font-semibold leading-tight tracking-tight text-white sm:text-3xl lg:text-4xl">
              Theo dõi công việc bảo trì quan trọng từ một góc nhìn thống nhất.
            </h2>
            <p className="mt-4 hidden max-w-xl text-sm leading-6 text-sidebar-foreground/70 sm:block lg:text-base">
              Kết nối tài sản, sự cố, lệnh công việc và tồn kho để đội ngũ có
              đủ ngữ cảnh trước khi ưu tiên hành động.
            </p>
            <ul className="mt-8 hidden space-y-3 text-sm text-sidebar-foreground/80 lg:block">
              <li className="flex items-center gap-3">
                <CheckCircle2 className="size-4 text-blue-300" aria-hidden="true" />
                Phân tích theo lô từ dữ liệu đã được kiểm tra.
              </li>
              <li className="flex items-center gap-3">
                <CheckCircle2 className="size-4 text-blue-300" aria-hidden="true" />
                Quyền truy cập theo đúng vai trò vận hành.
              </li>
            </ul>
          </div>

          <p className="mt-10 hidden text-xs text-sidebar-foreground/50 lg:block">
            Dành cho đội ngũ vận hành nội bộ
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center rounded-t-3xl bg-background px-4 py-8 sm:px-8 lg:min-h-dvh lg:rounded-none lg:px-12">
        <Card className="w-full max-w-md shadow-xl shadow-slate-950/8">
          <CardHeader className="gap-2 px-5 pt-2 sm:px-6">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              Cổng vận hành nội bộ
            </p>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
              Đăng nhập hệ thống bảo trì
            </h1>
            <p id="login-description" className="text-sm leading-5 text-muted-foreground">
              Sử dụng tài khoản nội bộ được quản trị viên cấp.
            </p>
          </CardHeader>
          <CardContent className="px-5 sm:px-6">
            <form
              className="space-y-4"
              onSubmit={submit}
              aria-describedby="login-description"
              aria-busy={pending}
            >
              <div className="space-y-1.5">
                <Label htmlFor="identifier">Tên đăng nhập hoặc email</Label>
                <Input
                  id="identifier"
                  autoComplete="username"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  required
                  autoFocus
                  disabled={pending}
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
                  disabled={pending}
                />
              </div>
              {error && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-950"
                >
                  {error}
                </div>
              )}
              <Button className="h-10 w-full" type="submit" disabled={pending}>
                {pending ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <LockKeyhole aria-hidden="true" />
                )}
                {pending ? "Đang đăng nhập…" : "Đăng nhập"}
              </Button>
            </form>
            <div className="mt-5 flex gap-3 border-t pt-4 text-xs leading-5 text-muted-foreground">
              <ShieldCheck
                className="mt-0.5 size-4 shrink-0 text-primary"
                aria-hidden="true"
              />
              <p>
                Đây là lớp hỗ trợ quyết định. Quản lý và kỹ thuật viên vẫn chịu
                trách nhiệm cho kiểm tra an toàn và quyết định cuối cùng.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
