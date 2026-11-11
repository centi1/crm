"""Where was this photo taken? (Athen, user 2026-11-11, first for AGEPL's solar site visits.)

Every image attached to a CRM Lead / Deal gets coordinates on its File record:
1. from the photo's EXIF GPS tags when the camera wrote them, read from the upload bytes before
   Frappe strips the metadata from the stored copy (privacy setting kept on); WhatsApp-forwarded
   images have none (WhatsApp strips EXIF), else
2. from the browser's position at upload time, which the CRM uploader sends right after the
   upload (`set_file_location`), labelled "Upload location".
The lead / deal keeps the latest photo's position in `photo_latitude` / `photo_longitude` (editable:
the user may correct them; the Google Maps link `photo_map_link` is recomputed on save) and, when
its `location` (detailed address) is still empty, the address found for those coordinates
(OpenStreetMap Nominatim reverse geocoding, else the coordinates themselves). The attachments
panel shows a map pin per file. Territory (largest area) and Place (the town) are not touched.

Custom fields are created on migrate (`after_migrate` hook), so every group site has them.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt

PARENTS = ("CRM Lead", "CRM Deal")
IMAGE_TYPES = {"JPG", "JPEG", "PNG", "WEBP", "TIFF", "TIF", "HEIC", "HEIF"}
CUSTOM_FIELDS = {
	"File": [
		dict(fieldname="photo_location_section", label="Photo Location", fieldtype="Section Break", insert_after="attached_to_field",
			collapsible=1),
		dict(fieldname="latitude", label="Latitude", fieldtype="Float", precision="7", insert_after="photo_location_section", read_only=1),
		dict(fieldname="longitude", label="Longitude", fieldtype="Float", precision="7", insert_after="latitude", read_only=1),
		dict(fieldname="location_source", label="Location Source", fieldtype="Select", options="\nPhoto EXIF\nUpload location",
			insert_after="longitude", read_only=1),
		dict(fieldname="photo_taken_on", label="Photo Taken On", fieldtype="Datetime", insert_after="location_source", read_only=1),
		dict(fieldname="map_link", label="Map", fieldtype="Data", options="URL", insert_after="photo_taken_on", read_only=1),
	],
}
for _dt in PARENTS:
	CUSTOM_FIELDS[_dt] = [
		dict(fieldname="photo_location_section", label="Photo Location", fieldtype="Section Break", insert_after="lost_notes", collapsible=1),
		dict(fieldname="photo_latitude", label="Latitude", fieldtype="Float", precision="7", insert_after="photo_location_section",
			description="From the latest photo; correct it here if needed"),
		dict(fieldname="photo_longitude", label="Longitude", fieldtype="Float", precision="7", insert_after="photo_latitude"),
		dict(fieldname="photo_map_link", label="Open in Map", fieldtype="Data", options="URL", insert_after="photo_longitude",
			read_only=1, in_list_view=1, description="Google Maps link for the coordinates above"),
	]


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True)


def maps_url(lat, lng):
	return f"https://www.google.com/maps?q={flt(lat):.6f},{flt(lng):.6f}"


def is_photo(file_doc) -> bool:
	return bool(file_doc.attached_to_doctype in PARENTS and file_doc.attached_to_name
		and (file_doc.file_type or "").upper() in IMAGE_TYPES)


def _dms_to_degrees(value, ref):
	degrees = flt(value[0]) + flt(value[1]) / 60 + flt(value[2]) / 3600
	return -degrees if ref in ("S", "W") else degrees


def read_exif_location(source):
	"""(lat, lng, taken_on) from the image's EXIF, or None. `source` is a path or the image bytes."""
	try:
		import io

		from PIL import Image

		with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as im:
			exif = im.getexif()
			if not exif:
				return None
			gps = exif.get_ifd(0x8825) or {}
			if 2 in gps and 4 in gps:  # GPSLatitude / GPSLongitude with their refs (1 / 3)
				lat = _dms_to_degrees(gps[2], gps.get(1, "N"))
				lng = _dms_to_degrees(gps[4], gps.get(3, "E"))
				taken = exif.get(306) or (exif.get_ifd(0x8769) or {}).get(36867)  # DateTime / DateTimeOriginal
				taken_on = None
				if taken:
					try:
						taken_on = frappe.utils.get_datetime(str(taken).replace(":", "-", 2))
					except Exception:
						taken_on = None
				if abs(lat) <= 90 and abs(lng) <= 180 and (lat or lng):
					return lat, lng, taken_on
	except Exception:
		frappe.log_error("photo location: EXIF read failed", frappe.get_traceback())
	return None


