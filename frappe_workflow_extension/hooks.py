app_name = "frappe_workflow_extension"
app_title = "Frappe Workflow Extension"
app_publisher = "Navari Ltd"
app_description = (
	"Extend Frappe's workflow system with enhanced permissions, user roles, and approval flexibility."
)
app_email = "support@navari.co.ke"
app_license = "agpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_workflow_extension",
# 		"logo": "/assets/frappe_workflow_extension/logo.png",
# 		"title": "Frappe Workflow Extension",
# 		"route": "/frappe_workflow_extension",
# 		"has_permission": "frappe_workflow_extension.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_workflow_extension/css/frappe_workflow_extension.css"
app_include_js = [
	"/assets/frappe_workflow_extension/js/nl_workflow_registry.js",
	"/assets/frappe_workflow_extension/js/nl_workflow.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/frappe_workflow_extension/css/frappe_workflow_extension.css"
# web_include_js = "/assets/frappe_workflow_extension/js/frappe_workflow_extension.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_workflow_extension/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_workflow_extension/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "frappe_workflow_extension.utils.jinja_methods",
# 	"filters": "frappe_workflow_extension.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "frappe_workflow_extension.install.before_install"
# after_install = "frappe_workflow_extension.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_workflow_extension.uninstall.before_uninstall"
# after_uninstall = "frappe_workflow_extension.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_workflow_extension.utils.before_app_install"
# after_app_install = "frappe_workflow_extension.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_workflow_extension.utils.before_app_uninstall"
# after_app_uninstall = "frappe_workflow_extension.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_workflow_extension.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"validate": [
			"frappe_workflow_extension.frappe_workflow_extension.compat.validate_workflow_document",
		],
		"before_update_after_submit": [
			"frappe_workflow_extension.frappe_workflow_extension.compat.set_workflow_state_on_update_after_submit",
		],
		"on_update": [
			"frappe_workflow_extension.frappe_workflow_extension.doctype.nl_workflow_action.nl_workflow_action.process_workflow_actions",
		],
		"on_cancel": [
			"frappe_workflow_extension.frappe_workflow_extension.doctype.nl_workflow_action.nl_workflow_action.process_workflow_actions",
		],
		"on_trash": [
			"frappe_workflow_extension.frappe_workflow_extension.doctype.nl_workflow_action.nl_workflow_action.process_workflow_actions",
		],
		"on_update_after_submit": [
			"frappe_workflow_extension.frappe_workflow_extension.doctype.nl_workflow_action.nl_workflow_action.process_workflow_actions",
		],
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"frappe_workflow_extension.tasks.all"
# 	],
# 	"daily": [
# 		"frappe_workflow_extension.tasks.daily"
# 	],
# 	"hourly": [
# 		"frappe_workflow_extension.tasks.hourly"
# 	],
# 	"weekly": [
# 		"frappe_workflow_extension.tasks.weekly"
# 	],
# 	"monthly": [
# 		"frappe_workflow_extension.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "frappe_workflow_extension.install.before_tests"

# Overriding Methods
# ------------------------------
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_workflow_extension.task.get_dashboard_data"
# }

# Bridge the Frappe core workflow endpoints to the NL Workflow engine so that the
# Desk (toolbar, workflow filters, list bulk actions), `frappe.client` and third
# party apps keep working for DocTypes governed by an `NL Workflow`.
override_whitelisted_methods = {
	"frappe.model.workflow.get_transitions": "frappe_workflow_extension.frappe_workflow_extension.compat.get_transitions",
	"frappe.model.workflow.apply_workflow": "frappe_workflow_extension.frappe_workflow_extension.compat.apply_workflow",
	"frappe.model.workflow.bulk_workflow_approval": "frappe_workflow_extension.frappe_workflow_extension.compat.bulk_workflow_approval",
	"frappe.model.workflow.get_common_transition_actions": "frappe_workflow_extension.frappe_workflow_extension.compat.get_common_transition_actions",
	"frappe.model.workflow.can_cancel_document": "frappe_workflow_extension.frappe_workflow_extension.compat.can_cancel_document",
}

# Sessions / Boot
# ------------------
# Publish active NL Workflows to the Desk so that the client side workflow
# registries can be filled (see public/js/nl_workflow_registry.js).
boot_session = "frappe_workflow_extension.frappe_workflow_extension.client_data.boot_session"

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_workflow_extension.utils.before_request"]
# after_request = ["frappe_workflow_extension.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_workflow_extension.utils.before_job"]
# after_job = ["frappe_workflow_extension.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"frappe_workflow_extension.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


accounting_dimension_doctypes = [
	"NL Workflow",
]

fixtures = [
	{
		"doctype": "Workspace",
		"filters": [["name", "in", ["Settings"]]],
	}
]
