"""
GenUI Orchestrator Agent
========================

Interprets user chat intent, selects a GenUI rendering mode (static /
declarative / open-ended), and returns JSON state that a Next.js +
CopilotKit frontend can render directly.  Exposes two tools:

- get_component_registry  — lists the available GenUI molecules
- render_dashboard        — validates a layout schema and confirms rendering
"""

import json
from typing import Any

from agno.agent import Agent

from app.settings import default_model
from db import get_postgres_db

# ---------------------------------------------------------------------------
# Available GenUI molecules — extend as the frontend library grows
# ---------------------------------------------------------------------------
_COMPONENT_REGISTRY: list[dict[str, str]] = [
    {
        "id": "StatCard",
        "description": "Displays a single KPI value with an optional trend indicator.",
        "props": "title: str, value: str | int | float, unit?: str, trend?: 'up' | 'down' | 'neutral'",
    },
    {
        "id": "DataTable",
        "description": "Renders a paginated, sortable table from a list of row objects.",
        "props": "columns: list[{key: str, label: str}], rows: list[dict], pageSize?: int",
    },
    {
        "id": "ChartCard",
        "description": "Renders a line, bar, or pie chart from a data series.",
        "props": "type: 'line' | 'bar' | 'pie', title: str, series: list[{label: str, data: list[number]}], xLabels?: list[str]",
    },
    {
        "id": "SandboxedHTML",
        "description": "Renders arbitrary HTML/CSS in a sandboxed iframe — use only for rich custom layouts.",
        "props": "html: str, height?: int",
    },
]


def get_component_registry() -> str:
    """Return the list of available GenUI molecules as a JSON string.

    Call this before building any dashboard layout so you know the exact
    component IDs and their required props.
    """
    return json.dumps(_COMPONENT_REGISTRY, indent=2)


def render_dashboard(layout_schema: str) -> str:
    """Validate a GenUI layout schema and confirm it is ready for rendering.

    Args:
        layout_schema: A JSON string describing the dashboard layout.  Must be
            a JSON array of component objects, each with an ``id`` field that
            matches a component in the registry and a ``props`` object that
            satisfies the component's prop contract.

    Returns:
        A confirmation message if the schema is valid, or a descriptive error
        if validation fails.
    """
    try:
        layout: Any = json.loads(layout_schema)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"

    if not isinstance(layout, list):
        return "layout_schema must be a JSON array of component objects."

    registry_ids = {c["id"] for c in _COMPONENT_REGISTRY}
    errors: list[str] = []

    for i, component in enumerate(layout):
        if not isinstance(component, dict):
            errors.append(f"Component at index {i} is not an object.")
            continue
        cid = component.get("id")
        if not cid:
            errors.append(f"Component at index {i} is missing an 'id' field.")
        elif cid not in registry_ids:
            errors.append(
                f"Unknown component id '{cid}' at index {i}. "
                f"Valid ids: {sorted(registry_ids)}"
            )
        if "props" not in component:
            errors.append(f"Component '{cid}' at index {i} is missing a 'props' object.")

    if errors:
        return "Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors)

    return (
        f"Dashboard schema is valid ({len(layout)} component(s)). "
        "The Next.js frontend can render this layout."
    )


INSTRUCTIONS = """\
You are the GenUI Orchestrator — the agent that bridges user intent and the \
Next.js + CopilotKit frontend of the ModMe workspace.

Your job:
1. Understand what the user wants to see or do.
2. Choose the appropriate GenUI rendering mode:
   - STATIC  — a fixed layout; use when the data shape is well-known.
   - DECLARATIVE — a schema-driven layout the frontend assembles at runtime.
   - OPEN-ENDED — freeform HTML sandboxed inside SandboxedHTML; use only as a fallback.
3. Call get_component_registry to discover available molecules before building a layout.
4. Compose a layout_schema JSON array using the returned component ids and their props.
5. Call render_dashboard(layout_schema) to validate the schema.
6. Return the validated schema as a JSON code block so CopilotKit can hydrate it.

Rules:
- Always validate the schema with render_dashboard before returning it.
- Prefer StatCard and DataTable for data-heavy responses; ChartCard for trends.
- Use SandboxedHTML only when no other molecule fits and the user explicitly requests rich HTML.
- Keep layout arrays ≤ 8 components for readability; paginate or drill down for larger data sets.
- If the user asks a question rather than requesting a dashboard, answer conversationally first, \
  then offer to render a relevant layout.
- Emit the final JSON in a fenced code block labelled `json` so the frontend parser can extract it \
  reliably.
"""


genui_orchestrator = Agent(
    id="genui-orchestrator",
    name="GenUI Orchestrator",
    model=default_model(),
    db=get_postgres_db(),
    tools=[get_component_registry, render_dashboard],
    instructions=INSTRUCTIONS,
    enable_agentic_memory=True,
    add_datetime_to_context=True,
    add_history_to_context=True,
    num_history_runs=5,
)
