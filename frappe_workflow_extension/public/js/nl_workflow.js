/**
 * Workflow actions on forms of DocTypes governed by an `NL Workflow`.
 *
 * `nl_workflow_registry.js` registers NL Workflows in the native client
 * registries, so the Desk renders workflow indicators, workflow state columns,
 * form read only handling, transition buttons and the workflow help action for
 * those DocTypes from the standard `frappe.ui.form.States` controller. Two
 * engine specific rules still need a client side counterpart:
 *
 * 1. A transition may be assigned to a single user (`approver_type`), which the
 *    native action menu filters out because it compares `allowed` with the roles
 *    of the user. The transitions returned by `get_transitions` are already
 *    resolved for the current user, so only the self approval rule has to be
 *    re-applied here.
 * 2. A transition may require a comment, which the native action menu does not
 *    collect.
 */

const native_show_actions = frappe.ui.form.States.prototype.show_actions;

frappe.ui.form.States.prototype.show_actions = function () {
	if (!frappe.nl_workflow.is_enabled(this.frm.doctype)) {
		return native_show_actions.call(this);
	}

	show_nl_workflow_actions(this);
};

/**
 * Show the transitions available for the current user as form actions.
 *
 * Mirrors `frappe.ui.form.States.show_actions` without its role check, see the
 * module docstring.
 *
 * @param {frappe.ui.form.States} states - States controller of the form.
 */
function show_nl_workflow_actions(states) {
	const frm = states.frm;

	if (frm.doc.__unsaved === 1) return;

	frappe.workflow
		.get_transitions(frm.doc)
		.then((transitions) => {
			frm.page.clear_actions_menu();
			let added = false;

			transitions
				.filter((transition) => nl_has_approval_access(frm, transition))
				.forEach((transition) => {
					added = true;
					frm.page.add_action_item(__(transition.action), function () {
						const workflow = frappe.workflow.workflows[frm.doctype] || {};

						if (workflow.enable_action_confirmation) {
							frappe.confirm(
								__("Are you sure you want to {0}?", [transition.action]),
								() => states.handle_workflow_action(transition)
							);
						} else {
							states.handle_workflow_action(transition);
						}
					});
				});

			states.setup_btn(added);
		})
		.catch(() => {
			// A failed transition lookup must not leave the form without its
			// regular actions, so fall back to showing no workflow action.
			states.setup_btn(false);
		});
}

/**
 * Apply the self approval rule of the engine.
 *
 * @param {frappe.ui.form.Form} frm - Form holding the document.
 * @param {Object} transition - Transition offered for the current state.
 * @returns {boolean} True when the current user may apply the transition.
 */
function nl_has_approval_access(frm, transition) {
	return (
		frappe.session.user === "Administrator" ||
		Boolean(transition.allow_self_approval) ||
		frappe.session.user !== frm.doc.owner
	);
}

const native_handle_workflow_action = frappe.ui.form.States.prototype.handle_workflow_action;

frappe.ui.form.States.prototype.handle_workflow_action = function (transition) {
	const frm = this.frm;

	if (!frappe.nl_workflow.requires_comment(frm.doctype, transition.action)) {
		return native_handle_workflow_action.call(this, transition);
	}

	frappe.prompt(
		[
			{
				fieldtype: "Small Text",
				fieldname: "comment",
				label: __("Comment"),
				description: __("This transition requires a comment."),
				reqd: 1,
			},
		],
		(values) => apply_nl_workflow_action(frm, transition.action, values.comment),
		__("Workflow Action: {0}", [transition.action]),
		__("Apply")
	);
};

/**
 * Apply a workflow action together with a comment.
 *
 * Mirrors `frappe.ui.form.States.handle_workflow_action`, which does not send a
 * comment.
 *
 * @param {frappe.ui.form.Form} frm - Form being transitioned.
 * @param {string} action - Workflow action to apply.
 * @param {string} comment - Comment stored with the transition.
 */
function apply_nl_workflow_action(frm, action, comment) {
	frappe.dom.freeze();
	frm.selected_workflow_action = action;

	Promise.resolve(frm.script_manager.trigger("before_workflow_action"))
		.then(() =>
			frappe.xcall("frappe.model.workflow.apply_workflow", {
				doc: frm.doc,
				action: action,
				comment: comment,
			})
		)
		.then((doc) => {
			frappe.model.sync(doc);
			frm.refresh();
			frm.selected_workflow_action = null;
			frm.script_manager.trigger("after_workflow_action");
		})
		.finally(() => frappe.dom.unfreeze());
}
