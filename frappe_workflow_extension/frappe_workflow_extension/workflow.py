# Copyright (c) 2025, Kenya Red Cross Society
# License: see license.txt

import json
from collections import defaultdict
from typing import Union

import frappe
from frappe import _
from frappe.model.docstatus import DocStatus
from frappe.model.document import Document
from frappe.utils import cint


def get_doc_workflow_state(doc):
    workflow_name = get_workflow_name(doc.get("doctype"), doc.get("name"))
    workflow_state_field = get_workflow_state_field(workflow_name)
    return doc.get(workflow_state_field)


def get_closest_company_with_workflow(
    company: str, workflows: list[dict]
) -> str | None:
    """
    Returns the company (current or closest parent with allow_descendants)
    that has an active workflow defined.
    Stops at the first eligible parent found.
    """
    if any(wf.company == company for wf in workflows):
        return company

    current = company
    while True:
        parent = frappe.db.get_value("Company", current, "parent_company")
        if not parent:
            break

        parent_workflow_exists = any(
            wf.company == parent and wf.allow_descendants for wf in workflows
        )
        if parent_workflow_exists:
            return parent

        current = parent

    return None


@frappe.whitelist()
def get_workflow_name(doctype: str, docname: str | int = None) -> str | None:
    """
    Determine the most specific active workflow for a document based on:
    Priority:
    1️⃣ Closest company in tree (company or closest parent with allow_descendants)
    2️⃣ User
    3️⃣ Accounting Dimensions
    4️⃣ Cost Center
    5️⃣ Project
    """

    doc = frappe.get_doc(doctype, docname) if docname else None

    company = getattr(doc, "company", None) or frappe.defaults.get_user_default(
        "Company"
    )
    project = getattr(doc, "project", None)
    cost_center = getattr(doc, "cost_center", None)
    user = getattr(doc, "owner", None) or frappe.session.user

    if not company:
        return None

    workflows = frappe.get_all(
        "NL Workflow",
        filters={"document_type": doctype, "is_active": 1},
        fields=[
            "name",
            "company",
            "project",
            "cost_center",
            "allow_descendants",
            "user",
        ],
    )

    closest_company = get_closest_company_with_workflow(company, workflows)
    if not closest_company:
        return None

    valid_workflows = [wf for wf in workflows if wf.company == closest_company] + [
        wf for wf in workflows if wf.allow_descendants and wf.company == closest_company
    ]

    accounting_dimensions = frappe.get_all(
        "Accounting Dimension", filters={"disabled": 0}, pluck="fieldname"
    )

    def matches_user(wf):
        return wf.user and wf.user == user

    def matches_accounting_dimensions(wf):
        if not accounting_dimensions or not doc:
            return False
        for dim in accounting_dimensions:
            doc_val = getattr(doc, dim, None)
            wf_val = getattr(wf, dim, None)
            if wf_val and doc_val and wf_val == doc_val:
                return True
        return False

    def matches_cost_center(wf):
        return wf.cost_center and wf.cost_center == cost_center

    def matches_project(wf):
        return wf.project and wf.project == project

    def matches_company(wf):
        return wf.company == closest_company

    priority_checks = [
        matches_user,
        matches_accounting_dimensions,
        matches_cost_center,
        matches_project,
        matches_company,
    ]

    for check in priority_checks:
        for wf in valid_workflows:
            if check(wf):
                return wf.name

    return None


@frappe.whitelist()
def get_workflow(doctype: str, docname: str | int = None):
    """Return cached NL Workflow document for the given doctype."""
    workflow_name = get_workflow_name(doctype, docname)
    if not workflow_name:
        frappe.throw(
            _(f"No active NL Workflow found for {doctype}. Please configure one."),
            title=_("Workflow Missing"),
        )
    return frappe.get_cached_doc("NL Workflow", workflow_name)


