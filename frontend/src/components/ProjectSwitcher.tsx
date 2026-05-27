import { ChevronDown } from "lucide-react";
import { ProjectRecord } from "../api/workspace";

export function ProjectSwitcher({
  projects,
  currentProjectId,
  busy,
  onSwitch
}: {
  projects: ProjectRecord[];
  currentProjectId: string;
  busy: boolean;
  onSwitch: (projectId: string) => void;
}) {
  return (
    <label className="switcher-select">
      <span className="eyebrow">Project</span>
      <div className="switcher-row">
        <select
          value={currentProjectId}
          onChange={(event) => onSwitch(event.target.value)}
          disabled={busy || projects.length === 0}
        >
          {projects.length === 0 ? <option value="">无项目</option> : null}
          {projects.map((project) => (
            <option value={project.id} key={project.id}>
              {project.key} · {project.name}
            </option>
          ))}
        </select>
        <ChevronDown size={14} aria-hidden="true" />
      </div>
    </label>
  );
}
