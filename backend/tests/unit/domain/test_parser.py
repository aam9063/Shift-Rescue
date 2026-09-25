"""Unit tests for the deterministic message parser (degraded mode, spec §9.3).

Feature 2 replaces the LLM interpreter with this parser: it only recognizes
an explicit vocabulary and clear absence phrasing; everything else is UNCLEAR
and never triggers actions.
"""

import pytest

from app.domain.parser import Intent, parse_message


class TestOfferVocabulary:
    @pytest.mark.parametrize(
        "text", ["sí", "si", "SÍ", "vale", "ok", "Ok", "1", "👍", "confirmo", "voy"]
    )
    def test_confirmation_words(self, text: str) -> None:
        parsed = parse_message(text)
        assert parsed.intent == Intent.CONFIRM
        assert parsed.confidence == 1.0

    @pytest.mark.parametrize("text", ["no", "NO", "2", "nop", "no gracias"])
    def test_decline_words(self, text: str) -> None:
        parsed = parse_message(text)
        assert parsed.intent == Intent.DECLINE
        assert parsed.confidence == 1.0


class TestAbsencePhrasing:
    @pytest.mark.parametrize(
        "text",
        [
            "buenas, me he levantado fatal, hoy no puedo ir",
            "me encuentro mal, no voy a poder ir hoy",
            "estoy enfermo, no llego",
            "hoy no voy a poder ir",
            "no puedo ir hoy",
            "no voy hoy",
        ],
    )
    def test_absence_report(self, text: str) -> None:
        parsed = parse_message(text)
        assert parsed.intent == Intent.ABSENCE_REPORT
        assert parsed.confidence >= 0.9

    def test_absence_report_normalizes_case_and_accents(self) -> None:
        parsed = parse_message("NO PUEDO IR")
        assert parsed.intent == Intent.ABSENCE_REPORT

    def test_retraction_after_confirmation(self, ) -> None:
        parsed = parse_message("al final sí puedo ir")
        assert parsed.intent == Intent.ABSENCE_RETRACT


class TestAmbiguity:
    @pytest.mark.parametrize(
        "text",
        [
            "igual sí, luego te digo",
            "¿a qué hora era?",
            "quien es esto?",
            "jajaja",
            "",
            "hola",
        ],
    )
    def test_unclear_messages_never_trigger_actions(self, text: str) -> None:
        parsed = parse_message(text)
        assert parsed.intent == Intent.UNCLEAR
        assert parsed.confidence < 0.75


def test_parser_never_sees_health_details_as_intent() -> None:
    """Health content stays inside the text; the parser only reports ABSENCE_REPORT."""
    parsed = parse_message("me encuentro fatal, migraña horrible, hoy no puedo ir")
    assert parsed.intent == Intent.ABSENCE_REPORT
    assert "migraña" not in repr(parsed.intent)

class TestConditionalExtraction:
    def test_quarter_past_seven(self) -> None:
        parsed = parse_message("llego a las 7 y cuarto")
        assert parsed.proposed_start == "07:15"

    def test_half_past_six(self) -> None:
        parsed = parse_message("llego a las 6 y media")
        assert parsed.proposed_start == "06:30"

    def test_range(self) -> None:
        parsed = parse_message("puedo de 9 a 15 si")
        assert parsed.proposed_start == "09:00"
        assert parsed.proposed_end == "15:00"

    def test_until(self) -> None:
        parsed = parse_message("hasta mediodia puedo")
        # "mediodía" is not numeric: stays UNCLEAR-ish without times
        assert parsed.proposed_end is None

    def test_afternoon_disambiguation(self) -> None:
        parsed = parse_message("llego a las 7:15 de la tarde")
        assert parsed.proposed_start == "19:15"

    def test_from(self) -> None:
        parsed = parse_message("puedo a partir de las 12")
        assert parsed.proposed_start == "12:00"