@frappe.whitelist()
def get_transitions(
    doc: Union[Document, str, dict],
    workflow: str = None,
    current_state: str = None,
    raise_exception: bool = False,
) -> list[dict]:
    """Return transitions for the current user in NL Workflow."""

    if not isinstance(doc, Document):
        doc = frappe.get_doc(frappe.parse_json(doc))
        if not doc.get("name"):
            return []
        doc.load_from_db()

    if doc.is_new():
        return []

    user = frappe.session.user
    doc.check_permission("read")

    workflow_doc = (
        frappe.get_doc("NL Workflow", workflow)
        if workflow
        else get_workflow(doc.doctype, doc.name)
    )
    current_state = current_state or doc.get(workflow_doc.workflow_state_field)

    if not current_state:
        current_state = workflow_doc.transitions[0].state

    state = next((s for s in workflow_doc.states if s.state == current_state), None)

    if state and (cint(state.doc_status) != cint(doc.get("docstatus"))):
        frappe.throw(
            _(
                "Workflow state '{0}' is not compatible with document status ({1}). "
                "Please verify the NL Workflow configuration and ensure the document's "
                "workflow state matches its docstatus."
            ).format(state.state, doc.get("docstatus")),
            title=_("Invalid Workflow State"),
        )
        return []

    if not current_state:
        if raise_exception:
            frappe.throw(_("Workflow State not set"))
        return []
    transitions = get_allowed_transitions_for_user(
        workflow_doc.name, current_state, user
    )
    allowed_transitions = []
    for transition in transitions:
        if not is_transition_condition_satisfied(transition, doc):
            continue
        allowed_transitions.append(transition)
    return allowed_transitions


def get_allowed_transitions_for_user(
    workflow, current_state: str, user: str = None
) -> list[dict]:
    """Return all transitions allowed for the user for current state."""
    if not user:
        user = frappe.session.user
    transitions = frappe.get_all(
        "NL Workflow Transition",
        filters={"parent": workflow, "state": current_state},
        fields=["*"],
        order_by="idx asc",
    )

    user_roles = frappe.get_roles(user)
    allowed = []

    for t in transitions:
        if t.approver_type == "Role" and t.allowed in user_roles:
            if t.company:
                if t.get("company"):
                    if not frappe.has_permission(
                        "Company", doc=t.company, ptype="read", user=user
                    ):
                        continue
            allowed.append(t)
        elif t.approver_type == "User" and t.allowed == user:
            allowed.append(t)

    return allowed


def has_approval_access(user, doc, transition):
    """Determine if user can perform transition (no self-approval unless allowed)."""
    return (
        user == "Administrator"
        or transition.get("allow_self_approval")
        or user != doc.get("owner")
    )


@frappe.whitelist()
def apply_workflow(doc, action, comment=None):
    """Execute a workflow transition action for NL Workflow."""
    doc = frappe.get_doc(frappe.parse_json(doc))
    doc.load_from_db()

    workflow = get_workflow(doc.doctype, doc.name)
    transitions = get_transitions(doc, workflow.name)
    user = frappe.session.user

    transition = next((t for t in transitions if t.action == action), None)

    if not transition:
        frappe.throw(_("Invalid Workflow Action: {0}").format(action))

    if not has_approval_access(user, doc, transition):
        frappe.throw(_("Self-approval is not allowed for this action."))

    doc.set(workflow.workflow_state_field, transition.next_state)

    next_state = next(
        (s for s in workflow.states if s.state == transition.next_state), None
    )
    if not next_state:
        frappe.throw(
            _("Next workflow state not defined: {0}").format(transition.next_state)
        )

    if next_state.update_field:
        doc.set(next_state.update_field, next_state.update_value)

    new_docstatus = DocStatus(next_state.doc_status or 0)
    _update_docstatus(doc, new_docstatus)

    docstatus_color_map = {
        0: {"bg": "#fff3cd", "border": "#ffc107", "text": "#856404", "icon": "⊙"},
        1: {"bg": "#e8f5e9", "border": "#4caf50", "text": "#2e7d32", "icon": "✓"},
        2: {"bg": "#ffebee", "border": "#f44336", "text": "#c62828", "icon": "✕"},
    }
    status_style = docstatus_color_map.get(
        int(next_state.doc_status or 0), docstatus_color_map[0]
    )

    comment_text = _(
        f"<div style='padding: 8px; background-color: {status_style['bg']}; border-left: 4px solid {status_style['border']}; border-radius: 4px;'><strong style='color: {status_style['text']}'>{status_style['icon']} Moved to</strong> <span style='color: #1565c0; font-weight: bold;'>{next_state.state}</span></div>"
    )
    if comment:
        comment_text += f"<div style='margin-top: 8px; padding: 8px; background-color: #e3f2fd; border-left: 4px solid #2196f3; border-radius: 4px;'><strong style='color: #1565c0;'>💬 Note:</strong> <em style='color: #666;'>{comment}</em></div>"
    doc.add_comment("Workflow", comment_text)
    return doc


