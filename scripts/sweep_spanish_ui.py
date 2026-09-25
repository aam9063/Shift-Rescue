"""One-off sweep: finds Spanish-looking UI string literals in the frontend.

Usage: cd frontend/src && python ../../scripts/sweep_spanish_ui.py
Kept in the repo as a small guard for the English-only UI rule (spec §0 rule 1).
"""

import io
import os
import re

# Words that indicate Spanish UI copy (WhatsApp message bodies are the
# intentional exception: employee/manager facing, es-ES per spec).
SPANISH = re.compile(
    r"\b(hoy|ayer|mensaje[s]?|emplead[oa]s?|confianza|modelo|coste|latencia|"
    r"atascad[oa]|fallo|entrega|tasa|umbral|barra|sala|cocina|limpieza|"
    r"encargad[oa]|oleada[s]?|silencio|guardar|pendiente[s]?|rescate[s]?|"
    r"ajustes|equidad|proximidad|preferencia|vacaciones|puede[s]?|puedo|"
    r"responde|gracias|recuerda|resumen|ultima|eventos|encuentro|fatal|"
    r"desde|hasta)\b",
    re.IGNORECASE,
)
LITERAL = re.compile(r"'([^'\n]{3,})'|\"([^\"\n]{3,})\"|`([^`\n]{3,})`")
SKIP_PREFIXES = ("*", "//", "import", "export type", "className", "@")
WHATSAPP_CONTENT_FILE = "./services/dashboardMock.ts"


def main() -> None:
    findings = 0
    for root, _, files in os.walk("."):
        if "node_modules" in root:
            continue
        for name in sorted(files):
            if not name.endswith((".ts", ".tsx")) or ".test." in name:
                continue
            path = os.path.join(root, name).replace(os.sep, "/")
            for lineno, line in enumerate(
                io.open(path, encoding="utf8").read().split("\n"), 1
            ):
                if line.strip().startswith(SKIP_PREFIXES):
                    continue
                for match in LITERAL.finditer(line):
                    value = match.group(1) or match.group(2) or match.group(3) or ""
                    if not SPANISH.search(value):
                        continue
                    findings += 1
                    tag = "WHATSAPP-OK" if path == WHATSAPP_CONTENT_FILE else "REVIEW"
                    print(f"[{tag}] {path}:{lineno} {value[:80]}")
    print(f"total strings flagged: {findings}")


if __name__ == "__main__":
    main()
