"""SimulatedChannel (spec §7.3): records outbound messages for the demo
simulator and the eval harness. No external calls.
"""

from typing import Any


class SimulatedChannel:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(
        self,
        recipient_phone_e164: str,
        body: str,
        *,
        template_key: str | None = None,
        rescue_id: str | None = None,
    ) -> str:
        self.sent.append(
            {
                "to": recipient_phone_e164,
                "body": body,
                "template_key": template_key,
                "rescue_id": rescue_id,
            }
        )
        return f"prov_{len(self.sent)}"

    def with_template(self, template_key: str) -> list[dict[str, Any]]:
        return [m for m in self.sent if m["template_key"] == template_key]

    def to(self, phone: str) -> list[dict[str, Any]]:
        return [m for m in self.sent if m["to"] == phone]
