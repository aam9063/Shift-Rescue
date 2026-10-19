# Informe del proyecto Shift Rescue

**Documento de reconstrucción completa: planteamiento del problema, definición de
las especificaciones, paso a paso del desarrollo, iteraciones y decisiones de
system design.**

| | |
|---|---|
| **Proyecto** | Shift Rescue — agente de IA que cubre ausencias de última hora en negocios con turnos |
| **Repositorio** | `github.com/aam9063/Shift-Rescue` |
| **Periodo de construcción** | 24 de septiembre de 2026 → 1 de octubre de 2026 (8 días) |
| **Volumen** | 156 commits · 25 pull requests (26 merges) · 15 ramas de feature · 25 feature documents |
| **Código** | 10.410 líneas de backend (74 archivos) · 8.531 líneas de frontend · 2.785 líneas de documentación en `docs/` (ADRs incluidos) |
| **Pruebas** | 47 archivos de test backend · 25 de frontend · 15 escenarios de evaluación · 155 mensajes en el golden set |
| **Estado** | MVP funcional; dashboard, despliegue y pulido en progreso |

> **Sobre este documento.** Todo lo que sigue está reconstruido a partir de los
> artefactos reales del repositorio: `docs/SHIFT_RESCUE_SPEC.md`, los cuatro
> ADRs, los 25 feature documents de `odd/tasks/`, el historial de Git y
> `docs/eval-report.md`. Donde un dato proviene de una fuente concreta, se
> indica. Donde algo sigue pendiente, se dice que está pendiente.

---

## Índice

