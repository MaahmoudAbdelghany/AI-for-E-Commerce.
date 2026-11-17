import { AppShell } from "@/components/shell/AppShell";
import { ShoppingWorkspace } from "@/components/workspace/ShoppingWorkspace";

export default function HomePage() {
  return (
    <AppShell>
      <ShoppingWorkspace />
    </AppShell>
  );
}
