# Copyright (c) 2026, Athen Automobiles and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CRMAsteriskSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from crm.fcrm.doctype.crm_asterisk_inbound_number.crm_asterisk_inbound_number import (
			CRMAsteriskInboundNumber,
		)

		agent_ring_seconds: DF.Int
		bridge_api_key: DF.Password | None
		bridge_url: DF.Data | None
		enabled: DF.Check
		escalation_endpoint: DF.Data | None
		escalation_ring_seconds: DF.Int
		inbound_numbers: DF.Table[CRMAsteriskInboundNumber]
		max_agent_attempts: DF.Int
		record_call: DF.Check
		webhook_verify_token: DF.Data | None
	# end: auto-generated types

	def validate(self):
		if self.enabled and not self.bridge_url:
			frappe.throw(_("Bridge URL is required to enable Asterisk telephony."))
