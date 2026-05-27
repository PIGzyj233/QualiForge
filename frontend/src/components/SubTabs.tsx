import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type SubTab = { key: string; label: string };

export function SubTabs({ tabs, active, onChange }: { tabs: SubTab[]; active: string; onChange: (key: string) => void }) {
  return (
    <Tabs value={active} onValueChange={onChange}>
      <TabsList>
        {tabs.map((tab) => <TabsTrigger key={tab.key} value={tab.key}>{tab.label}</TabsTrigger>)}
      </TabsList>
    </Tabs>
  );
}
