"""Tests for the fallback used when no NL Workflow applies to a document.

The Desk asks for the workflow actions and for the cancel state of documents that
may predate the workflow, belong to an uncovered company or whose DocType was
never governed. Those requests have to resolve to "no workflow action" instead of
failing, otherwise the list view action menu and the form toolbar break for those
records.
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from frappe_workflow_extension.frappe_workflow_extension import workflow as nl_workflow


class TestWorkflowFallback(UnitTestCase):
	"""Cover the no-workflow branch of the document scoped lookups."""

	def setUp(self):
		patcher = patch.object(nl_workflow, "get_workflow_name", return_value=None)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_get_workflow_returns_none_when_not_raising(self):
		"""Callers serving records outside the scope get None, not an error."""
		self.assertIsNone(nl_workflow.get_workflow("Journal Entry", "ACC-JV-1", raise_exception=False))

	def test_get_workflow_raises_by_default(self):
		"""Explicit callers (apply, validate) still get a configuration error."""
		with self.assertRaises(frappe.ValidationError):
			nl_workflow.get_workflow("Journal Entry", "ACC-JV-1")

	def test_can_cancel_document_without_workflow(self):
		"""A record outside the scope keeps the native cancel path."""
		self.assertTrue(nl_workflow.can_cancel_document("Journal Entry", "ACC-JV-1"))
