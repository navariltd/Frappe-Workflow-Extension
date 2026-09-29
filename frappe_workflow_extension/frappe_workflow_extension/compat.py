"""Bridge the Frappe core workflow endpoints to the NL Workflow engine.

The Desk (toolbar, list view bulk actions, workflow filters), `frappe.client`
and third party apps call the whitelisted endpoints of `frappe.model.workflow`
and `Document.validate_workflow`. Those only understand native `Workflow`
documents. The functions below are wired through `override_whitelisted_methods`
and `doc_events` in `hooks.py`, delegate to the NL Workflow engine
(`frappe_workflow_extension.workflow`) when a DocType is governed by an active
`NL Workflow` and fall back to `frappe.model.workflow` otherwise.
"""

from __future__ import annotations

import frappe
from frappe.model import workflow as native_workflow

from . import workflow as nl_workflow


def is_nl_workflow_doctype(doctype: str | None) -> bool:
	"""Return True when an active `NL Workflow` is configured for `doctype`.

	The answer is cached on `frappe.local` for the duration of the request so
	that the per save, per transition and per form checks stay cheap.

	Args:
	    doctype: DocType to check.

	Returns:
	    True when the extension owns the workflow of this DocType.
	"""
	if not doctype:
		return False

	cache = getattr(frappe.local, "nl_workflow_doctypes", None)
	if cache is None:
		cache = frappe.local.nl_workflow_doctypes = {}

	if doctype not in cache:
		cache[doctype] = bool(frappe.db.exists("NL Workflow", {"document_type": doctype, "is_active": 1}))

	return cache[doctype]


def get_doctype(doc) -> str | None:
	"""Extract the DocType from a document, dictionary or JSON string.

	Args:
	    doc: A `Document`, a document dictionary or its JSON representation.

	Returns:
	    The DocType name, or None when it cannot be determined.
	"""
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)

	return doc.get("doctype") if hasattr(doc, "get") else None


@frappe.whitelist()
def get_transitions(doc, workflow=None, raise_exception: bool = False):
	"""Return the workflow transitions available for `doc`.

	Args:
	    doc: Document, document dictionary or JSON string to inspect.
	    workflow: Optional workflow name to use instead of resolving one.
	    raise_exception: Throw when the document has no workflow state.

	Returns:
	    List of transition dictionaries as understood by the Desk.
	"""
	if is_nl_workflow_doctype(get_doctype(doc)):
		return nl_workflow.get_transitions(doc, workflow, raise_exception=raise_exception)

	return native_workflow.get_transitions(doc, workflow, raise_exception=raise_exception)


@frappe.whitelist()
def apply_workflow(doc, action, comment: str | None = None):
	"""Apply the workflow `action` on `doc` and return the updated document.

	Args:
	    doc: Document, document dictionary or JSON string to transition.
	    action: Workflow action to apply.
	    comment: Optional comment stored with the workflow comment.

	Returns:
	    The saved document.
	"""
	if is_nl_workflow_doctype(get_doctype(doc)):
		return nl_workflow.apply_workflow(doc, action, comment)

	return native_workflow.apply_workflow(doc, action)


@frappe.whitelist()
def bulk_workflow_approval(docnames, doctype, action) -> None:
	"""Apply `action` on several documents, mirroring the Desk bulk action.

	Args:
	    docnames: JSON list of document names.
	    doctype: DocType of the documents.
	    action: Workflow action to apply on every document.
	"""
	if is_nl_workflow_doctype(doctype):
		nl_workflow.bulk_workflow_approval(docnames, doctype, action)
		return

	native_workflow.bulk_workflow_approval(docnames, doctype, action)


@frappe.whitelist()
def get_common_transition_actions(docs, doctype) -> list[str]:
	"""Return the workflow actions valid for every document in `docs`.

	Args:
	    docs: JSON list of document dictionaries, e.g. the checked list rows.
	    doctype: DocType of the documents.

	Returns:
	    Names of the actions that can be applied to all documents at once.
	"""
	if is_nl_workflow_doctype(doctype):
		return nl_workflow.get_common_transition_actions(docs, doctype)

	return native_workflow.get_common_transition_actions(docs, doctype)


@frappe.whitelist()
def can_cancel_document(doctype, docname: str | None = None) -> bool:
	"""Return False when the workflow expects cancellation through a transition.

	Args:
	    doctype: DocType of the document.
	    docname: Optional document name for document scoped workflows.

	Returns:
	    True when the document can be cancelled directly.
	"""
	if is_nl_workflow_doctype(doctype):
		return nl_workflow.can_cancel_document(doctype, docname)

	return native_workflow.can_cancel_document(doctype)


def get_applicable_workflow(doc) -> str | None:
	"""Return the NL Workflow governing `doc`, or None when there is none.

	The document being validated is passed along: a new document is already
	named by its naming series but has no row yet, so resolving its scope from
	the database would fail.

	Args:
	    doc: Document being validated.

	Returns:
	    Name of the matching `NL Workflow`, or None when the DocType is not
	    governed, no scoped workflow matches the document, or the app is being
	    installed.
	"""
	if frappe.flags.in_install == "frappe":
		return None

	if not is_nl_workflow_doctype(doc.doctype):
		return None

	return nl_workflow.get_workflow_name(doc.doctype, doc.name, doc)


def validate_workflow_document(doc, method: str | None = None) -> None:
	"""`validate` document hook enforcing NL Workflow states and transitions.

	Mirrors `frappe.model.document.Document.validate_workflow` for documents
	governed by an `NL Workflow`: the state field may only be changed through a
	permitted transition and, on submit, the state configured for the submitted
	docstatus is applied.

	Args:
	    doc: Document being validated.
	    method: Doc event name provided by the framework.
	"""
	workflow_name = get_applicable_workflow(doc)
	if not workflow_name:
		return

	nl_workflow.validate_workflow(doc)

	if getattr(doc, "_action", "save") == "submit":
		nl_workflow.set_workflow_state_on_action(doc, workflow_name, "submit")


def set_workflow_state_on_update_after_submit(doc, method: str | None = None) -> None:
	"""`before_update_after_submit` hook aligning the state with `docstatus`.

	Native workflows apply this from `Document._validate`, which does not run
	for `update_after_submit`; the extension mirrors it through this hook.

	Args:
	    doc: Submitted document being updated.
	    method: Doc event name provided by the framework.
	"""
	workflow_name = get_applicable_workflow(doc)
	if not workflow_name:
		return

	nl_workflow.validate_workflow(doc)
	nl_workflow.set_workflow_state_on_action(doc, workflow_name, "update_after_submit")
