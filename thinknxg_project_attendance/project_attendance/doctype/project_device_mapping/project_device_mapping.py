from frappe.model.document import Document


class ProjectDeviceMapping(Document):
    def validate(self):
        self.device_id = (self.device_id or "").strip()
