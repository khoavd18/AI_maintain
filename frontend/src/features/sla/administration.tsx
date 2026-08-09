"use client";

import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useBusinessCalendarsQuery,
  useSlaPoliciesQuery,
  useTicketingOptionsQuery,
} from "@/hooks/use-ticketing";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { BusinessCalendar, SlaPolicy } from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";

import { CalendarList } from "./components/calendar-list";
import { PolicyList } from "./components/policy-list";
import { BusinessCalendarForm } from "./forms/business-calendar-form";
import { SlaPolicyForm } from "./forms/sla-policy-form";
import { ReadOnlyNotice } from "./components/form-controls";

export function SlaAdministration() {
  const auth = useAuth();
  const canManage = auth.can(permissions.slaPoliciesManage);
  const calendars = useBusinessCalendarsQuery();
  const policies = useSlaPoliciesQuery();
  const options = useTicketingOptionsQuery();
  const [calendarEdit, setCalendarEdit] = useState<BusinessCalendar | null>(null);
  const [policyEdit, setPolicyEdit] = useState<SlaPolicy | null>(null);

  if (calendars.isPending || policies.isPending || options.isPending) {
    return <LoadingSkeleton />;
  }
  if (calendars.isError || policies.isError || options.isError) {
    return (
      <ErrorState
        title="Chưa tải được cấu hình SLA"
        description={getApiErrorMessage(calendars.error ?? policies.error ?? options.error)}
        action={
          <RetryButton
            onClick={() => {
              void calendars.refetch();
              void policies.refetch();
              void options.refetch();
            }}
          />
        }
      />
    );
  }

  return (
    <Tabs defaultValue="policies">
      <TabsList>
        <TabsTrigger value="policies">SLA policies</TabsTrigger>
        <TabsTrigger value="calendars">Business calendars</TabsTrigger>
      </TabsList>

      <TabsContent value="policies" className="mt-4">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
          <PolicyList
            policies={policies.data}
            canManage={canManage}
            onNew={() => setPolicyEdit(null)}
            onEdit={setPolicyEdit}
          />
          {canManage ? (
            <SlaPolicyForm
              key={policyEdit?.id ?? "new-policy"}
              initial={policyEdit}
              calendars={calendars.data}
              categories={options.data.categories}
              onSaved={() => setPolicyEdit(null)}
            />
          ) : (
            <ReadOnlyNotice />
          )}
        </div>
      </TabsContent>

      <TabsContent value="calendars" className="mt-4">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
          <CalendarList
            calendars={calendars.data}
            canManage={canManage}
            onNew={() => setCalendarEdit(null)}
            onEdit={setCalendarEdit}
          />
          {canManage ? (
            <BusinessCalendarForm
              key={calendarEdit?.id ?? "new-calendar"}
              initial={calendarEdit}
              onSaved={() => setCalendarEdit(null)}
            />
          ) : (
            <ReadOnlyNotice />
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
