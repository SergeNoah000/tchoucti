import { Shell } from "@/components/layout/shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <Shell forceRole="super_admin" homeHref="/admin">
      {children}
    </Shell>
  );
}
