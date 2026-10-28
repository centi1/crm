import frappe
import requests
from frappe import _
from frappe.integrations.utils import create_request_log

from crm.integrations.api import find_contact_by_phone_number

# Endpoints for webhook
#
# Call status updates (our own bridge -> Frappe):
# <site>/api/method/crm.integrations.asterisk.handler.handle_request?key=<webhook-verify-token>
#
# The bridge is our own service (not a third-party vendor), so it reports status
# using the exact CRM Call Log status values directly - no vendor status mapping
# needed here, unlike the Exotel/Twilio integrations.


# Outgoing Call
@frappe.whitelist()
def make_a_call(to_number: str, from_number: str | None = None):
	if not is_integration_enabled():
		frappe.throw(_("Please setup Asterisk integration"), title=_("Integration Not Enabled"))

	if not from_number:
		from_number = frappe.db.get_value(
			"CRM Telephony Agent", {"user": frappe.session.user}, "asterisk_extension"
		)

	if not from_number:
		frappe.throw(
			_("You do not have an Asterisk Extension set in your Telephony Agent"),
			title=_("Extension Missing"),
		)

	settings = get_asterisk_settings()
	call_id = frappe.generate_hash(length=20)

	call_log_creation_failed = False
	try:
		response = requests.post(
			f"{settings.bridge_url.rstrip('/')}/call",
			json={
				"call_id": call_id,
				"agent_extension": from_number,
				"number": to_number,
				"record": bool(settings.record_call),
				"status_callback": get_status_updater_url(),
			},
			headers={"X-Api-Key": settings.get_password("bridge_api_key")},
			timeout=10,
		)
		response.raise_for_status()
	except requests.exceptions.RequestException as e:
		frappe.throw(_("Could not reach the Asterisk bridge: {0}").format(str(e)), title=_("Bridge Error"))

	try:
		create_call_log(
			call_id=call_id,
			from_number=from_number,
			to_number=to_number,
			call_type="Outgoing",
			agent=frappe.session.user,
			status="Initiated",
		)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Error while creating Asterisk call log")
		frappe.db.commit()
		call_log_creation_failed = True

	return {"CallSid": call_id, "call_log_creation_failed": call_log_creation_failed}


# Call status webhook (from our own ARI bridge)
@frappe.whitelist(allow_guest=True)
def handle_request(**kwargs):
	validate_request()
	if not is_integration_enabled():
		return

	request_log = create_request_log(
		kwargs,
		request_description="Asterisk Call",
		service_name="Asterisk",
		request_headers=frappe.request.headers,
		is_remote_request=1,
	)

	try:
		request_log.status = "Completed"
		call_payload = kwargs

		frappe.publish_realtime("asterisk_call", call_payload)

		call_id = call_payload.get("call_id")
		if not call_id:
			return

		if call_log := get_call_log(call_id):
			update_call_log(call_payload, call_log=call_log)
		elif call_payload.get("direction") == "incoming":
			create_call_log(
				call_id=call_id,
				from_number=call_payload.get("from_number"),
				to_number=call_payload.get("to_number"),
				call_type="Incoming",
				agent=call_payload.get("agent"),
				status=call_payload.get("status") or "Ringing",
			)
	except Exception:
		request_log.status = "Failed"
		request_log.error = frappe.get_traceback()
		frappe.db.rollback()
		frappe.log_error(title="Error while creating/updating Asterisk call record")
		frappe.db.commit()
	finally:
		request_log.save(ignore_permissions=True)
		frappe.db.commit()


def get_status_updater_url():
	from frappe.utils.data import get_url

	webhook_verify_token = frappe.db.get_single_value("CRM Asterisk Settings", "webhook_verify_token")
	return get_url(f"api/method/crm.integrations.asterisk.handler.handle_request?key={webhook_verify_token}")


def get_asterisk_settings():
	return frappe.get_single("CRM Asterisk Settings")


def validate_request():
	# Workaround for security since our own bridge is a plain HTTP client, same
	# pattern used by the Exotel integration (no request-signing support there either).
	webhook_verify_token = frappe.db.get_single_value("CRM Asterisk Settings", "webhook_verify_token")
	key = frappe.request.args.get("key")
	is_valid = key and key == webhook_verify_token

	if not is_valid:
		frappe.throw(_("Unauthorized request"), exc=frappe.PermissionError)


@frappe.whitelist()
def is_integration_enabled():
	return frappe.db.get_single_value("CRM Asterisk Settings", "enabled", True)


# Call Log Functions
def create_call_log(
	call_id,
	from_number,
	to_number,
	agent,
	status="Ringing",
	call_type="Incoming",
):
	call_log = frappe.new_doc("CRM Call Log")
	call_log.id = call_id
	call_log.to = to_number
	call_log.type = call_type
	call_log.status = status
	call_log.telephony_medium = "Asterisk"
	setattr(call_log, "from", from_number)

	if call_type == "Incoming":
		call_log.receiver = agent
	else:
		call_log.caller = agent

	# link call log with lead/deal
	contact_number = from_number if call_type == "Incoming" else to_number
	link(contact_number, call_log)

	call_log.save(ignore_permissions=True)
	frappe.db.commit()
	return call_log


def link(contact_number, call_log):
	contact = find_contact_by_phone_number(contact_number)
	if contact.get("name"):
		doctype = "Contact"
		docname = contact.get("name")
		if contact.get("lead"):
			doctype = "CRM Lead"
			docname = contact.get("lead")
		elif contact.get("deal"):
			doctype = "CRM Deal"
			docname = contact.get("deal")
		call_log.link_with_reference_doc(doctype, docname)


def get_call_log(call_id):
	if frappe.db.exists("CRM Call Log", call_id):
		return frappe.get_doc("CRM Call Log", call_id)


def update_call_log(call_payload, call_log=None):
	call_id = call_payload.get("call_id")
	call_log = call_log or get_call_log(call_id)
	try:
		if call_log:
			status = call_payload.get("status")
			if status:
				call_log.status = status

			if call_payload.get("to_number"):
				call_log.to = call_payload.get("to_number")

			if call_payload.get("duration") is not None:
				call_log.duration = call_payload.get("duration")

			if call_payload.get("recording_url"):
				call_log.recording_url = call_payload.get("recording_url")

			if call_payload.get("start_time"):
				call_log.start_time = call_payload.get("start_time")

			if call_payload.get("end_time"):
				call_log.end_time = call_payload.get("end_time")

			call_log.save(ignore_permissions=True)
			frappe.db.commit()
			return call_log
	except Exception:
		frappe.log_error(title="Error while updating Asterisk call record")
		frappe.db.commit()
