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
    "state_searching_coverage": (
        "Vale {employee_name}, tu ausencia del turno de {role} de {start} a "
        "{end} ya está registrada y estoy buscando a alguien que te cubra. "
        "No tienes que hacer nada más."
    ),
    "state_awaiting_approval": (
        "Gracias, {employee_name}. Ya hay quien cubra tu turno de {role} de "
        "{start} a {end}, solo falta que el encargado lo confirme. Te digo "
        "algo en cuanto resuelva."
    ),
    "offer_reminder": (
        "Hola {employee_name}, sigue abierta la propuesta de cubrir el turno "
        "de {role} de hoy de {start} a {end}. Responde SÍ o NO, o dime hasta "
        "qué hora puedes."
    ),
    "ask_which_shift": (
        "Vale {employee_name}, veo varios turnos hoy: {shift_list}. ¿De cuál te "
        "das de baja?"
    ),
    "ask_clarification": (
        "No te he entendido bien. ¿Me lo repites? Responde SÍ o NO."
    ),
    "state_case_escalated": (
        "Vale {employee_name}, tu ausencia del turno de {role} de {start} a {end} ya "
        "está registrada. No llegamos a confirmarla a tiempo, así que se la he pasado "
        "a tu encargado para que se ocupe de cubrirla. No tienes que hacer nada más."
    ),
    "state_case_covered": (
        "Buenas noticias, {employee_name}: tu turno de {start} a {end} ya está cubierto. "
        "No tienes que hacer nada más."
    ),
    "state_case_closed": (
        "{employee_name}, tu aviso del turno de {start} a {end} quedó cerrado por tu "
        "encargado. Para cualquier cosa, habla directamente con él."
    ),
    "out_of_scope": (
        "Hola, soy el asistente de turnos de {location_name} y solo gestiono "
        "avisos de ausencia y coberturas. Para cualquier otra cosa, contacta "
        "con tu encargado."
    ),
    "manager_agent_paused": (
        "{employee_name} ha escrito: \"{message}\". El agente está en pausa en "
        "{location_name}, así que lo dejo en tus manos."
    ),
    "manager_escalated": (
        "No se ha podido cubrir el turno de {role} de {start} a {end}. "
        "Te dejo el resumen en el panel: revisa a quién contacté y qué opciones "
        "quedan."
    ),
    "manager_covered": (
        "{employee_name} cubrirá el turno de {role} de {start} a {end}."
    ),
    "manager_cancel_requested": (
        "{employee_name} dice que al final sí puede ir al turno de {role} de "
        "{start} a {end}. ¿Cancelamos el rescate? Respóndeme en el panel."
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