def _update_docstatus(doc, new_docstatus):
    """Handle docstatus transitions cleanly."""
    if doc.docstatus.is_draft() and new_docstatus.is_draft():
        doc.save()
    elif doc.docstatus.is_draft() and new_docstatus.is_submitted():
        doc.submit()
    elif doc.docstatus.is_submitted() and new_docstatus.is_submitted():
        doc.save()
    elif doc.docstatus.is_submitted() and new_docstatus.is_cancelled():
        doc.cancel()
    else:
        frappe.throw(_("Illegal Document Status transition"))


@frappe.whitelist()
def bulk_workflow_approval(docnames, doctype, action):
    """Run bulk workflow approvals in background or sequentially."""
    docnames = json.loads(docnames)
    if len(docnames) < 20:
        _bulk_workflow_action(docnames, doctype, action)
    elif len(docnames) <= 500:
        frappe.msgprint(
            _(f"Bulk {action} enqueued for background processing."),
            alert=True,
        )
        frappe.enqueue(
            _bulk_workflow_action,
            docnames=docnames,
            doctype=doctype,
            action=action,
            queue="short",
            timeout=1000,
        )
    else:
        frappe.throw(_("Bulk approval limited to 500 documents."))


def _bulk_workflow_action(docnames, doctype, action):
    failed, success = defaultdict(list), defaultdict(list)
    frappe.clear_messages()

    for idx, name in enumerate(docnames, 1):
        try:
            show_progress(docnames, _("Applying: {0}").format(action), idx, name)
            apply_workflow(frappe.get_doc(doctype, name), action)
            frappe.db.commit()
            success[name].append({"message": "Success"})
        except Exception as e:
            frappe.db.rollback()
            failed[name].append({"message": str(e)})
            frappe.log_error(
                title=f"Workflow {action} failed for {doctype} {name}",
                reference_doctype="NL Workflow",
                reference_name=action,
            )

    _print_workflow_results(success, failed, doctype)


def _print_workflow_results(success, failed, doctype):
    """Display a summarized report after bulk workflow processing."""
    if success:
        _print_workflow_log(success, _("Successful Transactions"), doctype, "green")
    if failed:
        _print_workflow_log(failed, _("Failed Transactions"), doctype, "red")


def _print_workflow_log(records, title, doctype, indicator):
    if not records:
        return
    msg = f"<h4>{title}</h4>"
    for doc, logs in records.items():
        html = (
            f"<details><summary>{frappe.utils.get_link_to_form(doctype, doc)}</summary>"
        )
        for l in logs:
            html += f"<div class='small text-muted' style='padding:2.5px'>{l.get('message')}</div>"
        html += "</details>"
        msg += html
    frappe.msgprint(
        msg,
        title=_("Workflow Status"),
        indicator=indicator,
        is_minimizable=True,
        realtime=True,
    )


def show_progress(docnames, message, i, description):
    n = len(docnames)
    if n >= 5:
        frappe.publish_progress(
            float(i) * 100 / n, title=message, description=description
        )


@frappe.whitelist()
def get_workflow_info(doc: dict | str):
    if isinstance(doc, str):
        doc = json.loads(doc)

    workflow_name = get_workflow_name(doc.get("doctype"), doc.get("name"))
    if not workflow_name:
        return None

    workflow = frappe.get_cached_doc("NL Workflow", workflow_name)
    allow_edit = False
    user = frappe.session.user
    user_roles = frappe.get_roles(user)

    workflow_state = get_doc_workflow_state(doc)
    if not workflow_state:
        workflow_state = workflow.transitions[0].state

    state = next((s for s in workflow.states if s.state == workflow_state), None)

    if state and (cint(state.doc_status) != cint(doc.get("docstatus"))):
        return None

    if state:
        if state.edit_permission_type == "User":
            if state.allow_edit == user:
                allow_edit = True
        elif state.edit_permission_type == "Role":
            allowed_role = state.allow_edit
            if allowed_role:
                if isinstance(allowed_role, str):
                    allowed_role = allowed_role.strip()
                if allowed_role in user_roles:
                    allow_edit = True

    result = {"workflow": workflow.as_dict(), "current_state": workflow_state}
    if allow_edit:
        result["allow_edit"] = allow_edit

    return result


@frappe.whitelist()
def get_common_transition_actions(docs, doctype):
    """Find workflow actions common to all given documents."""
    if isinstance(docs, str):
        docs = json.loads(docs)

    user = frappe.session.user
    common_actions = None

    for doc in docs:
        if not doc.get("doctype"):
            doc["doctype"] = doctype

        transitions = get_transitions(doc)
        actions = [
            t.get("action") for t in transitions if has_approval_access(user, doc, t)
        ]
        if common_actions is None:
            common_actions = set(actions)
        else:
            common_actions &= set(actions)
        if not common_actions:
            break

    return list(common_actions or [])


