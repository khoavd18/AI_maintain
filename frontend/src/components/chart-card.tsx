import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface ChartCardProps {
  title: string;
  description?: string;
  summary: string;
  children: React.ReactNode;
  className?: string;
}

export function ChartCard({ title, description, summary, children, className }: ChartCardProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {children}
        <p className="mt-3 border-t pt-3 text-xs leading-5 text-muted-foreground">{summary}</p>
      </CardContent>
    </Card>
  );
}
