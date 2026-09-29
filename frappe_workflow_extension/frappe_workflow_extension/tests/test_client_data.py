"""Tests for the Desk bootinfo payload assembled by `client_data`.

The payload has to be complete enough for the Desk to recognise every workflow
state of a DocType while a single document may still be governed by a different
NL Workflow instance (per company, user, project, cost center or dimension).
Only the pure helpers are covered here; reading the workflows is exercised by
`boot_session` at runtime.
"""

from frappe.tests import UnitTestCase

from frappe_workflow_extension.frappe_workflow_extension.client_data import (
	add_unique,
	group_by_doctype,
	is_global_workflow,
	merge_workflows,
	pick_base_workflow,
)


def make_state(state: str, **overrides) -> dict:
	"""Return an `NL Workflow Document State` row as published to the Desk."""
	return {
		"state": state,
		"doc_status": "0",
		"allow_edit": "All",
		"edit_permission_type": None,
		"avoid_status_override": 0,
		"update_field": None,
		**overrides,
	}


def make_transition(state: str, action: str, next_state: str, **overrides) -> dict:
	"""Return an `NL Workflow Transition` row as published to the Desk."""
	return {
		"state": state,
		"action": action,
		"next_state": next_state,
		"allowed": "All",
		"approver_type": "Role",
		"allow_self_approval": 0,
		"require_comment": 0,
		**overrides,
	}


def make_workflow(name: str, **overrides) -> dict:
	"""Return an `NL Workflow` dictionary as built by `get_active_workflows`."""
	return {
		"name": name,
		"document_type": "Journal Entry",
		"workflow_state_field": "workflow_state",
		"override_status": 0,
		"states": [],
		"transitions": [],
		**overrides,
	}


class TestNLWorkflowClientData(UnitTestCase):
	"""Cover the merge rules that hide scoping from the Desk."""

	def test_is_global_workflow(self):
		"""Only workflows without scoping are global."""
		self.assertTrue(is_global_workflow(make_workflow("All Companies")))
		self.assertFalse(is_global_workflow(make_workflow("ACME", company="ACME")))
		self.assertFalse(is_global_workflow(make_workflow("Me", user="a@b.c")))
		self.assertFalse(is_global_workflow(make_workflow("Proj", project="P-1")))
		self.assertFalse(is_global_workflow(make_workflow("CC", cost_center="Main")))
		self.assertFalse(is_global_workflow(make_workflow("Tree", allow_descendants=1)))

	def test_pick_base_workflow_prefers_least_specific(self):
		"""The first globally scoped workflow wins, whatever its position."""
		scoped = make_workflow("ACME", company="ACME")
		global_workflow = make_workflow("All Companies")

		self.assertIs(pick_base_workflow([scoped, global_workflow]), global_workflow)
		self.assertIs(pick_base_workflow([scoped]), scoped)

	def test_add_unique_uses_composite_key(self):
		"""Rows are deduplicated on the configured key only."""
		rows = [make_transition("Draft", "Approve", "Approved", allowed="Role A")]

		add_unique(rows, dict(rows[0]), ("state", "action", "next_state", "allowed"))
		self.assertEqual(len(rows), 1)

		add_unique(
			rows,
			make_transition("Draft", "Approve", "Approved", allowed="Role B"),
			("state", "action", "next_state", "allowed"),
		)
		self.assertEqual([row["allowed"] for row in rows], ["Role A", "Role B"])

	def test_merge_workflows_takes_base_fields_and_unions_rows(self):
		"""Scoped workflows add rows without redefining workflow level fields."""
		global_workflow = make_workflow(
			"All Companies",
			states=[make_state("Draft"), make_state("Approved", doc_status="1")],
			transitions=[make_transition("Draft", "Approve", "Approved")],
		)
		scoped = make_workflow(
			"ACME",
			company="ACME",
			workflow_state_field="acme_state",
			override_status=1,
			states=[make_state("Draft"), make_state("Rejected")],
			transitions=[
				make_transition("Draft", "Reject", "Rejected"),
				make_transition("Draft", "Approve", "Approved", allowed="ACME Approver"),
			],
		)

		merged = merge_workflows([scoped, global_workflow])

		self.assertEqual(merged["name"], "All Companies")
		self.assertEqual(merged["workflow_state_field"], "workflow_state")
		self.assertEqual(merged["override_status"], 0)
		self.assertEqual(
			[state["state"] for state in merged["states"]],
			["Draft", "Approved", "Rejected"],
		)
		self.assertEqual(
			[(row["action"], row["allowed"]) for row in merged["transitions"]],
			[("Approve", "All"), ("Reject", "All"), ("Approve", "ACME Approver")],
		)

	def test_merge_workflows_state_rows_keep_least_specific_definition(self):
		"""A state configured twice is published once, from the base workflow.

		Read only handling for the document still resolves server side, so the
		base definition only decides how the Desk renders the state.
		"""
		global_workflow = make_workflow("All Companies", states=[make_state("Draft", allow_edit="All")])
		scoped = make_workflow(
			"ACME",
			company="ACME",
			states=[make_state("Draft", allow_edit="ACME Manager")],
		)

		merged = merge_workflows([scoped, global_workflow])

		self.assertEqual(len(merged["states"]), 1)
		self.assertEqual(merged["states"][0]["allow_edit"], "All")

	def test_group_by_doctype(self):
		"""Workflows are grouped per DocType and merged within the group."""
		grouped = group_by_doctype(
			[
				make_workflow("JE All", states=[make_state("Draft")]),
				make_workflow("JE ACME", company="ACME", states=[make_state("Approved")]),
				make_workflow("SO All", document_type="Sales Order"),
			]
		)

		self.assertEqual(sorted(grouped), ["Journal Entry", "Sales Order"])
		self.assertEqual(
			[state["state"] for state in grouped["Journal Entry"]["states"]],
			["Draft", "Approved"],
		)
		self.assertEqual(grouped["Sales Order"]["name"], "SO All")
