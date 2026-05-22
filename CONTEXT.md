# QualiForge Context

QualiForge is an AI-native test asset platform for small to mid-sized engineering and QA teams.

The product helps teams turn messy historical test cases, GitLab repository context, tag diffs, review workflows, test plan execution, and release reports into a structured knowledge base that both humans and AI agents can use.

Core domain concepts:

- `Workspace`: the top-level team or personal working area.
- `Project`: a product or system under test inside a workspace.
- `Repository`: a GitLab repository connected to a project.
- `Git Sandbox`: the controlled local clone/mirror and temporary worktree area used for read-only analysis.
- `Module` or `FeatureArea`: the team's human-friendly grouping of product functionality.
- `ModuleMapping`: rules that connect modules to code paths, services, API routes, configuration keys, or keywords.
- `TestCase`: the current canonical test case object, including status and content.
- `CaseRevision`: a historical snapshot of a test case.
- `Review`: the process and record for approving, rejecting, or requesting changes to a test case.
- `DiffAnalysis`: analysis of a repository diff, usually `baseTag -> targetTag`, including impacted modules and test recommendations.
- `AICaseCandidate`: an AI-generated or AI-normalized candidate test case that must be reviewed before becoming official.
- `TestPlan`: a scoped plan for release, regression, smoke, feature, or custom testing.
- `PlanItem`: a concrete executable item in a test plan, using a snapshot of a formal test case, an AI suggestion, or a manual temporary item.
- `Job`: a background task for Git sync, import parsing, AI normalization, diff analysis, case generation, report drafting, or export.
- `Report`: a human-confirmed test report for team release decisions.

Important product principles:

- AI can suggest, normalize, summarize, and draft, but cannot bypass human review for official test assets.
- AI-generated case candidates can be executed as temporary plan items, but must pass review before entering the formal case library.
- Git repository analysis is read-only in the MVP. The platform must not run project code, start services, execute arbitrary commands, or access business databases.
- Black-box testers should not be required to know code paths. Technical associations are inferred by the system and can be confirmed or corrected by humans.
- MVP deployment is private/self-hosted first, with Docker Compose as the initial deployment shape.
- The UI should feel like a quiet, dense workbench for test and release decisions, not a marketing site or AI chat demo.

Primary reference docs:

- `docs/mvp-prd.md`: MVP product requirements.
- `docs/future-roadmap.md`: deferred and future capabilities.
- `docs/adr/`: architectural decision records.

