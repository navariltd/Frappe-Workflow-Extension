$(document).on("form-refresh", function (event, frm) {
	if (!frm || !frm.doctype) return;
	if (frm.doc.__islocal) return;

	try {
		frappe.call({
			method: "frappe_workflow_extension.frappe_workflow_extension.workflow.get_workflow_info",
			args: { doc: frm.doc },
			callback: function (res) {
				if (!res?.message?.workflow && !res?.message?.current_state) return;
				const workflow = res.message.workflow;
				const workflow_name = res.message.workflow.name;
				const current_state = res.message.current_state;

				if (!res.message.allow_edit) {
					frm.set_read_only(true);
				}

				const has_workflow = !!workflow_name;

				if (has_workflow) {
					frm.page.clear_primary_action();

					if (!workflow.override_status)
						override_document_status(
							frm,
							current_state,
							workflow.workflow_state_field,
						);
				}

				if (workflow.name) {
					load_allowed_transitions(frm, workflow, current_state);
				}
			},
		});
	} catch (error) {
		console.error(" Error initializing workflow:", error);
	}
});

function load_allowed_transitions(frm, workflow, current_state) {
	frappe.call({
		method: "frappe_workflow_extension.frappe_workflow_extension.workflow.get_transitions",
		args: { doc: frm.doc, workflow: workflow.name, current_state: current_state },
		callback: function (r) {
			const transitions = r.message || [];

			frm.page.clear_actions_menu();

			if (!transitions.length) return;

			let added = false;

			transitions.forEach((t) => {
				frm.page.add_action_item(__(t.action), function () {
					frm.selected_workflow_action = t.action;

					if (!frappe.ui.form.check_mandatory(frm)) {
						return;
					}

					open_workflow_comment_dialog(frm, t);
				});
				added = true;
			});

			if (added) add_workflow_help_action(frm, transitions);
		},
	});
}

function add_workflow_help_action(frm, transitions) {
	try {
		frm.page.add_action_item(__("Workflow Help"), function () {
			const state_field = frappe.workflow.get_state_fieldname(frm.doctype);
			const current_state = frm.doc[state_field] || __("Unknown");

			let next_actions = transitions
				.map((d) => `${d.action.bold()} (${d.allowed})`)
				.join(", ");

			if (!next_actions) next_actions = __("None: End of Workflow").bold();

			const dialog = new frappe.ui.Dialog({
				title: __("Workflow: {0}", [frm.doctype]),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "info",
						options: `
							<p>${__("Current status")}: ${current_state.bold()}</p>
							<p>${__("Next actions")}: ${next_actions}</p>
							<p>${__("Only users with permission can perform these transitions.")}</p>
						`,
					},
				],
			});
			dialog.show();
		});
	} catch (error) {
		console.warn(" Failed to add help action:", error);
	}
}

function override_document_status(frm, current_state, workflow_state_field) {
	try {
		const doc = frm.doc;
		const doctype = frm.doctype;
		if (!doc || !doctype) return;

		let label = __("Unknown");
		let filter = null;

		const meta = frappe.get_meta(doctype);
		const is_submittable = meta?.is_submittable;

		if (doc.__unsaved) {
			label = __("Not Saved");
			const color = "orange";
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color);
			}
		} else if (current_state) {
			const value = current_state;
			label = __(value);
			filter = `${workflow_state_field},=,${value}`;

			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Workflow State",
					fieldname: "style",
					filters: { name: value },
				},
				callback: function (r) {
					let color = "gray";
					if (r.message && r.message.style) {
						const style = r.message.style;
						color =
							{
								Success: "green",
								Warning: "orange",
								Danger: "red",
								Primary: "blue",
								Inverse: "black",
								Info: "light-blue",
							}[style] || "gray";
					}

					if (frm.page && typeof frm.page.set_indicator === "function") {
						frm.page.set_indicator(label, color, filter);
					}
				},
			});
		} else if (is_submittable && doc.docstatus === 0) {
			label = __("Draft");
			const color = "red";
			filter = "docstatus,=,0";
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (is_submittable && doc.docstatus === 1) {
			label = __("Submitted");
			const color = "blue";
			filter = "docstatus,=,1";
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (is_submittable && doc.docstatus === 2) {
			label = __("Cancelled");
			const color = "red";
			filter = "docstatus,=,2";
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (doc.status && meta?.states?.find((d) => d.title === doc.status)) {
			const state = meta.states.find((d) => d.title === doc.status);
			label = __(doc.status);
			const color = frappe.scrub(state.color, "-");
			filter = `status,=,${doc.status}`;
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (doc.status) {
			label = __(doc.status);
			const color = frappe.utils.guess_colour(doc.status);
			filter = `status,=,${doc.status}`;
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (frappe.meta.has_field(doctype, "enabled")) {
			label = doc.enabled ? __("Enabled") : __("Disabled");
			const color = doc.enabled ? "blue" : "gray";
			filter = `enabled,=,${doc.enabled ? 1 : 0}`;
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		} else if (frappe.meta.has_field(doctype, "disabled")) {
			label = doc.disabled ? __("Disabled") : __("Enabled");
			const color = doc.disabled ? "gray" : "blue";
			filter = `disabled,=,${doc.disabled ? 1 : 0}`;
			if (frm.page && typeof frm.page.set_indicator === "function") {
				frm.page.set_indicator(label, color, filter);
			}
		}
	} catch (error) {
		console.warn("Failed to override document status:", error);
	}
}

function open_workflow_comment_dialog(frm, transition) {
	const require_comment = !!transition.require_comment;

	const d = new frappe.ui.Dialog({
		title: __("Workflow Action: {0}", [transition.action]),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "comment",
				label: __("Comment"),
				reqd: require_comment,
				description: require_comment
					? __("A comment is required for this transition.")
					: __("Optional"),
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			if (require_comment && !values.comment) {
				frappe.msgprint(__("Comment is required."));
				return;
			}

			d.hide();
			apply_workflow_with_comment(frm, transition.action, values.comment);
		},
	});

	d.show();
}

function apply_workflow_with_comment(frm, action, comment) {
	frappe.dom.freeze();

	frappe
		.xcall("frappe_workflow_extension.frappe_workflow_extension.workflow.apply_workflow", {
			doc: frm.doc,
			action: action,
			comment: comment,
		})
		.then((doc) => {
			frappe.model.sync(doc);
			frm.refresh();
			frappe.show_alert({
				message: __("Workflow action applied: {0}", [action]),
				indicator: "green",
			});
		})
		.finally(() => frappe.dom.unfreeze());
}
