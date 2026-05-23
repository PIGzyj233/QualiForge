type SubTab = {
  key: string;
  label: string;
};

type SubTabsProps = {
  tabs: SubTab[];
  active: string;
  onChange: (key: string) => void;
};

export function SubTabs({ tabs, active, onChange }: SubTabsProps) {
  return (
    <div className="sub-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          className={active === tab.key ? "sub-tab active" : "sub-tab"}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