1. [Cómo se planteó el problema](#1-cómo-se-planteó-el-problema)
2. [Cómo se definieron las especificaciones](#2-cómo-se-definieron-las-especificaciones)
3. [El paso a paso, en orden real](#3-el-paso-a-paso-en-orden-real)
4. [Cómo se iteró](#4-cómo-se-iteró)
5. [Decisiones de system design y arquitectura](#5-decisiones-de-system-design-y-arquitectura)
6. [Estado actual, límites y deuda técnica](#6-estado-actual-límites-y-deuda-técnica)
7. [Métricas del proyecto](#7-métricas-del-proyecto)
8. [Índice de evidencia](#8-índice-de-evidencia)

---

## 1. Cómo se planteó el problema

### 1.1 El cliente ficticio y las notas de discovery

El proyecto parte de un cliente inventado pero verosímil: **Grupo Marea
Restauración**, un grupo de restauración con varios locales. El MVP se despliega
en uno solo, **La Terraza del Puerto**: un restaurante con unos 25 empleados
repartidos entre cocina (8), sala (9), barra (4), office (2) y encargados (2),
con turnos de mañana, tarde y noche, siete días a la semana.

Los hallazgos que definieron el problema (`docs/SHIFT_RESCUE_SPEC.md` §1.2) son
siete, y cada uno tiene consecuencias de diseño:

| Hallazgo de discovery | Consecuencia en el diseño |
|---|---|
| La ausencia se avisa con **menos de dos horas** de margen | El sistema debe resolver en minutos, no en días: oleadas de 10 minutos y plazo por defecto de 30 minutos antes del turno |
| El encargado pierde **30–60 minutos** entre mensajes y llamadas | La métrica de éxito es "minutos de encargado ahorrados", no "features entregadas" |
| No sabe quién está disponible, quién va justo de horas, quién cerró anoche | Hace falta un motor de elegibilidad que **explique** sus razones, no una caja negra |
| Llama **a los de siempre**, que acumulan horas extra y se queman | El ranking pondera equidad y existe un tope de coberturas por empleado en 14 días |
| El turno sin cubrir arranca corto: peor servicio, más estrés, peores reseñas | El valor se mide en el turno cubierto, no en la conversación con el agente |
| Los empleados **no usan email ni portal corporativo**: todo es WhatsApp | El canal no es una decisión técnica, es una restricción del negocio |
| El horario vive en su software de RR. HH. y **no quieren cambiarlo** | El producto es una capa sobre el sistema existente, nunca su reemplazo |

Estas notas se declaran explícitamente como **hipótesis de discovery**, no como
hechos: la spec indica que toda decisión que dependa de ellas se registre en
`docs/assumptions.md` para validarla después con clientes reales.

### 1.2 La tesis del producto

De esos siete hallazgos sale una frase que gobierna todo lo demás:

> **Shift Rescue es una capa de ejecución, no un sistema de registro.**

Es decir: el producto es dueño del **proceso** — el caso de rescate, las
ofertas, el rastro auditable — y no de la **verdad**, que es quién trabaja
cuándo. El horario sigue viviendo en el HRIS del cliente, que permanece como
autoridad; el agente escribe el cambio allí a través de un adaptador.

Esta frontera se eligió por costo de adopción. Si el producto exigiera migrar de
sistema e instalar una aplicación a 25 personas de operación, el costo de
adopción sería enorme para un problema que dura dos horas. Y si duplicara el
horario, tendría dos fuentes de verdad que divergen inevitablemente.

### 1.3 Qué se decidió dejar fuera, y por qué

La lista de exclusiones (`§3.2`) es tan deliberada como la de inclusiones:

| Excluido | Motivo |
|---|---|
| Generación y planificación de horarios | Es el trabajo del HRIS. Entrar ahí convierte al producto en competidor de los incumbentes y rompe la premisa de "funciona sobre lo que ya tenés" |
| Nómina, fichajes, cálculo salarial | Igual que el anterior, más exposición legal innecesaria |
| Integraciones reales con HRIS de terceros | En el MVP solo existe el adaptador y su implementación mock. Construir conectores reales antes de validar el flujo es pavimentar un camino que nadie caminó |
| Canal de voz o telefonía | El canal real del trabajador es WhatsApp; voz agrega superficie de fallo sin necesidad probada |
| **Registro del motivo de la ausencia** | Minimización de datos: no hace falta para decidir. Si el intérprete detecta detalles de salud, el cuerpo se redacta **antes** de persistirlo y nunca llega al manager, a los logs ni a las trazas |
| **Cualquier puntuación de "fiabilidad" del empleado** | Es alto riesgo bajo el Reglamento Europeo de IA y es una trampa de equidad: castiga a quien siempre dice que sí. La equidad se persigue al revés, protegiendo con un tope a quienes cubren mucho |
| El bucle autónomo del LLM | Pondría decisiones con peso legal detrás de comportamiento probabilístico (ver ADR-002) |
| Recordatorios de oferta | Un solo mensaje de oferta por empleado y rescate, como invariante: el agente no insiste |

### 1.4 Quién decide qué: la tabla que gobierna el diseño

La spec (§2.1) fija la distribución de autoridad antes de escribir código. Es la
tabla más importante del proyecto porque define dónde puede actuar el LLM:

| Decisión | Quién decide |
|---|---|
| Quién es elegible | **Código** (motor de elegibilidad, pura) |
| Orden de contacto | **Código** (ranking con pesos configurables) |
| Qué significa un mensaje | **LLM** (interpretación estructurada y validada) |
| Asignar un turno sin condiciones y sin horas extra | Código, tras una aceptación válida |
| Horas extra, coberturas parciales, cambios de horario | **Manager** |
| Cancelar un rescate porque el ausente al final sí va | **Manager** (el agente lo propone) |
| Qué hacer si no se cubre | **Manager** (el agente resume opciones) |

### 1.5 Los siete invariantes

Antes de implementar nada se fijaron siete invariantes que **nunca se relajan
para que pase un test** (§5.4):

1. Un turno nunca queda asignado a más de una persona.
2. Nunca se envía una oferta a un empleado no elegible.
3. Nunca se asigna algo que requiere aprobación sin aprobación del manager.
4. Nunca se envían ofertas en horas de silencio fuera de la excepción definida.
5. Nunca más de un mensaje de oferta por empleado y rescate.
6. Todo cambio de estado queda registrado en `AuditEvent`.
7. Ningún detalle de salud llega al manager, a los logs ni a las trazas.

Estos invariantes se comprueban en tests unitarios, en tests de integración **y
en cada escenario de evaluación**. Cero violaciones es condición de merge.

---

## 2. Cómo se definieron las especificaciones

### 2.1 Un único documento-contrato

La especificación (`docs/SHIFT_RESCUE_SPEC.md`, 726 líneas, 17 secciones) se
escribió **antes** del código y funciona como contrato de alcance. Su estructura
es deliberada:

| Sección | Contenido | Por qué importa |
|---|---|---|
| §0 | Rol, metodología y reglas del equipo | Define *cómo* se trabaja, no *qué* se construye |
| §1 | Contexto de negocio y tesis | El problema antes de la solución |
| §2 | Flujo principal y quién decide qué | Distribución de autoridad |
| §3 | Dentro y fuera del MVP | El alcance negativo explícito |
| §4 | Modelo de dominio y máquina de estados | El núcleo determinista |
| §5 | Reglas de negocio, invariantes y casos límite | Los siete invariantes y 13 casos límite con comportamiento esperado |
| §6 | Diseño del agente (uso del LLM) | Los tres bordes acotados |
| §7 | Arquitectura técnica | Stack, puertos, concurrencia, API, pantallas, estructura |
| §8 | Evaluación | Golden set, simulación, métricas, selección de modelo |
| §9 | Observabilidad, guardrails y degradación | Alertas, circuit breaker, pausa del agente |
| §10 | Privacidad y cumplimiento | Minimización, Reglamento Europeo de IA, retención |
| §11–§12 | Datos semilla, configuración y entornos | Reproducibilidad |
| §13 | Features de construcción y Definition of Done | El plan de trabajo, con 9 features |
| §14–§16 | KPIs, entregables y glosario | Cómo se mide el éxito |

Un detalle de método: la §13 no es una lista de tareas suelta, sino **nueve
features ordenadas por dependencia**, cada una con su Definition of Done. La spec
establece que tras la feature 1 los contratos quedan fijados y las features 2 a
6 pueden trabajarse en paralelo.

### 2.2 El protocolo de trabajo (spec §0)

La §0 define el ciclo de cada petición, en siete pasos:

1. **Authorize** — decidir si la petición autoriza cambios. Explicar, investigar
   o proponer es trabajo de solo lectura.
2. **Explore** — leer el código y la spec antes de tocar nada, en proporción a
   lo que se pide.
3. **Resolve uncertainty** — investigación solo para una incertidumbre concreta;
   como máximo una pregunta para una decisión de producto real, y como máximo un
   cuestionamiento de una premisa de alto impacto sin probar.
4. **Classify** — es trabajo sustancial si la exploración da dos o más pasos de
   implementación con sentido. El trabajo pequeño y entendido se hace sin
   artefactos.
5. **Track before the first write** — para trabajo sustancial, se crea el feature
   document antes de tocar el código.
6. **Implement task by task** — con TDD y cierre por work-unit commit.
7. **Close** — reportar resultado verificado, checks fallidos y siguiente paso.

Además, la spec fija la configuración de trabajo: **TDD activado** (RED
observado antes de implementar, después GREEN y REFACTOR), runners exactos
(`uv run pytest` en backend, `pnpm vitest run` en frontend), un tamaño
orientativo de ~400 líneas cambiadas por tarea o slice de PR, estrategia de
entrega `auto-chain` con `stacked-to-main`, y revisión recomendada basada en el
riesgo de cada work-unit commit. Commit, push y release siguen siendo decisión
humana.

### 2.3 Las reglas del equipo de agentes

La §0 también fija siete reglas que resuelven de antemano las ambigüedades
típicas de trabajar con agentes. Tres merecen destacarse:

- **Idioma**: código, nombres, commits, PRs y documentación técnica **en inglés**;
  los mensajes de WhatsApp a empleados y managers **en español (es-ES)** por
  defecto; la interfaz del dashboard en inglés.
- **Los invariantes de §5.4 nunca se relajan** para que pase un test o una eval.
- **Las dependencias que evolucionan rápido se fijan** a versión exacta
  (`strands-agents==1.56.0`), y antes de usar cualquier API suya se verifica en
  la documentación de esa versión — nunca de memoria.
- **No se inventan datos de personas reales**: todo es ficticio salvo los
  números de prueba unidos al sandbox de Twilio.

### 2.4 El log de supuestos

`docs/assumptions.md` registra cada decisión tomada sobre una premisa no probada
o bajo ambigüedad, con la opción conservadora elegida y cómo validarla después.
Contiene cinco entradas al cierre de este informe:

| # | Supuesto |
|---|---|
| A1 | Sustitución tipográfica: `SoDoSans` (propietaria) → **Inter** |
| A2 | Ancla de espaciado: se mantiene `1rem = 16px` en lugar del truco `62.5%` |
| A3 | Los tokens de diseño se bloquean con tests de contenido de archivo, porque jsdom no computa custom properties de forma fiable |
| A4 | **Langfuse Cloud** en lugar de self-hosted (instrucción del product owner), con el detalle de que la §9.1 original decía "self-hosted" y quedó enmendada |
| A5 | **OpenAI** como primer proveedor de LLM (créditos disponibles, baja latencia), con `anthropic` y `bedrock` implementados pero opcionales y el SDK de Anthropic deliberadamente **no** como dependencia dura |

El log cumple una función doble: documenta la decisión y deja escrito qué habría
que revisar antes de un despliegue real.

### 2.5 Los ADRs: decisiones con alternativas rechazadas

Las decisiones de arquitectura que son entregables del portfolio se escriben
además como ADR en `docs/adr/`. Se escribieron **cuatro**:

| ADR | Decisión | Fecha |
|---|---|---|
| ADR-001 | Stack de la fundación | 2026-09-24 |
| ADR-002 | Strands sin bucle autónomo; LLM en los bordes, dominio a cargo | 2026-09-24 |
| ADR-003 | Despliegue del demo en AWS (una EC2 + Langfuse Cloud) | 2026-09-25 |
| ADR-004 | Selección de proveedor de LLM: OpenAI primero, *fail-closed* al parser | 2026-09-25 |

Lo distintivo es que cada ADR incluye una sección de **alternativas rechazadas**
con el motivo. No son documentos que justifican lo hecho, son documentos que
registran lo descartado.

### 2.6 Los feature documents: la unidad de trabajo

Cada feature de la §13 se convierte en un documento en `odd/tasks/<nombre>.md`.
Se crearon **25**, y todos comparten la misma estructura:

```
# Feature: <nombre>
**Status**: closed | in progress
**Branch**: `feature/<nombre>`
**Spec references**: §... (las secciones de la spec que implementa)
**Design system**: DESIGN.md §... (cuando aplica)

## Problem          ← qué duele, con evidencia de que duele
## Decisions (fixed, do not re-litigate)   ← lo ya decidido, para no reabrir
## Tareas / checklist con IDs estables
## Evidencia de verificación y commits
```

Dos secciones merecen explicación, porque son las que hacen que el método
funcione:

- **Problem con evidencia.** No describe una feature, describe un defecto o una
  necesidad observada. Ejemplo real del feature `demo-readiness`: *"el reloj de
  demo no tiene vuelta atrás; un offset residual encontrado en +18 h 50 m movía
  el 'ahora' de todo el worker"*. Eso es un hallazgo, no una idea.
- **"Decisions (fixed, do not re-litigate)".** Evita el ciclo de reabrir
  decisiones ya tomadas, que es el modo más común de perder tiempo con agentes.

### 2.7 La Definition of Done como criterio de aceptación

Cada feature de la §13 trae su DoD, y el feature document copia esos criterios
como criterios de aceptación. Algunos ejemplos textuales de la spec:

- **foundation**: *"un agente nuevo puede clonar, ejecutar `make up && make seed`
  y ver la API respondiendo"*.
- **domain-rules**: *"cobertura ≥ 95 % en `domain/`, tests de propiedad con
  Hypothesis para descanso y solapes, todos los motivos de exclusión con código
  estable"*.
- **llm-interpreter**: *"intent accuracy ≥ 0.92 en el golden set, detección de
  detalles de salud ≥ 0.95, informe en `evals/reports/`"*.
- **evals-observability**: *"todos los escenarios mínimos pasan con 0
  violaciones de invariantes; una traza de Langfuse muestra un rescate completo
  de principio a fin"*.
- **deploy-delivery**: *"URL pública del dashboard en modo demo, pipeline
  completo en verde, README que un recruiter entiende en 60 segundos y un
  ingeniero en 5 minutos"*.

---

## 3. El paso a paso, en orden real

La cronología siguiente está reconstruida del historial de merges de Git (25
pull requests y 26 merges en total, entre el 24 de septiembre y el 1 de octubre
de 2026) y del estado de cada feature document.

### 3.1 Fase 0 — Andamiaje (PR #1–#3, 24 de septiembre)

Rama `dev` como integración y `main` como estable. El repositorio arranca con la
estructura de monorepo de la §7.7: `backend/`, `frontend/`, `infra/`, `docs/`,
`evals/`, `odd/tasks/`, `scripts/`.

**Detalle a destacar:** el PR #2 fue `feature/manager-dashboard`, *antes* de la
foundation del backend. La razón está en el feature `foundation`: *"the frontend
foundation exists (see manager-dashboard feature, slices 1-4)"*. Es decir, el
frontend y su contrato visual (`DESIGN.md`) se adelantaron al backend. La
consecuencia apareció más tarde y está documentada en el feature `dashboard-api`:
*"the dashboard is a complete UI with no HTTP client: every screen renders mock
data"*. El orden no fue un error, pero sí una deuda que hubo que pagar en la fase
de integración.

### 3.2 Feature `foundation` (PR #4)

Monorepo con Docker Compose (api, worker, beat, postgres, redis, y langfuse
detrás de un perfil opcional), `make up` funcional, CI con lint y tests vacíos en
verde, runners de TDD configurados. Cierra con ADR-001.

Decisión de secuenciación registrada en el ADR: **posponer la separación de
esquemas de PostgreSQL** (`workforce_mock`, `rescue`) a la migración de
`domain-rules`, para que las migraciones de la fundación fueran triviales.

### 3.3 Feature `domain-rules` (PR #5) — cerrado

El núcleo determinista, como código puro y sin I/O:

- `domain/entities.py` — las entidades
- `domain/eligibility.py` (208 líneas) — el motor de elegibilidad con códigos de
  razón estables: `REST_VIOLATION`, `MAX_WEEKLY_HOURS`, `MAX_COVERAGES_14D`
- `domain/ranking.py` (104 líneas) — puntuación ponderada con empates
  deterministas por id
- `domain/state_machine.py` (171 líneas) — 8 estados, 15 eventos, 10 efectos
- `domain/quiet_hours.py` (34 líneas) — la excepción de horas de silencio
- Contratos de `Channel`, `Scheduler`, `WorkforceAdapter` y `LLMClient`

DoD cumplida: cobertura del 100 % en `app/domain/`, con tests de propiedad de
Hypothesis para las reglas de descanso y solape (frontera de exactamente 12 h,
turnos que cruzan medianoche, cambio de horario de verano).

### 3.4 Feature `rescue-orchestration` (PR #6) — cerrado

`services/orchestrator.py`, que hoy tiene **2.740 líneas**: el corazón del
sistema. Incluye `SimScheduler`, `SimulatedChannel`, `MockWorkforceAdapter`,
oleadas, plazos, horas de silencio, concurrencia e idempotencia. El intérprete
queda sustituido, deliberadamente, por un **parser determinista**.

DoD cumplida: los casos límite de la §5.5 en verde, incluida la carrera de
aceptaciones contra PostgreSQL real (`tests/integration/test_race.py`).

Ese test merece un comentario: es el único archivo de integración del proyecto, y
contiene los dos tests más críticos —`test_acceptance_race_has_single_winner` y
`test_duplicate_provider_message_id_is_idempotent_on_postgres`—. Verifica el
bloqueo transaccional y la restricción única parcial, que son las dos redes que
impiden que un turno quede asignado a dos personas.

### 3.5 Feature `llm-interpreter` (PR #7) — cerrado

`agent/factory.py`, `agent/interpreter.py`, `agent/llm.py`, `agent/schemas.py` y
los prompts versionados. El `LLMClient` sobre Strands con trazas, medición de
coste, reintentos y circuit breaker. Cierra con **ADR-002**: Strands sin el bucle
autónomo, el `Agent` como llamada única con salida estructurada y **sin
herramientas**, y el parser determinista como respaldo degradado.

Se implementa la política de validación completa: revalidación con Pydantic, un
reintento con el error de validación incluido, y `UNCLEAR` si vuelve a fallar.

### 3.6 Feature `evals-observability` (PR #8) — cerrado

El harness de evaluación y la observabilidad. Se crean los 15 escenarios YAML,
las personas simuladas, los evaluadores y el `ShiftRescueTarget` que expone el
sistema completo a las evals. La división de responsabilidades queda fijada aquí:
los invariantes, el reloj simulado, el runner y los umbrales son **código propio
y determinista**; la parte probabilística (jueces, simuladores, diagnóstico)
viene de Strands Evals.

Se configura además la exportación OTLP a Langfuse y la redacción de teléfonos.

### 3.7 Feature `manager-dashboard` (PR #9, y rediseño posterior) — cerrado

Las nueve pantallas de la §7.6: Today, Rescue detail, Approvals, Ops, Settings,
Demo simulator, Conversations, Agent decisions y Evals. El status final del
feature document dice *"slices 1-3 closed; slice 4 (redesign) closed"* — hubo un
rediseño de una porción del dashboard, lo que confirma que la iteración de
interfaz fue explícita y no accidental.

### 3.8 Feature `whatsapp-channel` (PR #10) — código completo, verificado en vivo

`TwilioWhatsAppChannel`, validación de firmas, callbacks de estado y las
plantillas de mensajes. El status es literal: *"code complete and verified live
up to Twilio's trial outbound limit"*. La limitación es del proveedor, no del
código, y está documentada en `docs/twilio-sandbox-setup.md`.

### 3.9 Feature `deploy-delivery` (PR #11) — en progreso

`infra/docker-compose.prod.yml`, `infra/Caddyfile`, `infra/deploy/bootstrap-ec2.sh`
y `infra/deploy/remote-deploy.sh`, con el workflow `deploy.yml` que construye,
publica en ECR y despliega por SSH. Cierra con **ADR-003**.

La decisión central: **una sola EC2 t3.large** con Docker Compose y Caddy, no un
despliegue serverless, porque Celery necesita procesos persistentes. Y Langfuse
Cloud en lugar de self-hosted, que elimina tres contenedores (Langfuse,
ClickHouse y su Postgres) y permite bajar de t3.xlarge a t3.large.

### 3.10 Feature `resilience` (PR #12) — cerrado

Modo degradado, pausa del agente, inyección de fallos en el adaptador y en el
LLM, límites de envío y purga por retención. Los escenarios `llm_down_degraded`
y `hris_failure_escalates` pasan, y el dashboard refleja el modo degradado.

### 3.11 Fase de correcciones (PR #13–#19)

Entre el 25 y el 28 de septiembre aparecen los primeros merges que no son
features nuevas, sino reparaciones:

| PR | Rama | Qué corrige |
|---|---|---|
| #13 | `fix/compose-secret-scan` | Falsos positivos del escáner de secretos en el compose |
| #15 y #18 | `fix/ui-english-copy` | Textos de la interfaz al inglés (regla de idioma de la §0) |
| #16 | `fix/deploy-workflow-guard` | Guarda en el workflow de despliegue |

Este patrón —67 commits `feat` contra 27 `fix`— es la señal más honesta de cómo
fue el desarrollo: la mayoría del trabajo fue construcción, y una cuarta parte,
reparación de lo construido.

### 3.12 El hallazgo de `llm-runtime-wiring` (PR #20) — un defecto latente

Este es uno de los momentos más interesantes del proyecto. El feature document
lo dice sin adornos:

> *"The LLM layer is implemented and tested, but **nothing wires it into the
> runtime**"*.

Concretamente: la API construía el orquestador **sin intérprete**, así que cada
mensaje real de WhatsApp lo respondía el parser determinista. `StrandsLLMClient`
existía pero ningún código de producción construía un modelo real. El módulo de
trazas podía describir atributos de span pero ningún `TracerProvider` se
instalaba, así que nada se exportaba a Langfuse. Y el `.env` tenía variables
(`LLM_PROVIDER_INTERPRETER`, `NAN_*`, `LANGFUSE_*`) **que ningún código leía**.

Es decir: todas las features estaban cerradas y con sus DoD cumplidas, y el
sistema en producción seguía sin usar el LLM. Cierra con **ADR-004**, que fija la
política: OpenAI como primer proveedor, una única factoría, resolución de
credenciales solo desde `Settings`, y **fail-closed al parser determinista** —
un LLM mal configurado degrada *calidad*, nunca *disponibilidad*.

### 3.13 El defecto que destapó cablear el LLM: `webhook-offload` (PR #21)

Inmediatamente después aparece la consecuencia en cascada, y el feature document
la describe con precisión:

> *"Wiring the LLM exposed a deviation from spec §7.5 that was invisible while
> the webhook only ran the deterministic parser."*

El webhook hacía `await orchestrator.handle_inbound()`, así que pasaba a bloquear
1–3 segundos en la llamada de interpretación, cuando la spec exige responder en
menos de 200 ms y **nunca** llamar al LLM dentro del webhook. Además, la
orquestación vivía en el proceso de la API — que es también la razón por la que
los timeouts de oleada se manejaban con un ticker `asyncio` en el *lifespan* de
FastAPI.

Esta es la mejor ilustración de por qué el proyecto insiste en correr el sistema
de punta a punta: **dos features verdes y con tests podían esconder una desviación
arquitectónica hasta que se cableó la pieza que faltaba**.

### 3.14 `dashboard-live` (PR #22) — la deuda del mock

La rama más larga, con el mayor número de features abiertas: `dashboard-api`,
`demo-simulator`, `manager-can-act`, `state-aware-replies`, `responsive-dashboard`,
`interpretation-persistence`, `broker-owned-timers`, `handle-what-the-agent-asks`,
`evals-live` y `demo-readiness`.

Aquí se paga la deuda de haber construido el frontend primero. `dashboard-api`
lo declara: *"the dashboard is a complete UI with **no HTTP client**: every
screen renders mock data"*. Y los demás documentos son hallazgos del uso real
del producto:

- `manager-can-act`: *"the user drove the product and could not use it. Five
  verified defects turn the manager's flow into a dead end."*
- `broker-owned-timers`: *"timers never fire in the deployed stack, so no rescue
  ever escalates."*
- `state-aware-replies`: *"when the agent cannot act on a message it answers with
  one generic line."*
- `realtime-events`: *"the dashboard is pull-only… a change produced elsewhere
  stays invisible until the manager refocuses the tab. The user called this out
  ('no es tiempo real') and agreed to defer it."*
- `demo-readiness`: el caso del reloj de demo sin vuelta atrás, con un offset
  residual de +18 h 50 m que movía el "ahora" de todo el worker.

### 3.15 `realtime-and-polish` (PR #24) — en progreso

Tiempo real por WebSocket y una ronda de pulido. El diseño de la solución de
tiempo real es notablemente conservador y vale la pena citarlo: el socket
**solo le dice a las pantallas qué volver a pedir** — cada tipo de evento mapea a
las mismas claves de consulta que las acciones ya invalidaban, "so nothing is
duplicated in the client cache". Y degrada como el resto: los estados
`connecting | live | offline` se renderizan, y un cierre 4401 limpia la sesión
igual que un 401.

---

## 4. Cómo se iteró

### 4.1 La iteración del intérprete: cinco versiones con números

La parte más medible de la iteración es el intérprete. Cada versión del prompt se
evaluó contra el golden set y quedó registrada en `docs/eval-report.md`:

| Versión | Intent accuracy | Detección de salud | Tiempos condicionales | Veredicto |
|---|---|---|---|---|
| Parser determinista (offline) | 0.3733 | 0.0 | 0.0 | Piso informativo, nunca bloquea |
| `gpt-4o-mini`, **v1** | 0.86 | 0.9167 | 0.95 | **2 violaciones** (intent < 0.92, salud < 0.95) |
| `gpt-4o-mini`, **v2** | 0.9333 | 1.0 | 0.85 | Umbrales cumplidos |
| `gpt-4o-mini`, **v3** | 0.9867 | 1.0 | **0.75** | **1 violación** (tiempos < 0.80): arregló las retiradas, rompió los tiempos |
| `gpt-4o-mini`, **v4** | 0.9933 | 1.0 | 1.0 | Umbrales cumplidos con 1 fallo restante |
| `gpt-4o-mini`, **v5** (155 muestras) | **0.9935** | **1.0** | **0.95** | **Umbrales cumplidos, 1 fallo restante** |

Lo valioso no es la progresión, es **lo que cada salto enseña**:

- **v2** añadió un procedimiento de decisión explícito apoyado en el contexto que
  el harness ya provee (primero ofertas pendientes, después confirmación
  pendiente, después nada), respuestas numéricas solo cuando hay algo pendiente,
  una regla de salud más amplia y ejemplos resueltos de las confusiones que
  expuso la corrida de v1.
- **v3** agregó el marcador de oferta aceptada: el orquestador pasa
  `accepted_offers`, de modo que una cancelación con oferta aceptada es una
  retirada y no una adivinanza. **Arregló los seis casos de retirada y rompió los
  tiempos (0.75).** Los umbrales lo atraparon: la iteración no fue lineal, fue un
  trade-off entre capacidades.
- **v4** corrigió el ejemplo del propio prompt. Todos los prompts desde v1
  afirmaban que `"hasta mediodía puedo"` debía llenar `proposed_start 07:00` y
  `proposed_end 12:00`, cuando el golden set espera `start=null, end=12:00`. **El
  ejemplo contradecía las etiquetas que supuestamente enseñaba, y el modelo seguía
  el ejemplo.** v4 enuncia la regla que los datos codifican: una sola frontera
  llena exactamente un campo.
- **v5** resolvió el caso de "¿de cuál te das de baja?": los candidatos pasaron a
  enviarse con fecha (`<shift_id> <rol> <YYYY-MM-DD> <HH:MM>-<HH:MM>`) y el
  orquestador añadió un ancla `[today=YYYY-MM-DD]`, porque sin fecha el modelo no
  tenía forma de mapear "el de hoy" sobre un candidato.

Un detalle de rigor: **v5 se editó en el lugar** en vez de crear una v6, con este
argumento: *"ADR-002's versioning rule exists to keep shipped prompts
attributable, and inflating versions for an unreleased prompt would not improve
attribution."* La regla de versionado existe para atribuir prompts publicados; un
prompt que nunca se publicó no gana nada con inflar versiones.

### 4.2 La corrección del fixture: un caso de sobreajuste detectado y evitado

El golden set tenía seis filas de `OFFER_WITHDRAW` con **exactamente el mismo
contexto** que las de `OFFER_DECLINE`: `{"pending_offers": ["offer_1"]}`. La
única forma de distinguirlas era una regla léxica sobre "al final", que es
**sobreajuste al prompt, no una capacidad real**.

La respuesta del proyecto fue corregir el mundo descrito por el fixture en lugar
de forzar el modelo: cada fila de `OFFER_WITHDRAW` ahora lleva
`"accepted_offers": ["offer_1"]`, que el orquestador provee como clave de
contexto. Las etiquetas esperadas quedaron **idénticas byte a byte**; solo cambió
el estado descrito. El eval-report es explícito: *"The fixture described an
incomplete world state for those labels"*.

### 4.3 El guardián del contrato de contexto

De aquel episodio salió un test que es el mejor activo del harness:

> `test_llm_context_contract_exact_key_set` fija, por estado, el conjunto exacto
> de claves que el orquestador envía y las cadenas exactas de los candidatos. Es
> el test que habría atrapado los tres desajustes de fixture/producción que esta
> feature corrigió (marcador de retirada, confirmación pendiente, lista de
> turnos): los fixtures describen el contexto que producción debe enviar, y el
> test falla en el momento en que cualquiera de los dos lados se desvía.

Es la respuesta estructural a un problema recurrente: en lugar de confiar en que
el fixture y la producción coincidan, se fija el contrato y se falla ruidosamente
cuando divergen.

### 4.4 Los catorce defectos encontrados durante el desarrollo

El informe de evals documenta una tabla de catorce defectos reales con su causa
raíz y su corrección. No son hipotéticos: la mayoría se encontró **corriendo el
sistema de punta a punta**, no con tests unitarios. Los más instructivos:

| # | Defecto | Causa raíz | Lección |
|---|---|---|---|
| 1 | Descansos mal calculados en el cambio de horario | CPython devuelve la diferencia **naive** al restar dos datetimes con el **mismo** objeto `tzinfo` | El bug más sutil del proyecto; lo cubre un test de propiedad en la frontera de DST |
| 2 | Pérdida silenciosa de datos en tests | SQLite en memoria + `StaticPool` con sesiones anidadas: un commit interno invalida la transacción externa | Los harness de test usan bases en archivo temporal |
| 3 | El plazo del rescate escalaba demasiado pronto | `max(start-30min, opened+10min)` en lugar de la regla real de la §5.3 | Una fórmula plausible no es una especificación |
| 4 | Las ofertas de la oleada 1 desaparecían al arrancar la 2 | La implementación expiraba ofertas previas; la §5.3 las mantiene vivas | El timeout de oleada solo envía la siguiente, no invalida la anterior |
| 5 | La transacción de confirmación hacía rollback **después** de enviar los mensajes | IDs compuestos que superaban `VARCHAR(64)` | Los IDs son basados en UUID; un test verifica que todo ID persistido tenga ≤ 64 caracteres |
| 6 | Los timeouts de oleada nunca disparaban en la API desplegada | El `SimScheduler` en memoria nunca se avanzaba fuera del harness de evals | El *lifespan* de FastAPI ahora corre `run_due` cada 5 s |
| 7 | El webhook de Twilio devolvía **403** detrás del túnel | La firma se validaba contra la URL interna `http://api:8000` en vez de la pública | Validar contra la URL pública reenviada (`X-Forwarded-Proto/Host`) |
| 8 | Twilio reportaba **12300** en cada mensaje entrante | El webhook respondía sin `Content-Type` | Los endpoints responden TwiML vacío (`application/xml`) |
| 9 | Un destinatario rechazado tumbaba el webhook entero (500) | El error del proveedor se propagaba fuera del bucle de oleada | Los fallos de entrega se auditan, ese candidato se cancela y la oleada sobrevive |
| 12 | El gate de precisión imprimía **"Thresholds met."** con dos umbrales violados | Las claves terminaban en `_min`/`_max` y el reporte guardaba las métricas sin el sufijo, así que cada comparación se saltaba; **el YAML nunca se leía** | Los umbrales se movieron a código, leen el YAML y **fallan cerrado** |
| 13 | Los ejemplos del prompt contradecían las etiquetas y costaban 5 de 20 extracciones de tiempo | El ejemplo de `"hasta mediodía puedo"` llenaba `proposed_start` mientras las etiquetas esperan `null` | El modelo siguió el ejemplo, no la regla |
| 14 | Un test pasaba en local y fallaba en CI | `build_runtime(settings)` ignoraba sus propios settings para la base y caía al `.env` ambiente | El runtime pasa `settings.database_url` explícitamente |

Los defectos 12 y 14 son los que más dicen del método. El 12 es un gate de
calidad que **pasaba en silencio**: durante un tiempo el proyecto creyó que sus
umbrales bloqueaban cuando en realidad nunca se evaluaban. El 14 es el clásico
"funciona en mi máquina" —el test se conectaba a la base local del
desarrollador— y su corrección es hacer explícito lo que estaba implícito.

### 4.5 Cómo se descubrieron las cosas: uso por encima de tests

Un patrón se repite en los feature documents de la última etapa. Las citas
textuales lo muestran:

- *"Two things make the demo unusable or confusing, **found by using it**"*
  (`demo-readiness`)
- *"The user drove the product and could not use it"* (`manager-can-act`)
- *"The user called this out ('no es tiempo real')"* (`realtime-events`)
- *"Timers never fire in the deployed stack"* (`broker-owned-timers`)

Ninguno de esos hallazgos habría aparecido en una suite verde: los tests pasaban.
Aparecieron al usar el producto, y por eso la fase final del proyecto es una fase
de uso intensivo con el usuario manejando el dashboard y reportando lo que no
funcionaba.

### 4.6 Las iteraciones que no fueron de código

El proyecto también iteró sobre documentos:

- La §9.1 de la spec decía "Langfuse self-hosted" y quedó **enmendada** por la
  instrucción del product owner (A4), aplicando la regla de la §0 sobre cambios
  de alcance: *"si una revisión cambia la intención, se actualizan juntas la
  intención y las tareas afectadas"*.
- El `.env.example` perdió las variables `NAN_*` y `LLM_PROVIDER_INTERPRETER`
  cuando se comprobó que **ningún código las leía** (A5). Limpiar la configuración
  muerta fue parte de la iteración.
- Los tokens de diseño se estabilizaron con tests de contenido de archivo en
  lugar de tests de estilo computado (A3), con la limitación documentada.

---

## 5. Decisiones de system design y arquitectura

### 5.1 La arquitectura, en una imagen

El camino en tiempo de ejecución de una ausencia, de punta a punta:

![Flujo de rescate de una ausencia: WhatsApp entra como webhook a FastAPI, que persiste y encola en Redis; el worker de Celery orquesta el rescate, consulta al proveedor de LLM para interpretar el mensaje, persiste cada transición en PostgreSQL y vuelve a salir por WhatsApp con las ofertas de la oleada. El SPA del manager opera por REST + JWT](frontend/public/img/shift-rescue-absence-rescue-flow.png)

Lo que el diagrama deja ver de un vistazo, y que son decisiones de diseño, no
detalles de implementación:

- El **webhook solo persiste y encola**: la llamada no espera al LLM (la regla de
  responder en menos de 200 ms que destapó el feature `webhook-offload`).
- La **orquestación corre en el worker de Celery**, no en el proceso de la API.
- El **LLM se consulta desde el worker**, y solo como borde de interpretación:
  no tiene herramientas que muten estado (ADR-002).
- **Cada transición se persiste** en PostgreSQL antes de continuar.
- El **bucle punteado** de la izquierda es la respuesta: el worker vuelve a salir
  por WhatsApp para ofrecer el turno a los candidatos.

El mapa completo del sistema incluye tres cosas que este diagrama de flujo
deliberadamente no dibuja, para no perder legibilidad: el **adaptador del HRIS**
(la frontera con el sistema que el cliente ya usa), el **motor de elegibilidad y
ranking** como código puro, y la **exportación de trazas** a Langfuse. Ese mapa
completo es este:

```
WhatsApp (Twilio) ──webhook──> FastAPI ──enqueue──> Celery workers ──> Rescue Orchestrator
                                  │                        │               │
                                  │                        │               ├─> Eligibility / Ranking (puro)
Dashboard (React) <──WebSocket────┤                        │               ├─> LLM agents (Strands SDK)
                                  │                        │               ├─> Channel (Twilio | Simulado)
                                  └──REST──> PostgreSQL <──┘               └─> WorkforceAdapter (Mock HRIS)
                                                 ▲
                              Redis (broker, locks, pub/sub)   Langfuse (trazas)   Sentry
```

### 5.2 ADR-001: el stack, y por qué

| Capa | Elección | Motivo registrado |
|---|---|---|
| Lenguaje | Python 3.12 con `uv` | Ecosistema estándar para agentes; `uv` da resolución rápida y reproducible |
| API | FastAPI + Uvicorn | Async, contratos tipados con Pydantic v2, WebSockets nativos |
| ORM | SQLAlchemy 2.0 async + Alembic | Control fino de transacciones; hace falta `SELECT ... FOR UPDATE` para las carreras de aceptación |
| Base de datos | PostgreSQL 16 | Transacciones, **restricciones únicas parciales** (una oferta ACCEPTED por rescate), jsonb |
| Colas | Celery + Redis | Workers persistentes para oleadas, timeouts y reintentos; Redis además actúa de almacén de locks y pub/sub para el WebSocket |
| Agentes | Strands Agents SDK fijado, **sin el bucle autónomo** | Abstracción de proveedor, salida estructurada, hooks y OpenTelemetry nativo; la orquestación sigue siendo propia |
| Frontend | React 19 + TypeScript + Vite + Tailwind v4 + TanStack Query | Establecido en las features previas de frontend |
| Observabilidad | structlog (JSON), OpenTelemetry → Langfuse, Sentry | Una traza por rescate con coste y latencia |
| Pruebas | pytest + pytest-asyncio + Hypothesis; Vitest + RTL | Tests de propiedad para los casos de frontera de elegibilidad |
| Despliegue | EC2 + Docker Compose + Caddy, imágenes en ECR, secretos en SSM, GitHub Actions con OIDC | La forma más barata de tener workers persistentes; el camino a servicios gestionados queda documentado |

**Consecuencias asumidas y registradas en el ADR:** una sola cadena de
herramientas de Python (`uv run pytest` es el único runner de backend y el CI lo
replica); el stack de Compose es el contrato entre backend y frontend
(`make up && make seed` debe dejar siempre una API funcionando); y Langfuse viaja
detrás de un perfil de Compose hasta que la feature de observabilidad cablea la
exportación.

### 5.3 ADR-002: el LLM no maneja — la decisión más importante del proyecto

Es la decisión que define todo lo demás. El contexto registrado: el SDK de
Strands está diseñado alrededor de un bucle dirigido por el modelo donde el LLM
razona, elige herramientas e itera hasta cumplir un objetivo. Pero el flujo de
rescate es una máquina de estados determinista cuyas transiciones **tienen peso
legal**: un turno, una persona; ninguna asignación sin aprobación del manager;
ninguna oferta en horas de silencio.

> *"An LLM in the loop with tools that mutate state would put invariant-critical
> decisions behind probabilistic behavior, and the preassembled harness brings
> capabilities (web search, fetch) that only widen the attack surface."*

Seis decisiones concretas:

1. **Sin bucle autónomo.** La máquina de estados es el único orquestador. El
   `Agent` de Strands se usa exclusivamente como llamada de salida estructurada a
   un solo tiro, **sin herramientas adjuntas**.
2. **El LLM en tres bordes acotados**: interpretación de mensajes, redacción de
   respuestas en sesión y resúmenes de escalado.
3. **Toda salida validada.** Revalidación con Pydantic, un reintento incluyendo el
   error de validación, y `UNCLEAR` ante fallo repetido o caída del proveedor. El
   orquestador trata `UNCLEAR` como una petición de aclaración, nunca como una
   acción.
4. **El parser determinista es el respaldo degradado.** Cuando el circuit breaker
   se abre, el sistema sigue funcionando.
5. **Fijado de versión exacta** (`strands-agents==1.56.0`), con verificación de
   API contra la documentación de esa versión, nunca de memoria.
6. **Sin perfilado de comportamiento.** El intérprete ve el mensaje y contexto
   mínimo; el historial de respuestas o las tasas de aceptación **nunca** entran
   en los prompts ni en el ranking.

**Consecuencias**: cambiar de proveedor es configuración (el `Agent` recibe un
`model`); el coste y la latencia por interpretación se capturan y se exportan como
atributos de traza; y los prompts son archivos versionados cuya versión se guarda
con cada `Interpretation` para poder atribuir resultados.

### 5.4 ADR-003: por qué una EC2 y por qué Langfuse Cloud

**El contexto:** el stack necesita workers persistentes (Celery worker y beat) y
una base de datos, así que un enfoque puramente serverless no alcanza para el
demo. Y la especificación original asumía un Langfuse self-hosted, que trae
ClickHouse, su propio Postgres y Redis.

La decisión se apoya en una tabla de ahorro que vale la pena reproducir porque es
un argumento de negocio, no de gusto:

| | Langfuse self-hosted | Langfuse Cloud (elegido) |
|---|---|---|
| Contenedores en la instancia | 6 de aplicación + 3 de Langfuse | 6 |
| RAM extra necesaria | ~8 GB solo para ClickHouse y Langfuse | ~2 GB |
| Tamaño de instancia | t3.xlarge (4 vCPU / 16 GB) | **t3.large (2 vCPU / 8 GB)** |
| Coste on-demand (eu-west-1) | ~0,1664 $/h ≈ **121 $/mes** | ~0,0832 $/h ≈ **61 $/mes** |
| Mantenimiento del almacén de trazas | nuestro | de Langfuse |

Es decir: **la mitad del coste de cómputo**, un sistema con estado menos que
operar, y enlaces de traza que un revisor puede abrir. Además, el dominio queda
tan aislado que el camino a producción (ECS Fargate, RDS, ElastiCache, ALB + ACM)
está documentado pero no construido: los puertos y adaptadores ya lo permiten.

Otros detalles de esta decisión: dominio **sslip.io** (sin comprar dominio; Caddy
obtiene un certificado válido de Let's Encrypt y cambiarlo a un dominio real es un
valor en `.env`), secretos en **SSM Parameter Store** con la instancia
descartable, y **OIDC** para que no haya claves de AWS de larga vida en el
repositorio.

### 5.5 ADR-004: el proveedor de LLM y la política de fallo

El contexto es el hallazgo descrito en §3.12: la capa LLM estaba implementada y
probada, pero ningún camino de producción construía un modelo real.

| Aspecto | Decisión | Motivo |
|---|---|---|
| Proveedor por defecto | `openai`, modelo `gpt-4o-mini` | Créditos disponibles, baja latencia p95, salida estructurada fiable |
| Superficie de proveedores | `openai`, `anthropic`, `bedrock` tras una única factoría | Cambiar de proveedor es una variable de entorno |
| Gateways compatibles con OpenAI | **No** son un proveedor aparte: `LLM_PROVIDER=openai` + `OPENAI_BASE_URL` | Un segundo camino de código sería lógica duplicada sin garantía adicional |
| Resolución de credenciales | Solo desde `Settings` (Pydantic Settings), nunca `os.getenv` en el punto de uso | Un único lugar tipado para auditar |
| Política de fallo | **Fail closed al parser determinista** | Un LLM mal configurado debe degradar calidad, nunca disponibilidad |
| Forma del agente | `Agent` de Strands **sin herramientas**, con `structured_output_model` | ADR-002 |
| Latencia objetivo | **p95 < 2,5 s**, medido | La cifra anterior de 1,2 s era un mockup sin medir |

**Alternativas rechazadas y sus motivos** (registradas en el ADR): dejar el parser
como único camino vivo (seguro, pero la promesa central del producto —entender
español coloquial por WhatsApp— sería falsa en el demo); implementar un proveedor
`nan` aparte (lógica duplicada para un endpoint compatible); fallar rápido al
arrancar si faltan credenciales (convierte un error de configuración en una caída);
usar el SDK de Langfuse en lugar de OpenTelemetry (segundo camino de
instrumentación y no captura los spans de Strands); e instrumentar las llamadas
al modelo a mano (Strands ya emite spans; los envoltorios manuales se desviarían
del SDK).

### 5.6 Las decisiones de diseño que no llegaron a ADR

Hay un conjunto de decisiones igualmente determinantes que viven en la spec y en
el código, sin documento propio:

**1. Todo lo impuro es un `Protocol`.** Cinco puertos, cada uno con su
implementación real y su falsa:

| Puerto | Producción | Test/simulación |
|---|---|---|
| `Clock` | `SystemClock` | `FakeClock` — el dominio **jamás** llama a `datetime.now()` |
| `Scheduler` | `CeleryScheduler` | `SimScheduler` (cola en memoria) |
| `Channel` | `TwilioWhatsAppChannel` | `SimulatedChannel` |
| `WorkforceAdapter` | `MockWorkforceAdapter` | con inyección de fallos y latencia |
| `LLMClient` | `StrandsLLMClient` | `ReplayLLMClient` |

El dominio **nunca importa Strands**: solo conoce el Protocol. Esto es lo que
permite que un rescate de 40 minutos simulados corra en milisegundos, y es de
donde salen el simulador de demo y los escenarios de evaluación.

**2. La máquina de estados es pura.** `transition(state, event) ->
TransitionResult(nuevo_estado, efectos)`; los efectos se ejecutan **fuera**,
después de persistir. Y un par (estado, evento) no definido **lanza
`UndefinedTransition` y alerta**, nunca se ignora en silencio.

**3. La concurrencia se resuelve en dos capas.** Primero el código: transacción
con `SELECT ... FOR UPDATE`, revalidación de elegibilidad y cambio de estado.
Después la base de datos como red de seguridad: **restricción única parcial** que
garantiza una sola oferta aceptada por rescate. El código primero, la base como
respaldo.

**4. El webhook responde en menos de 200 ms.** Valida firma, inserta el mensaje
con `provider_message_id` único (si ya existe, 200 y fin — idempotencia gratis),
encola y responde. **El LLM nunca corre dentro del webhook.** Esta regla existía
desde la spec y su violación fue lo que destapó `webhook-offload`.

**5. Los efectos externos van después del commit.** Enviar un mensaje o asignar en
el HRIS ocurre con el estado ya persistido, con patrón outbox si el tiempo
alcanza.

**6. Los invariantes se verifican con código determinista, nunca con un juez
LLM.** La división es explícita: los invariantes, el reloj simulado, el runner de
escenarios y los umbrales de CI son código propio; Strands Evals aporta la parte
probabilística. Un fallo de invariante nunca depende de la opinión de un modelo.

**7. La redacción de salud ocurre antes de persistir.** No es una capa de
presentación: si el intérprete marca `contains_health_details`, el cuerpo se
redacta antes de escribirse en la base, y no llega al manager, ni a Langfuse, ni
a los logs.

**8. La equidad se resuelve con un tope, no con una puntuación.** El ranking
pondera equidad y el motor aplica `max_coverages_per_14_days`, en lugar de
construir un perfil de comportamiento por empleado —que sería alto riesgo legal y
una trampa de equidad.

**9. El sistema de mensajería separa lo generado de lo plantillado.** Los
mensajes iniciados por la empresa (ofertas, avisos) usan **plantillas fijas**, no
texto generado por el LLM. Doble motivo: WhatsApp exige plantillas aprobadas fuera
de la ventana de 24 h, y elimina riesgo en el mensaje más importante. El redactor
con LLM se reserva para respuestas dentro de una conversación activa, y su salida
se revalida antes de enviar.

**10. Todo se degrada con elegancia.** Circuit breaker del LLM → modo degradado
con plantilla `offer_degraded` y parser determinista; pausa del agente por local;
fallos del HRIS con backoff exponencial y escalado con motivo técnico. En todos
los casos se sigue cubriendo el turno aunque el proveedor esté caído.

### 5.7 El modelo de dominio y su separación

Dos esquemas de base de datos, y la separación es una decisión de diseño, no una
convención de nombres:

- **`workforce_mock`** simula el HRIS del cliente (`Location`, `Employee`,
  `Shift`, `AvailabilityBlock`). El agente **solo** accede a través del adaptador.
- **`rescue`** es propiedad del agente (`RescueCase`, `Offer`, `Conversation`,
  `Message`, `Interpretation`, `ApprovalRequest`, `AuditEvent`, `Manager`,
  `LocationSettings`, `EvalRun`).

El detalle más importante es `AuditEvent`: es la **fuente del timeline del
dashboard**. No se reconstruye la historia a partir de otras tablas; se escribe
como evento con actor (`system`, `llm`, `employee:<id>`, `manager:<id>`). Eso hace
que el invariante 6 sea verificable de forma trivial y que la auditoría sea una
consulta.

### 5.8 La decisión de evaluación: por qué un harness y no solo tests

La evaluación se diseñó en tres capas con responsabilidades separadas:

1. **Golden set offline** — 155 mensajes etiquetados (el informe registra 150
   como mínimo exigido) con contexto y cobertura obligatoria de aceptaciones,
   rechazos, condicionales en formatos variados, ambiguos, retiradas, preguntas,
   emojis sueltos, faltas y abreviaturas, detalles de salud, intentos de
   manipulación y mensajes en inglés.
2. **Simulación de extremo a extremo** — 15 escenarios YAML que montan la
   aplicación real con `FakeClock`, `SimScheduler`, `SimulatedChannel` y el mock
   del HRIS, con **personas** simuladas: `quick_yes`, `slow_yes`, `polite_no`,
   `ghost`, `ambiguous`, `conditional`, `flaky`, `racer`, `manipulator` y
   `oversharer`. Las que necesitan precisión temporal (la carrera, la retirada)
   usan guion determinista; las que necesitan lenguaje natural usan simuladores
   con semilla fija.
3. **Regresión y selección de modelo** — umbrales que bloquean, con los valores
   numéricos en `evals/thresholds.yaml` (intent accuracy ≥ 0,92, detección de
   salud ≥ 0,95, tiempos condicionales ≥ 0,80, latencia media ≤ 5000 ms, coste
   medio ≤ 0,05 $), más las dos condiciones que la spec fija en su §8.4: cero
   violaciones de invariantes y puntuación de juez ≥ 4,0.

Y una regla de gobierno: **no se cambia de proveedor por coste si la exactitud o
la tasa de validación empeoran**. La comparación de modelos alimenta una tabla que
justifica la elección en un ADR, no una decisión por intuición.

---

## 6. Estado actual, límites y deuda técnica

### 6.1 Lo que está cerrado

- `foundation`, `frontend-foundation`, `domain-rules`, `rescue-orchestration`,
  `llm-interpreter`, `interpreter-quality`, `evals-observability`, `resilience`,
  `polish-round`, y `manager-dashboard` (sus cuatro slices).
- `whatsapp-channel`: código completo y **verificado en vivo** hasta el límite de
  envío de la cuenta de prueba de Twilio (limitación del proveedor, documentada).

### 6.2 Lo que está en progreso

`deploy-delivery`, `dashboard-api`, `manager-can-act`, `demo-simulator`,
`demo-readiness`, `state-aware-replies`, `responsive-dashboard`,
`interpretation-persistence`, `broker-owned-timers`, `handle-what-the-agent-asks`,
`evals-live`, `realtime-events` y `llm-runtime-wiring` (T1–T6 completos; T7, la
verificación en vivo con un modelo real, pendiente).

### 6.3 Deuda y límites reconocidos

El propio informe de evals los lista en su sección de huecos conocidos:

1. **El `SimScheduler` pierde temporizadores en vuelo si el worker se reinicia.**
   Los plazos de oleada sobrevivirán a un reinicio recién cuando el calendario
   viva en la base de datos. Celery beat ya es el camino de producción (cada 5 s
   `run-due-jobs`, más una purga diaria por retención).
2. **La prueba de aceptación con dos teléfonos reales** necesita un segundo número
   unido al sandbox; todo lo demás está verificado en vivo.
3. **`make eval-models`** (comparación Anthropic vs Bedrock vs NaN) está preparado
   pero pendiente de claves.
4. **El único archivo de tests de integración se saltea sin `DATABASE_URL`**, y el
   CI no aprovisiona PostgreSQL: la frontera de concurrencia se verifica solo en
   la máquina del desarrollador.
5. **El gate de cobertura no corre en CI**: `fail_under = 95` está configurado y
   limitado a `app/domain`, pero el workflow ejecuta `uv run pytest` sin `--cov`.
   Solo `make test-backend` lo aplica.
6. **El dashboard no tiene tests de navegador**: la DoD de la feature de dashboard
   pedía una prueba de Playwright del flujo de demo completo, y no está escrita.
7. **Las evals no bloquean en CI**: los umbrales existen y bloquean localmente,
   pero el workflow solo corre el baseline informativo del parser.
8. **Un fallo del golden set sigue abierto** (`"cancele el caso de todos"`,
   esperado `UNCLEAR`): está registrado como pendiente, no ajustado al modelo.

---

## 7. Métricas del proyecto

### 7.1 Volumen

| Métrica | Valor |
|---|---|
| Commits | 156 |
| Pull requests fusionados | 25 (más 1 merge de `origin/dev`) |
| Ramas de feature | 15 |
| Feature documents | 25 |
| ADRs | 4 |
| Backend | 10.410 líneas en 74 archivos Python |
| Frontend | 8.531 líneas |
| Documentación | 2.785 líneas en `docs/` (ADRs incluidos) |
| Archivos de test | 47 (backend) + 25 (frontend) |
| Escenarios de evaluación | 15 |
| Filas del golden set | 155 |
| Prompts versionados del intérprete | 5 (v1 → v5) |

### 7.2 Composición de los commits

| Tipo | Cantidad |
|---|---|
| `feat` | 67 |
| `fix` | 27 |
| `docs` | 22 |
| `test` | 6 |
| `chore` | 4 |

### 7.3 Últimos resultados registrados

Según `docs/eval-report.md` en su última ejecución:

| Suite | Comando | Resultado |
|---|---|---|
| Unit backend | `uv run pytest` | 435 pasados, 2 salteados |
| Integración (PostgreSQL real) | `pytest tests/integration -m integration` | 2 pasados |
| Gate de cobertura del dominio (≥95 %) | `uv run pytest --cov` | **100 %** en `app/domain/` |
| Frontend | `pnpm vitest run` | 119 pasados |
| Lint y tipos | `ruff`, `mypy` estricto, `oxlint` | limpio |
| Escenarios | `pytest tests/unit/evals` | **15 escenarios verdes, 0 violaciones de invariantes** |

### 7.4 La ventana temporal

Todo el proyecto se construyó entre el **24 de septiembre y el 1 de octubre de
2026**, con la mayor densidad el 24 y el 25 de septiembre (21 de los 25 PRs). El
28 y 29 de septiembre corresponden a la fase de integración, tiempo real y pulido,
que es donde aparecieron la mayoría de los defectos de uso descritos en §4.5.

---

## 8. Índice de evidencia

| Artefacto | Ruta | Contenido |
|---|---|---|
| Especificación | `docs/SHIFT_RESCUE_SPEC.md` | 16 secciones: negocio, alcance, dominio, reglas, agente, arquitectura, evals, privacidad, features y DoD |
| System design | `docs/system-design.md` | El recorrido técnico completo |
| ADR-001 | `docs/adr/ADR-001-foundation-stack.md` | Stack de la fundación y sus consecuencias |
| ADR-002 | `docs/adr/ADR-002-strands-without-autonomous-loop.md` | Strands sin bucle autónomo; LLM en los bordes |
| ADR-003 | `docs/adr/ADR-003-deployment-aws.md` | EC2, Caddy, ECR, SSM, OIDC y Langfuse Cloud con la tabla de costes |
| ADR-004 | `docs/adr/ADR-004-llm-provider-selection.md` | Selección de proveedor y política de fallo cerrado |
| Informe de evals | `docs/eval-report.md` | Resultados, iteración de prompts v1–v5 y los 14 defectos encontrados con su causa raíz |
| Supuestos | `docs/assumptions.md` | Cinco decisiones sobre premisas no probadas, con cómo validarlas |
| Runbook | `docs/runbook.md` | Operación y configuración |
| Guion de demo | `docs/demo-script.md` | El flujo de demostración |
| Sandbox de Twilio | `docs/twilio-sandbox-setup.md` | Limitaciones del proveedor y cómo sortearlas |
| Feature documents | `odd/tasks/*.md` | 25 documentos con problema, decisiones fijas, checklist y evidencia |
| Pipeline de desarrollo | `docs/agentic-pipeline.md` | Cómo se construyó el proyecto con agentes |
| Escenarios | `evals/scenarios/*.yaml` | 15 escenarios de extremo a extremo |
| Umbrales | `evals/thresholds.yaml` | Los gates numéricos de calidad |
| Diseño visual | `DESIGN.md` | Sistema de diseño y contrato responsivo |
| Infraestructura | `infra/` | Compose de desarrollo y producción, Caddyfile, scripts de despliegue |
| CI | `.github/workflows/ci.yml` | Lint, tipos, tests y build en ambos stacks |

---

*Informe generado a partir del estado del repositorio al 1 de octubre de 2026.
Las cifras de pruebas y cobertura provienen de la última ejecución registrada en
`docs/eval-report.md`; las de estructura y volumen, de una medición directa sobre
el árbol de trabajo.*
