import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface DataTableShellProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function DataTableShell({ title, description, actions, children, className }: DataTableShellProps) {
  return (
    <Card className={className}>
      <CardHeader className="border-b sm:grid-cols-[1fr_auto]">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {actions && <div className="mt-3 sm:mt-0">{actions}</div>}
      </CardHeader>
      <CardContent className="px-0">{children}</CardContent>
    </Card>
  );
}
