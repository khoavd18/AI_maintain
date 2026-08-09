"use client";

import Link from "next/link";
import { ShieldX } from "lucide-react";

import { defaultRouteFor, useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";

export default function ForbiddenPage() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-xl rounded-lg border bg-white p-8 text-center">
      <ShieldX className="mx-auto size-10 text-amber-600" aria-hidden="true" />
      <h1 className="mt-4 text-xl font-semibold">Không có quyền truy cập</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Vai trò hiện tại không được phép mở trang hoặc thực hiện thao tác này. Hãy quay lại
        khu vực công việc của bạn hoặc liên hệ quản trị viên nếu cần hỗ trợ.
      </p>
      <Button asChild className="mt-5">
        <Link href={user ? defaultRouteFor(user) : "/login"}>Về khu vực được phép</Link>
      </Button>
    </div>
  );
}