def get_workflow_safe_globals():
    # access to frappe.db.get_value, frappe.db.get_list, and date time utils.
    return dict(
        frappe=frappe._dict(
            db=frappe._dict(get_value=frappe.db.get_value, get_list=frappe.db.get_list),
            session=frappe.session,
            utils=frappe._dict(
                now_datetime=frappe.utils.now_datetime,
                add_to_date=frappe.utils.add_to_date,
                get_datetime=frappe.utils.get_datetime,
                now=frappe.utils.now,
            ),
        )
    )


def is_transition_condition_satisfied(transition, doc) -> bool:
    if not transition.condition:
        return True
    else:
        return frappe.safe_eval(
            transition.condition, get_workflow_safe_globals(), dict(doc=doc.as_dict())
        )


@frappe.whitelist()
def can_cancel_document(doctype, docname=None):
    workflow = get_workflow(doctype, docname)
    cancelling_states = [s.state for s in workflow.states if s.doc_status == "2"]
    if not cancelling_states:
        return True

    for transition in workflow.transitions:
        if transition.next_state in cancelling_states:
            return False
    return True


def validate_workflow(doc):
    """Validate Workflow State and Transition for the current user.

    - Check if user is allowed to edit in current state
    - Check if user is allowed to transition to the next state (if changed)
    """
    workflow = get_workflow(doc.doctype, doc.name)

    current_state = None
    if getattr(doc, "_doc_before_save", None):
        current_state = doc._doc_before_save.get(workflow.workflow_state_field)
    next_state = doc.get(workflow.workflow_state_field)

    if not next_state:
        next_state = workflow.states[0].state
        doc.set(workflow.workflow_state_field, next_state)

    if not current_state:
        current_state = workflow.states[0].state

    state_row = [d for d in workflow.states if d.state == current_state]
    if not state_row:
        frappe.throw(
            _(
                "{0} is not a valid Workflow State. Please update your Workflow and try again."
            ).format(frappe.bold(current_state))
        )
    state_row = state_row[0]

    # if transitioning, check if user is allowed to transition
    if current_state != next_state:
        bold_current = frappe.bold(current_state)
        bold_next = frappe.bold(next_state)

        if not doc._doc_before_save:
            # transitioning directly to a state other than the first
            # e.g from data import
            frappe.throw(
                _("Workflow State transition not allowed from {0} to {1}").format(
                    bold_current, bold_next
                ),
            )

        transitions = get_transitions(doc._doc_before_save)
        transition = [d for d in transitions if d.next_state == next_state]
        if not transition:
            frappe.throw(
                _("Workflow State transition not allowed from {0} to {1}").format(
                    bold_current, bold_next
                ),
            )


def get_workflow_state_field(workflow_name):
    return get_workflow_field_value(workflow_name, "workflow_state_field")


def send_email_alert(workflow_name):
    return get_workflow_field_value(workflow_name, "send_email_alert")


def get_workflow_field_value(workflow_name, field):
    return frappe.get_cached_value("NL Workflow", workflow_name, field)


def print_workflow_log(messages, title, doctype, indicator):
    if messages.keys():
        msg = f"<h4>{title}</h4>"

        for doc in messages.keys():
            if len(messages[doc]):
                html = f"<details><summary>{frappe.utils.get_link_to_form(doctype, doc)}</summary>"
                for log in messages[doc]:
                    if log.get("message"):
                        html += "<div class='small text-muted' style='padding:2.5px'>{}</div>".format(
                            log.get("message")
                        )
                html += "</details>"
            else:
                html = f"<div>{doc}</div>"
            msg += html

        frappe.msgprint(
            msg,
            title=_("Workflow Status"),
            indicator=indicator,
            is_minimizable=True,
            realtime=True,
        )


def set_workflow_state_on_action(doc, workflow_name, action):
    workflow = frappe.get_doc("NL Workflow", workflow_name)
    workflow_state_field = workflow.workflow_state_field

    # If workflow state of doc is already correct, don't set workflow state
    for state in workflow.states:
        if state.state == doc.get(workflow_state_field) and doc.docstatus == cint(
            state.doc_status
        ):
            return

    action_map = {"update_after_submit": "1", "submit": "1", "cancel": "2"}
    docstatus = action_map[action]
    for state in workflow.states:
        if state.doc_status == docstatus:
            doc.set(workflow_state_field, state.state)
            return
