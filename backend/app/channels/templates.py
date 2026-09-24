"""WhatsApp message templates (es-ES, spec §6.6).

Company-initiated messages use fixed templates — never generated text.
"""

from typing import Any

_TEMPLATES: dict[str, str] = {
    "absence_confirm": (
        "Vale {employee_name}, ¿confirmas que no vas al turno de {role} de hoy "
        "de {start} a {end}? Responde SÍ o NO."
    ),
    "absence_ack": (
        "Recibido, que te mejores. Ya me encargo de buscar a alguien para "
        "cubrirte, no tienes que hacer nada más."
    ),
    "offer": (
        "Hola {employee_name}, soy el asistente de turnos de {location_name}. "
        "Ha quedado libre un turno de {role} hoy de {start} a {end}. "
        "¿Puedes cubrirlo? Responde SÍ o NO, o dime si puedes solo una parte."
    ),
    "offer_confirmed": (
        "¡Genial, {employee_name}! El turno de {start} a {end} es tuyo. "
        "Ya está actualizado en tu horario. ¡Gracias!"
    ),
    "offer_pending_approval": (
        "Gracias, {employee_name}. Se lo paso a {manager_name} para que lo "
        "confirme y te digo algo en unos minutos."
    ),
    "offer_already_covered": (
        "Gracias por responder, {employee_name}. El turno ya se ha cubierto, "
        "¡gracias igualmente!"
    ),
    "ask_which_shift": (
        "Vale {employee_name}, veo varios turnos hoy: {shift_list}. ¿De cuál te "
        "das de baja?"
    ),
    "out_of_scope": (
        "Hola, soy el asistente de turnos de {location_name} y solo gestiono "
        "avisos de ausencia y coberturas. Para cualquier otra cosa, contacta "
        "con tu encargado."
    ),
    "manager_rescue_opened": (
        "{employee_name} no puede ir al turno de {role} de {start} a {end}. "
        "He avisado a {offered_count} compañeros y te cuento en cuanto haya "
        "novedades."
    ),
}


def render(template_key: str, **params: Any) -> str:
    template = _TEMPLATES[template_key]
    return template.format(**params)
