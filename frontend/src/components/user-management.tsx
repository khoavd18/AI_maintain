"use client";

import { Loader2, Save, UserPlus } from "lucide-react";
import { useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useCreateUser, useUpdateUser } from "@/hooks/use-api-mutations";
import { useRoleOptionsQuery, useUsersQuery } from "@/hooks/use-api-queries";
import { permissions } from "@/lib/auth";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { RoleCode, RoleOption, UserResponse } from "@/lib/api/schemas";
import { formatTimestamp } from "@/lib/formatters";

export function UserManagement() {
  const auth = useAuth();
  const users = useUsersQuery();
  const roles = useRoleOptionsQuery();
  const canCreate = auth.can(permissions.usersCreate);

  if (users.isPending || roles.isPending) return <LoadingSkeleton />;
  const failed = users.isError ? users : roles.isError ? roles : null;
  if (failed) {
    return (
      <ErrorState
        title="Chưa tải được người dùng"
        description={getApiErrorMessage(failed.error)}
        action={<RetryButton onClick={() => void Promise.all([users.refetch(), roles.refetch()])} />}
      />
    );
  }
  if (!users.data || !roles.data) return <LoadingSkeleton />;

  return (
    <div className="space-y-5">
      {canCreate ? (
        <CreateUserForm roles={roles.data} />
      ) : (
        <PermissionDeniedNotice message="Bạn có thể xem nhưng không có quyền tạo người dùng." />
      )}
      <div className="overflow-hidden rounded-lg border bg-white">
        <div className="lg:overflow-x-auto">
          <Table className="block lg:table">
            <TableHeader className="hidden lg:table-header-group">
              <TableRow>
                <TableHead>Người dùng</TableHead>
                <TableHead>Vai trò</TableHead>
                <TableHead>Mã kỹ thuật viên</TableHead>
                <TableHead>Trạng thái</TableHead>
                <TableHead>Lần đăng nhập cuối</TableHead>
                <TableHead className="text-right">Thao tác</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="block space-y-3 p-3 lg:table-row-group lg:space-y-0 lg:p-0">
              {users.data.map((user) => (
                <UserRow key={user.id} user={user} roles={roles.data} />
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

function CreateUserForm({ roles }: { roles: RoleOption[] }) {
  const mutation = useCreateUser();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<RoleCode>("helpdesk");
  const [technicianId, setTechnicianId] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        username,
        display_name: displayName,
        email: email.trim() || null,
        password,
        role,
        technician_id: role === "technician" ? technicianId : null,
        is_active: true,
      });
      setUsername("");
      setDisplayName("");
      setEmail("");
      setPassword("");
      setTechnicianId("");
    } catch {
      // Mutation state renders the API error next to the form.
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Tạo người dùng nội bộ</CardTitle></CardHeader>
      <CardContent>
        <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" onSubmit={(event) => void submit(event)}>
          <Field label="Tên đăng nhập"><Input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} /></Field>
          <Field label="Tên hiển thị"><Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required minLength={2} /></Field>
          <Field label="Email (tùy chọn)"><Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></Field>
          <Field label="Mật khẩu ban đầu"><Input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} /></Field>
          <Field label="Vai trò">
            <Select value={role} onValueChange={(value) => setRole(value as RoleCode)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{roles.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          {role === "technician" && <Field label="Mã kỹ thuật viên"><Input value={technicianId} onChange={(event) => setTechnicianId(event.target.value)} required /></Field>}
          <div className="flex items-end">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <UserPlus aria-hidden="true" />}
              Tạo người dùng
            </Button>
          </div>
        </form>
        {mutation.isError && <InlineError error={mutation.error} />}
        {mutation.isSuccess && <p role="status" className="mt-3 text-sm font-medium text-green-700">Đã tạo {mutation.data.username}. Mật khẩu không được hiển thị lại.</p>}
      </CardContent>
    </Card>
  );
}

function UserRow({ user, roles }: { user: UserResponse; roles: RoleOption[] }) {
  const auth = useAuth();
  const mutation = useUpdateUser(user.id);
  const [role, setRole] = useState<RoleCode>(user.role);
  const [active, setActive] = useState(user.is_active);
  const [technicianId, setTechnicianId] = useState(user.technician_id ?? "");
  const canUpdate = auth.can(permissions.usersUpdate);

  return (
    <TableRow className="grid grid-cols-2 gap-4 rounded-lg border bg-card p-4 shadow-sm lg:table-row lg:rounded-none lg:border-x-0 lg:border-t-0 lg:bg-transparent lg:p-0 lg:shadow-none">
      <TableCell className="col-span-2 block whitespace-normal p-0 lg:table-cell lg:p-2 lg:whitespace-nowrap"><p className="font-medium">{user.display_name}</p><p className="text-xs text-muted-foreground">{user.username}{user.email ? ` · ${user.email}` : ""}</p></TableCell>
      <TableCell className="col-span-2 block whitespace-normal p-0 sm:col-span-1 lg:table-cell lg:p-2 lg:whitespace-nowrap">
        <MobileFieldLabel>Vai trò</MobileFieldLabel>
        <Select value={role} onValueChange={(value) => setRole(value as RoleCode)} disabled={!canUpdate}>
          <SelectTrigger className="w-full lg:w-44"><SelectValue /></SelectTrigger>
          <SelectContent>{roles.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent>
        </Select>
      </TableCell>
      <TableCell className="col-span-2 block whitespace-normal p-0 sm:col-span-1 lg:table-cell lg:p-2 lg:whitespace-nowrap">
        <MobileFieldLabel>Mã kỹ thuật viên</MobileFieldLabel>
        <Input className="w-full lg:w-32" value={technicianId} onChange={(event) => setTechnicianId(event.target.value)} disabled={!canUpdate || role !== "technician"} placeholder="Không áp dụng" />
      </TableCell>
      <TableCell className="block whitespace-normal p-0 lg:table-cell lg:p-2 lg:whitespace-nowrap">
        <MobileFieldLabel>Trạng thái</MobileFieldLabel>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} disabled={!canUpdate || user.id === auth.user?.id} /><Badge variant={active ? "outline" : "secondary"}>{active ? "Đang hoạt động" : "Đã vô hiệu"}</Badge></label>
      </TableCell>
      <TableCell className="block whitespace-normal p-0 text-xs text-muted-foreground lg:table-cell lg:p-2 lg:whitespace-nowrap">
        <MobileFieldLabel>Lần đăng nhập cuối</MobileFieldLabel>
        {user.last_login_at ? formatTimestamp(user.last_login_at) : "Chưa đăng nhập"}
      </TableCell>
      <TableCell className="col-span-2 block whitespace-normal p-0 text-right lg:table-cell lg:p-2 lg:whitespace-nowrap">
        <Button className="w-full lg:w-auto" type="button" variant="outline" size="sm" disabled={!canUpdate || mutation.isPending} onClick={() => mutation.mutate({ role, is_active: active, technician_id: role === "technician" ? technicianId : null })}>
          {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}Lưu
        </Button>
        {mutation.isError && <p className="mt-1 text-xs text-red-700 lg:max-w-48">{getApiErrorMessage(mutation.error)}</p>}
      </TableCell>
    </TableRow>
  );
}

function MobileFieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted-foreground lg:hidden">
      {children}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}

function InlineError({ error }: { error: unknown }) {
  return <p role="alert" className="mt-3 text-sm font-medium text-red-700">{getApiErrorMessage(error)}</p>;
}
