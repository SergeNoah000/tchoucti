import { Users } from "lucide-react";
import { cn } from "@/lib/utils";

interface BrandMarkProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  /**
   * "brand" → fixed teal (landing, login — neutral marketing surfaces).
   * "primary" → follows the shell role primary color, so the logo recolours
   * per role (admin = violet, groupement = sky, association = emerald, member = teal).
   */
  variant?: "brand" | "primary";
  className?: string;
}

const sizes = {
  sm: { box: "h-8 w-8", icon: "h-4 w-4", text: "text-base" },
  md: { box: "h-10 w-10", icon: "h-5 w-5", text: "text-lg" },
  lg: { box: "h-12 w-12", icon: "h-6 w-6", text: "text-2xl" },
};

export function BrandMark({ size = "md", showText = true, variant = "brand", className }: BrandMarkProps) {
  const s = sizes[size];
  const isPrimary = variant === "primary";

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className={cn(
          "flex items-center justify-center rounded-xl shadow-sm",
          isPrimary
            ? "bg-gradient-to-br from-primary to-primary/70 shadow-primary/20"
            : "bg-gradient-to-br from-brand-500 to-brand-700 shadow-brand-500/20",
          s.box
        )}
      >
        <Users className={cn("text-primary-foreground", s.icon)} strokeWidth={2.5} />
      </div>
      {showText && (
        <span
          className={cn(
            "font-bold tracking-tight",
            isPrimary ? "text-gradient-primary" : "text-gradient-brand",
            s.text
          )}
        >
          Tchoucti
        </span>
      )}
    </div>
  );
}
