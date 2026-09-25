# Shift Rescue — resumen para CV

> Documento de una página pensado para que una IA lo convierta en viñetas de CV.
> El proyecto está en su repositorio público; este archivo resume qué es, qué
> problema resuelve, qué se construyó y con qué stack.

## Qué es

**Shift Rescue** es un agente de IA que cubre automáticamente las ausencias de
última hora en negocios con turnos (hostelería, retail, staffing). Funciona por
WhatsApp, encima del sistema de RRHH que ya usa el cliente, y mantiene siempre
al manager en control de las decisiones.

## El problema que resuelve

Cuando alguien avisa de que no puede ir a su turno, casi siempre es con menos de
dos horas de margen y por WhatsApp. El encargado, en plena operación, pierde
entre 30 y 60 minutos escribiendo y llamando para cubrir el hueco: no sabe quién
está disponible, quién va justo de horas ni quién cerró anoche. Si no lo cubre,
el servicio arranca con menos gente.

## Qué construí

Producto completo, de punta a punta, diseñado como software de producción:

- **Detección de la ausencia** por WhatsApp (canal real con Twilio) y desde el
  panel del manager, con confirmación explícita del empleado.
- **Motor de elegibilidad y ranking determinista**: rol, solapes, descanso
  mínimo entre turnos, topes semanales de horas, bloques de no disponibilidad y
  protección contra quemar a los mismos empleados.
- **Orquestación del rescate** como máquina de estados: apertura del caso,
  ofertas en oleadas, plazos, horas de silencio, concurrencia segura
  (aceptaciones simultáneas: gana una sola persona) e idempotencia de mensajes.
- **Aprobaciones del manager**: horas extra, coberturas parciales y cambios de
  horario nunca se asignan sin una decisión humana.
- **Intérprete de lenguaje con LLM** acotado a tres puntos concretos
  (interpretar mensajes, redactar respuestas en conversación y resumir
  escalados), siempre con salida estructurada validada y sin capacidad de
  modificar el estado del sistema.
- **Dashboard del manager** en tiempo real: tablero del día, detalle del rescate
  con timeline y candidatos, bandeja de aprobaciones, métricas de coste y
  latencia, inspector de decisiones del agente, resultados de evaluaciones,
  ajustes del local y simulador de móviles para demos.
- **Suite de evaluación propia**: escenarios de extremo a extremo con reloj
  simulado y empleados simulados (el que acepta rápido, el que se echa atrás,
  el que intenta manipular al agente…), verificación determinista de invariantes
  y umbrales que bloquean la CI.
- **Observabilidad y resiliencia**: una traza por rescate, coste y latencia por
  llamada al LLM, alertas, redacción de datos de salud, modo degradado sin LLM,
  pausa del agente, límites de envío y purga por retención.

## Decisiones técnicas destacables

- **El LLM propone, el dominio dispone**: las reglas de negocio (quién es
  elegible, qué se asigna, qué requiere aprobación) están en código puro y
  testeado; el LLM solo interpreta lenguaje y redacta.
- **Siete invariantes inviolables** (un turno nunca queda asignado a dos
  personas, nunca se ofrece a alguien no elegible, nunca se envía en horas de
  silencio, todo cambio queda auditado, los detalles de salud nunca salen de la
  conversación…), comprobados en tests unitarios, de integración y en cada
  escenario de evaluación.
- **Privacidad por diseño**: no se pide ni se guarda el motivo de la ausencia;
  si el empleado cuenta algo de salud, el cuerpo del mensaje se redacta antes de
  persistirlo.
- **Ingeniería de evaluación primero**: la calidad no depende de la opinión de
  un juez LLM; los invariantes y el reloj simulado son código determinista.

## Stack tecnológico

| Capa | Tecnologías |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic, `uv` |
| Datos y colas | PostgreSQL 16, Redis, Celery (worker y beat) |
| IA / agentes | Strands Agents SDK (fijado a 1.56.0) sin bucle autónomo, salida estructurada con Pydantic; proveedores intercambiables: Claude vía Anthropic, Claude vía Amazon Bedrock y modelos abiertos vía API compatible con OpenAI (NaN) |
| Mensajería | Twilio WhatsApp (REST + webhooks con validación de firma HMAC) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, diseño propio con tokens (tipografía serif/sans, paleta y sistema de sombras) |
| Observabilidad | OpenTelemetry → Langfuse Cloud, `structlog` JSON, alertas propias, Sentry |
| Testing | pytest, pytest-asyncio, Hypothesis (property-based), Vitest, React Testing Library |
| Calidad de código | ruff, mypy en modo estricto, oxlint, pre-commit |
| Infra y CI/CD | Docker y Docker Compose, Caddy (TLS automático), AWS (EC2, ECR, SSM Parameter Store, IAM con OIDC) y GitHub Actions |

## Números del proyecto

- **8 features** de especificación, **7 completas** (la octava con todo el código
  y la documentación listos para desplegar).
- **Más de 200 tests de backend** (más tests de integración contra PostgreSQL
  real) y **81 tests de frontend**, todos en verde.
- **14 escenarios de evaluación** de extremo a extremo con **0 violaciones de
  invariantes**.
- **100% de cobertura** en el paquete de dominio (regla de negocio).
- Especificación técnica, ADRs (decisiones de arquitectura), runbook de
  operaciones, informe de evaluación y guion de demo dentro del repositorio.

## Frases listas para el CV

- Diseñé y construí de punta a punta un agente de IA para gestión de ausencias
  de última hora en negocios con turnos, integrado por WhatsApp sobre el sistema
  de RRHH existente.
- Separé el razonamiento probabilístico del LLM de las reglas de negocio
  deterministas, con salida estructurada validada y siete invariantes
  verificados automáticamente en cada escenario de evaluación.
- Implementé una suite de evaluación propia con reloj simulado, empleados
  simulados y umbrales que bloquean la integración continua.
- Desplegué la aplicación con Docker Compose sobre AWS (EC2, ECR, secretos en
  SSM, CI/CD con OIDC) y observabilidad con OpenTelemetry hacia Langfuse Cloud.

## Estado

Proyecto de portfolio en desarrollo activo: las features 1-7 están completas y
verificadas; el despliegue en AWS está preparado (infraestructura como código de
los contenedores, pipeline y documentación) y se activa bajo demanda por coste.
La prueba con teléfonos reales de WhatsApp está validada de punta a punta
(recepción, interpretación, decisiones y envíos reales).