def reverse_geocode(lat, lng) -> str | None:
	"""Street address for coordinates (OpenStreetMap Nominatim; free, 1 request/s, needs a User-Agent)."""
	try:
		import requests

		r = requests.get("https://nominatim.openstreetmap.org/reverse",
			params={"lat": f"{flt(lat):.6f}", "lon": f"{flt(lng):.6f}", "format": "jsonv2", "zoom": 18, "addressdetails": 0},
			headers={"User-Agent": "AthenGroupCRM/1.0 (frappe crm; photo location)", "Accept-Language": "en"}, timeout=6)
		if r.ok:
			return (r.json() or {}).get("display_name") or None
	except Exception:
		pass
	return None


def _store(file_doc, lat, lng, source, taken_on=None):
	file_doc.db_set({"latitude": lat, "longitude": lng, "location_source": source, "photo_taken_on": taken_on,
		"map_link": maps_url(lat, lng)}, update_modified=False)
	parent_dt, parent = file_doc.attached_to_doctype, file_doc.attached_to_name
	if parent_dt in PARENTS and frappe.db.exists(parent_dt, parent):
		values = {"photo_latitude": lat, "photo_longitude": lng, "photo_map_link": maps_url(lat, lng)}
		meta = frappe.get_meta(parent_dt)
		if meta.has_field("location") and not (frappe.db.get_value(parent_dt, parent, "location") or "").strip():
			values["location"] = reverse_geocode(lat, lng) or f"{flt(lat):.6f}, {flt(lng):.6f}"
		frappe.db.set_value(parent_dt, parent, values, update_modified=False)


def update_map_link(doc, method=None):
	"""CRM Lead / Deal validate: the map link always matches the (possibly hand-corrected) coordinates."""
	if not doc.meta.has_field("photo_map_link"):
		return
	lat, lng = flt(doc.get("photo_latitude")), flt(doc.get("photo_longitude"))
	if (lat or lng) and abs(lat) <= 90 and abs(lng) <= 180:
		doc.photo_map_link = maps_url(lat, lng)
	else:
		doc.photo_map_link = None


def capture_location(doc, method=None):
	"""File after_insert: EXIF GPS of a photo attached to a lead / deal."""
	if not is_photo(doc) or not frappe.get_meta("File").has_field("latitude"):
		return
	# Frappe strips EXIF from the STORED jpeg (System Settings "strip EXIF metadata from uploaded images",
	# on by default and left on for privacy), so read the tags from the original upload bytes:
	# doc.content (programmatic insert / upload_file) or frappe.local.uploaded_file (web upload),
	# and only then from the stored file (older uploads, other storage backends).
	found = None
	for source in (doc.get("content"), getattr(frappe.local, "uploaded_file", None)):
		if isinstance(source, bytes) and source[:3] == b"\xff\xd8\xff":
			found = read_exif_location(source)
			if found:
				break
	if not found:
		try:
			found = read_exif_location(doc.get_full_path())
		except Exception:
			found = None
	if found:
		_store(doc, found[0], found[1], "Photo EXIF", found[2])


@frappe.whitelist()
def set_file_location(file: str, latitude: float, longitude: float, accuracy: float | None = None):
	"""Browser position at upload time (the CRM uploader calls this after an image upload).
	Never overrides coordinates that came from the photo itself."""
	doc = frappe.get_doc("File", file)
	doc.check_permission("write")
	if not is_photo(doc):
		return {"stored": False, "reason": "not a photo on a lead or deal"}
	if doc.get("location_source") == "Photo EXIF":
		return {"stored": False, "reason": "photo carries its own GPS"}
	lat, lng = flt(latitude), flt(longitude)
	if not (lat or lng) or abs(lat) > 90 or abs(lng) > 180:
		return {"stored": False, "reason": "invalid coordinates"}
	_store(doc, lat, lng, "Upload location", frappe.utils.now_datetime())
	return {"stored": True, "map_link": maps_url(lat, lng), "accuracy": cint(accuracy) if accuracy else None}
