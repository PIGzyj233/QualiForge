import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-[var(--radius-sm)] border px-4 py-3 text-sm flex items-start gap-3",
  {
    variants: {
      variant: {
        default: "bg-[var(--card)] text-[var(--foreground)]",
        destructive: "border-[var(--destructive)]/30 bg-[var(--destructive)]/10 text-[var(--destructive)]",
        warning: "border-amber-300/30 bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-400",
        success: "border-green-300/30 bg-green-50 text-green-800 dark:bg-green-900/20 dark:text-green-400"
      }
    },
    defaultVariants: { variant: "default" }
  }
);

const Alert = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
  )
);
Alert.displayName = "Alert";

const AlertDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm leading-relaxed", className)} {...props} />
  )
);
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertDescription };
