import { type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  trend?: { value: string; positive?: boolean };
  accent?: "brand" | "emerald" | "amber" | "sky" | "rose";
  className?: string;
}

const accents = {
  brand: "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300",
  emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  amber: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  sky: "bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  rose: "bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

export function StatCard({ label, value, icon: Icon, trend, accent = "brand", className }: StatCardProps) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardContent className="flex items-center gap-4 p-5">
        {Icon && (
          <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-xl", accents[accent])}>
            <Icon className="h-5 w-5" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-0.5 truncate text-2xl font-semibold text-foreground">{value}</p>
          {trend && (
            <p
              className={cn(
                "mt-1 text-xs font-medium",
                trend.positive ? "text-emerald-600" : "text-rose-600"
              )}
            >
              {trend.value}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
