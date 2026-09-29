"""Publish active NL Workflows to the Desk client.

Frappe's Desk decides whether to render workflow indicators, workflow state
columns, workflow aware submit/cancel buttons and bulk workflow actions from the
client side registries `frappe.workflow.workflows`, `frappe.workflow.state_fields`,
`frappe.workflow.avoid_status_override` and `frappe.model.has_workflow()`.
Those registries are filled from native `Workflow` documents only, so DocTypes
governed by an `NL Workflow` are invisible to the Desk.

This module ships the equivalent metadata over `bootinfo` so that
`public/js/nl_workflow_registry.js` can register NL Workflows in the same client
structures. Document specific resolution (company, user, project, cost center
and accounting dimensions) stays server side in
`frappe_workflow_extension.workflow.get_workflow_name`, so the payload only has
to be complete enough for the Desk to recognise the states a document may be in.
"""

from __future__ import annotations

import frappe

WORKFLOW_FIELDS = ("name", "document_type", "workflow_state_field", "override_status")
STATE_FIELDS = (
	"state",
	"doc_status",
	"allow_edit",
	"edit_permission_type",
	"avoid_status_override",
	"update_field",
)
TRANSITION_FIELDS = (
	"state",
	"action",
	"next_state",
	"allowed",
	"approver_type",
	"allow_self_approval",
	"require_comment",
)
SCOPING_FIELDS = ("company", "user", "project", "cost_center")
"""Scoping fields are not published: the Desk cannot resolve them, the workflow
that applies to a document is decided server side."""


def boot_session(bootinfo) -> None:
	"""`boot_session` hook: expose active NL Workflows to the Desk.

	Args:
	    bootinfo: Boot info dictionary that is sent to the browser.
	"""
	if frappe.session.user == "Guest":
		return

	workflows = get_active_workflows()
	if not workflows:
		return

	bootinfo.nl_workflows = {
		"by_doctype": group_by_doctype(workflows),
		"workflow_states": get_workflow_state_docs(workflows),
	}


def get_active_workflows() -> list[dict]:
	"""Return active NL Workflows including their states and transitions.

	Reads deliberately ignore user permissions on `NL Workflow`: the Desk has to
	know the workflow of every document it renders, exactly like native
	`Workflow` metadata which is shipped to every user as well.

	Returns:
	    One dictionary per workflow with `states` and `transitions` attached.
	"""
	workflows = frappe.get_all(
		"NL Workflow",
		filters={"is_active": 1},
		fields=list(WORKFLOW_FIELDS),
		order_by="creation asc",
		limit_page_length=0,
	)
	if not workflows:
		return []

	parents = [workflow["name"] for workflow in workflows]
	states = get_children("NL Workflow Document State", parents, STATE_FIELDS)
	transitions = get_children("NL Workflow Transition", parents, TRANSITION_FIELDS)

	for workflow in workflows:
		workflow["states"] = states.get(workflow["name"], [])
		workflow["transitions"] = transitions.get(workflow["name"], [])

	return workflows


def get_children(doctype: str, parents: list[str], fields: tuple) -> dict[str, list[dict]]:
	"""Return child table rows grouped by parent workflow name.

	Args:
	    doctype: Child DocType to read, e.g. `NL Workflow Transition`.
	    parents: Names of the parent `NL Workflow` documents.
	    fields: Fields to select from the child DocType.

	Returns:
	    Mapping of parent name to the ordered list of child rows.
	"""
	rows = frappe.get_all(
		doctype,
		filters={"parent": ["in", parents], "parenttype": "NL Workflow"},
		fields=["parent", *fields],
		order_by="idx asc",
		limit_page_length=0,
	)

	grouped: dict[str, list[dict]] = {}
	for row in rows:
		grouped.setdefault(row.pop("parent"), []).append(row)

	return grouped


def group_by_doctype(workflows: list[dict]) -> dict[str, dict]:
	"""Map each DocType to the single workflow definition the Desk understands.

	Args:
	    workflows: Active workflows with their states and transitions attached.

	Returns:
	    Mapping of `document_type` to a merged workflow definition.
	"""
	grouped: dict[str, list[dict]] = {}
	for workflow in workflows:
		grouped.setdefault(workflow["document_type"], []).append(workflow)

	return {doctype: merge_workflows(items) for doctype, items in grouped.items()}


def merge_workflows(workflows: list[dict]) -> dict:
	"""Merge the workflows of one DocType into a single client side definition.

	A DocType may have several NL Workflows (one per company, user, project,
	cost center or accounting dimension). The Desk only understands one, so the
	least specific workflow provides the workflow level fields while the states
	and transitions of all workflows are merged, letting the Desk resolve the
	state of documents governed by any of them. The transitions that apply to a
	single document remain resolved server side.

	Args:
	    workflows: Workflows of a single DocType, in configuration order.

	Returns:
	    Dictionary with `name`, `document_type`, `workflow_state_field`,
	    `override_status`, `states` and `transitions`.
	"""
	base = pick_base_workflow(workflows)
	merged = {
		"name": base["name"],
		"document_type": base["document_type"],
		"workflow_state_field": base["workflow_state_field"],
		"override_status": base["override_status"],
		"states": [],
		"transitions": [],
	}

	for workflow in [base, *(item for item in workflows if item is not base)]:
		for state in workflow["states"]:
			add_unique(merged["states"], state, "state")
		for transition in workflow["transitions"]:
			add_unique(
				merged["transitions"],
				transition,
				("state", "action", "next_state", "allowed"),
			)

	return merged


def pick_base_workflow(workflows: list[dict]) -> dict:
	"""Return the least specific workflow of a DocType.

	Args:
	    workflows: Workflows of a single DocType, in configuration order.

	Returns:
	    The first globally scoped workflow, or the first configured workflow.
	"""
	return next((workflow for workflow in workflows if is_global_workflow(workflow)), workflows[0])


def add_unique(rows: list[dict], row: dict, key: str | tuple) -> None:
	"""Append `row` to `rows` unless an equivalent row is already present.

	Args:
	    rows: Accumulated rows.
	    row: Row to add.
	    key: Field name or tuple of field names identifying a row uniquely.
	"""
	fields = (key,) if isinstance(key, str) else key
	if any(all(existing.get(field) == row.get(field) for field in fields) for existing in rows):
		return

	rows.append(row)


def is_global_workflow(workflow: dict) -> bool:
	"""Return True when the workflow applies to every document of its DocType.

	Args:
	    workflow: Workflow dictionary as built by `get_active_workflows`.

	Returns:
	    True when no company, user, project, cost center or descendant scoping
	    is configured.
	"""
	if workflow.get("allow_descendants"):
		return False

	return not any(workflow.get(field) for field in SCOPING_FIELDS)


def get_workflow_state_docs(workflows: list[dict]) -> list[dict]:
	"""Return the `Workflow State` records referenced by NL Workflow states.

	The Desk colours workflow indicators from `locals["Workflow State"]`
	(`frappe.get_indicator`), which is normally seeded by the `__workflow_docs`
	of the form meta. Publishing these records keeps NL Workflow indicators
	visually identical to native ones.

	Args:
	    workflows: Active workflows with their states attached.

	Returns:
	    `Workflow State` documents ready for `frappe.model.sync`.
	"""
	names = sorted(
		{state["state"] for workflow in workflows for state in workflow["states"] if state.get("state")}
	)
	if not names:
		return []

	return [
		{"doctype": "Workflow State", **state}
		for state in frappe.get_all(
			"Workflow State",
			filters={"name": ["in", names]},
			fields=["name", "workflow_state_name", "style", "icon"],
			limit_page_length=0,
		)
	]
