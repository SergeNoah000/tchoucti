import { type LucideIcon, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface ComingSoonProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  sprintLabel?: string;
  className?: string;
}

/**
 * Soft 404 — a minimal placeholder for routes whose feature has not landed yet.
 * Kept deliberately quiet (no fake stats) per UX call.
 */
export function ComingSoon({ icon: Icon, title, description, sprintLabel, className }: ComingSoonProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-24 px-4", className)}>
      {Icon ? (
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
          <Icon className="h-8 w-8" />
        </div>
      ) : (
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
          <Sparkles className="h-8 w-8" />
        </div>
      )}
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      {description && (
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {sprintLabel && (
        <Badge variant="brand" className="mt-5 gap-1.5 px-3 py-1">
          <Sparkles className="h-3.5 w-3.5" />
          {sprintLabel}
        </Badge>
      )}
    </div>
  );
}
