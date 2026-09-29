"""Tests for resolving the workflow of documents that are not stored yet.

Saving a new document runs the `validate` hook before the row is written, while
the document already carries the name handed out by its naming series. Resolving
the scoped workflow has to work from the in-memory document in that case: reading
it back by name raises a 404 and makes every insert of a governed DocType fail.
"""

from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from frappe_workflow_extension.frappe_workflow_extension import compat
from frappe_workflow_extension.frappe_workflow_extension import workflow as nl_workflow

COMPANY = "Workflow Scope Test Company"
WORKFLOW = "Workflow Scope Test Workflow"
UNSAVED_NAME = "ACC-JV-UNSAVED"


def get_all_workflows(doctype, **kwargs):
	"""Return one workflow scoped to COMPANY for NL Workflow reads."""
	if doctype != "NL Workflow":
		return []

	return [
		frappe._dict(
			name=WORKFLOW,
			company=COMPANY,
			project=None,
			cost_center=None,
			allow_descendants=0,
			user=None,
		)
	]


class TestWorkflowDocumentScope(UnitTestCase):
	"""Cover workflow resolution for unsaved documents."""

	def test_unsaved_document_is_not_read_back_by_name(self):
		"""The scope comes from the passed document, not from a database read."""
		doc = frappe._dict(doctype="Journal Entry", name=UNSAVED_NAME, company=COMPANY)
		get_doc = Mock(side_effect=AssertionError("the document must not be read back"))

		with (
			patch.object(nl_workflow.frappe, "get_all", side_effect=get_all_workflows),
			patch.object(nl_workflow.frappe, "get_doc", get_doc),
		):
			resolved = nl_workflow.get_workflow_name(doc.doctype, doc.name, doc)

		self.assertEqual(resolved, WORKFLOW)
		get_doc.assert_not_called()

	def test_stored_document_is_still_read_back_when_only_the_name_is_given(self):
		"""Callers that only know the name keep resolving the stored document."""
		doc = frappe._dict(company=COMPANY)

		with (
			patch.object(nl_workflow, "document_exists", return_value=True),
			patch.object(nl_workflow.frappe, "get_doc", return_value=doc) as get_doc,
			patch.object(nl_workflow.frappe, "get_all", side_effect=get_all_workflows),
		):
			resolved = nl_workflow.get_workflow_name("Journal Entry", "ACC-JV-1")

		self.assertEqual(resolved, WORKFLOW)
		get_doc.assert_called_once_with("Journal Entry", "ACC-JV-1")

	def test_missing_document_resolves_to_no_workflow(self):
		"""A record that is neither passed nor stored has no scope information."""
		with (
			patch.object(nl_workflow, "document_exists", return_value=False),
			patch.object(nl_workflow.frappe, "get_doc", Mock(side_effect=AssertionError("unexpected read"))),
			patch.object(nl_workflow.frappe, "get_all", return_value=[]),
		):
			self.assertIsNone(nl_workflow.get_workflow_name("Journal Entry", UNSAVED_NAME))

	def test_validate_hook_hands_the_document_to_the_resolver(self):
		"""The `validate` hook forwards the document it is validating."""
		doc = frappe._dict(doctype="Journal Entry", name=UNSAVED_NAME, company=COMPANY)
		resolve = Mock(return_value=None)

		with (
			patch.object(compat, "is_nl_workflow_doctype", return_value=True),
			patch.object(nl_workflow, "get_workflow_name", resolve),
		):
			compat.validate_workflow_document(doc, "validate")

		resolve.assert_called_once_with(doc.doctype, doc.name, doc)

	def test_transitions_without_a_stored_row_are_empty(self):
		"""A new document has no state yet, so it offers no transition."""
		payload = {"doctype": "Journal Entry", "name": UNSAVED_NAME}

		with patch.object(nl_workflow, "document_exists", return_value=False):
			self.assertEqual(nl_workflow.get_transitions(payload), [])
