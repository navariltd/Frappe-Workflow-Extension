import frappe
from frappe import _
from frappe.model.document import Document


class NLWorkflow(Document):
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from frappe.workflow.doctype.workflow_document_state.workflow_document_state import (
            WorkflowDocumentState,
        )
        from frappe.workflow.doctype.workflow_transition.workflow_transition import (
            WorkflowTransition,
        )

        document_type: DF.Link
        is_active: DF.Check
        override_status: DF.Check
        send_email_alert: DF.Check
        states: DF.Table[WorkflowDocumentState]
        transitions: DF.Table[WorkflowTransition]
        workflow_data: DF.JSON | None
        workflow_name: DF.Data
        workflow_state_field: DF.Data
        user: DF.Link | None
        company: DF.Link | None
        project: DF.Link | None

    def validate(self):
        self.validate_docstatus()
        self.validate_unique_active_combination()

    def on_update(self):
        self.create_custom_field_for_workflow_state()
        self.update_default_workflow_status()

    def create_custom_field_for_workflow_state(self):
        frappe.clear_cache(doctype=self.document_type)
        meta = frappe.get_meta(self.document_type)

        if not meta.get_field(self.workflow_state_field):
            custom_field = frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": self.document_type,
                    "fieldname": self.workflow_state_field,
                    "label": self.workflow_state_field.replace("_", " ").title(),
                    "hidden": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "fieldtype": "Link",
                    "options": "Workflow State",
                    "owner": "Administrator",
                }
            )
            custom_field.insert(ignore_permissions=True)
            frappe.msgprint(
                _("Created Custom Field {0} in {1}").format(
                    self.workflow_state_field, self.document_type
                )
            )

    def update_default_workflow_status(self):
        states = self.get("states") or []
        if not states:
            return

        for d in states:
            docs_to_update = frappe.get_all(
                self.document_type,
                filters={
                    self.workflow_state_field: ["in", ["", None]],
                    "docstatus": d.doc_status,
                },
                pluck="name",
            )

            for name in docs_to_update:
                frappe.db.set_value(
                    self.document_type, name, self.workflow_state_field, d.state
                )

    def validate_docstatus(self):
        def get_state(state):
            for s in self.states:
                if s.state == state:
                    return s
            frappe.throw(_("{0} is not a valid State").format(state))

        for t in self.transitions:
            state = get_state(t.state)
            next_state = get_state(t.next_state)

            if state.doc_status == "2":
                frappe.throw(
                    _(
                        "Cannot change state of Cancelled Document (Transition row {0})"
                    ).format(t.idx)
                )

            if state.doc_status == "1" and next_state.doc_status == "0":
                frappe.throw(
                    _(
                        "Submitted Document cannot revert to Draft (Transition row {0})"
                    ).format(t.idx)
                )

            if state.doc_status == "0" and next_state.doc_status == "2":
                frappe.throw(
                    _("Cannot cancel before submitting (Transition row {0})").format(
                        t.idx
                    )
                )

    def set_active(self):
        """Deactivate other workflows for the same document type if this one is active."""
        if int(self.is_active or 0):
            other_workflows = frappe.get_all(
                "NL Workflow",
                filters={
                    "document_type": self.document_type,
                    "is_active": 1,
                    "name": ["!=", self.name],
                },
                pluck="name",
            )
            for wf in other_workflows:
                frappe.db.set_value("NL Workflow", wf, "is_active", 0)

    def validate_unique_active_combination(self):
        """Ensure only one active workflow exists per unique combination of
        document_type, company, user, and all accounting dimensions."""
        if not self.document_type:
            frappe.throw(_("Document Type is required for workflow validation."))

        if not self.is_active:
            return

        existing_workflow = frappe.db.exists(
            "Workflow",
            {
                "document_type": self.document_type,
                "is_active": 1,
            },
        )

        if existing_workflow:
            frappe.throw(
                _(
                    f"An active standard workflow already exists for Document Type: {self.document_type}. "
                    f"Please deactivate the standard workflow before activating this one.<br><br>"
                    f"<a href='/app/workflow/{existing_workflow}' target='_blank' style='text-decoration: underline;'><strong>View Existing Workflow</strong></a>"
                )
            )

        accounting_dimensions = (
            frappe.get_all(
                "Accounting Dimension", filters={"disabled": 0}, pluck="fieldname"
            )
            or []
        )

        filters = {
            "document_type": self.document_type,
            "is_active": 1,
            "name": ["!=", self.name],
            "company": self.company or ["in", [None, ""]],
            "user": self.user or ["in", [None, ""]],
            "project": self.project or ["in", [None, ""]],
            "cost_center": self.cost_center or ["in", [None, ""]],
        }

        new_accounting_dimensions = []
        for dimension in accounting_dimensions:
            if hasattr(self, dimension):
                new_accounting_dimensions.append(dimension)

                if getattr(self, dimension):
                    filters[dimension] = getattr(self, dimension)

        existing_workflows = frappe.get_all(
            "NL Workflow",
            filters=filters,
            fields=["name", "document_type", *new_accounting_dimensions],
        )

        if existing_workflows:
            existing_doc = existing_workflows[0]

            matching_criteria = []
            matching_criteria.append(
                _("Document Type: <strong>{0}</strong>").format(self.document_type)
            )

            for dimension in accounting_dimensions:
                current_value = getattr(self, dimension, None)
                existing_value = existing_doc.get(dimension)

                if current_value and existing_value and current_value == existing_value:
                    dimension_label = (
                        frappe.get_meta("NL Workflow").get_field(dimension).label
                    )
                    matching_criteria.append(
                        _("{0}: <strong>{1}</strong>").format(
                            dimension_label, current_value
                        )
                    )

            error_message = """
                <div style="font-family: sans-serif;">
                    <h4 style="color: #e74c3c; margin-bottom: 15px;">🚫 Duplicate Active Workflow Detected</h4>
                    
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                        <p style="margin: 0 0 10px 0;"><strong>Matching Criteria:</strong></p>
                        <ul style="margin: 0; padding-left: 20px;">
                            {criteria_items}
                        </ul>
                    </div>
                    
                    <p style="margin-bottom: 15px;">
                        The workflow 
                        <a href="/app/nl-workflow/{existing_name}" target="_blank" style="color: #2490ef; text-decoration: none;">
                            <strong>{existing_name}</strong>
                        </a> 
                        is already active with the same combination.
                    </p>
                    
                    <div style="background: #fff3cd; padding: 12px; border-radius: 5px; border-left: 4px solid #ffc107;">
                        <strong>💡 Resolution Required:</strong><br>
                        Only one active workflow is allowed per unique combination of Document Type and Accounting Dimensions. 
                        You must either:
                        <ul style="margin: 10px 0;">
                            <li>Deactivate the existing workflow  <a href="/app/nl-workflow/{existing_name}" target="_blank" style="color: #2490ef; text-decoration: none;">
                            <strong>{existing_name}</strong>
                        </a> </li>
                            <li>Modify the accounting dimensions of this workflow to make it unique</li>
                            <li>Deactivate this workflow and use the existing one</li>
                        </ul>
                    </div>
                </div>
            """.format(
                criteria_items="".join(
                    [f"<li>{item}</li>" for item in matching_criteria if item]
                ),
                existing_name=existing_doc.name,
            )

            frappe.throw(_(error_message), title=_("Duplicate Workflow Configuration"))


@frappe.whitelist()
def get_workflow_state_count(doctype, workflow_state_field, states):
    frappe.has_permission(doctype=doctype, ptype="read", throw=True)
    states = frappe.parse_json(states)

    meta = frappe.get_meta(doctype)
    if workflow_state_field not in meta.get_valid_columns():
        return []

    return frappe.get_all(
        doctype,
        fields=[
            workflow_state_field,
            {"COUNT": "*", "as": "count"},
        ],
        filters={
            workflow_state_field: ["not in", states],
        },
        group_by=workflow_state_field,
    )
