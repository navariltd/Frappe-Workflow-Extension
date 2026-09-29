/**
 * Register NL Workflows in the Desk client registries.
 *
 * Frappe's Desk renders workflow indicators, workflow state columns, workflow
 * aware submit/cancel buttons, state based read only handling and bulk workflow
 * actions from `frappe.workflow.workflows`, `frappe.workflow.state_fields`,
 * `frappe.workflow.avoid_status_override` and `frappe.model.has_workflow()`.
 * Native Frappe only fills those registries from `Workflow` documents, which
 * leaves DocTypes governed by an `NL Workflow` invisible to the Desk.
 *
 * The active NL Workflows are shipped over bootinfo (see `client_data.py`) and
 * registered here exactly like native ones, so that the untouched Desk code
 * (`frappe.ui.form.States`, list indicators, list bulk actions) drives the UI.
 * Per document resolution (company, user, project, cost center, accounting
 * dimensions) stays server side behind the overridden workflow endpoints.
 */

frappe.provide("frappe.nl_workflow");

Object.assign(frappe.nl_workflow, {
	by_doctype: {},

	/**
	 * Fill the native workflow registries from `frappe.boot.nl_workflows`.
	 */
	setup() {
		const payload = frappe.boot?.nl_workflows;
		if (!payload) return;

		if (payload.workflow_states?.length) {
			frappe.model.sync(payload.workflow_states);
		}

		this.by_doctype = payload.by_doctype || {};
		Object.values(this.by_doctype).forEach((workflow) => this.register(workflow));
	},

	/**
	 * Register a single workflow in the native registries.
	 *
	 * @param {Object} workflow - Merged workflow definition of one DocType.
	 */
	register(workflow) {
		if (!workflow?.document_type) return;

		workflow.is_nl_workflow = true;
		frappe.workflow.workflows[workflow.document_type] = workflow;
		frappe.workflow.state_fields[workflow.document_type] = workflow.workflow_state_field;
		frappe.workflow.avoid_status_override[workflow.document_type] = (workflow.states || [])
			.filter((state) => state.avoid_status_override)
			.map((state) => state.state);
	},

	/**
	 * @param {string} doctype - DocType to check.
	 * @returns {boolean} True when an active NL Workflow governs the DocType.
	 */
	is_enabled(doctype) {
		return Boolean(frappe.workflow.workflows[doctype]?.is_nl_workflow);
	},

	/**
	 * Read only state of a document, mirroring the server side resolution.
	 *
	 * `frappe.workflow.is_read_only` compares the roles of the user with the
	 * `allow_edit` of the state, while an NL Workflow state may instead grant
	 * edit access to a single user (`edit_permission_type`). A state is also only
	 * applicable while its `doc_status` matches the document status.
	 *
	 * @param {string} doctype - DocType of the document.
	 * @param {string} name - Name of the document.
	 * @returns {boolean} True when the document may not be edited.
	 */
	is_read_only(doctype, name) {
		const state_fieldname = frappe.workflow.get_state_fieldname(doctype);
		if (!state_fieldname) return false;

		const doc = locals[doctype] && locals[doctype][name];
		if (!doc || doc.__islocal) return false;

		const state =
			doc[state_fieldname] || frappe.workflow.get_default_state(doctype, doc.docstatus);
		if (!state) return false;

		const state_rows = (frappe.workflow.workflows[doctype].states || []).filter(
			(row) => row.state === state && cint(row.doc_status) === cint(doc.docstatus)
		);

		const allows_edit = (state_row) => {
			if (state_row.edit_permission_type === "User") {
				return state_row.allow_edit === frappe.session.user;
			}
			return frappe.user_roles.includes(state_row.allow_edit);
		};

		return !state_rows.some(allows_edit);
	},

	/**
	 * @param {string} doctype - DocType of the document.
	 * @param {string} action - Workflow action being applied.
	 * @returns {boolean} True when the action requires a comment.
	 */
	requires_comment(doctype, action) {
		const transitions = this.by_doctype[doctype]?.transitions || [];
		return transitions.some(
			(transition) => transition.action === action && transition.require_comment
		);
	},
});

const native_setup = frappe.workflow.setup.bind(frappe.workflow);

frappe.workflow.setup = function (doctype) {
	if (frappe.nl_workflow.is_enabled(doctype)) {
		// NL Workflows come from bootinfo. Native setup would clear the state
		// field, as no `Workflow` document exists for the DocType.
		frappe.nl_workflow.register(frappe.workflow.workflows[doctype]);
		return;
	}

	native_setup(doctype);
};

const native_has_workflow = frappe.model.has_workflow.bind(frappe.model);

frappe.model.has_workflow = function (doctype) {
	return frappe.nl_workflow.is_enabled(doctype) || native_has_workflow(doctype);
};

const native_is_read_only = frappe.workflow.is_read_only.bind(frappe.workflow);

frappe.workflow.is_read_only = function (doctype, name) {
	if (frappe.nl_workflow.is_enabled(doctype)) {
		return frappe.nl_workflow.is_read_only(doctype, name);
	}

	return native_is_read_only(doctype, name);
};

frappe.nl_workflow.setup();
