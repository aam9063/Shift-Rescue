/**
 * Mock data for the manager-dashboard screens (mirrors the user mockups).
 * Behind a plain interface so later slices swap it for the REST API without
 * touching components.
 */

export interface ChatMessage {
  from: "employee" | "assistant";
  text: string;
}

export interface Conversation {
  employeeId: string;
  employeeName: string;
  initials: string;
  lastMessage: string;
  intent: string;
  rescueLabel: string;
  messages: ChatMessage[];
}

export interface AgentDecision {
  time: string;
  employeeName: string;
  intent: string;
  confidence: number;
  model: string;
  costUsd: number;
  latencyMs: number;
  validation: "OK" | "retry";
}

export interface ModelComparison {
  name: string;
  accuracy: number;
  costPerMessage: string;
}

export interface ScenarioResult {
  id: string;
  passed: boolean;
}

export interface EvalRunSummary {
  passed: boolean;
  commit: string;
  ranAgo: string;
  accuracyHistory: number[];
  threshold: number;
  latestAccuracy: number;
  scenarios: ScenarioResult[];
  models: ModelComparison[];
  invariantViolations: number;
}

export interface OpsAlert {
  severity: "error" | "warning";
  title: string;
  detail: string;
}

export interface OpsMetrics {
  costToday: number;
  rescuesCount: number;
  p95LatencyMs: number;
  latencyTargetMs: number;
  lowConfidencePct: number;
  lowConfidenceTotal: number;
  stuckCount: number;
  costHistory: number[];
  alerts: OpsAlert[];
}

export interface LocationSettings {
  agentPaused: boolean;
  rankingWeights: { label: string; level: "high" | "medium" }[];
  waveSize: number;
  waveIntervalMinutes: number;
  quietStart: string;
  quietEnd: string;
}

export const CONVERSATIONS: Conversation[] = [
  {
    employeeId: "emp_marta",
    employeeName: "Marta L.",
    initials: "ML",
    lastMessage: "puedo pero llego a las 15:15",
    intent: "OFFER_CONDITIONAL",
    rescueLabel: "Sala 15:00",
    messages: [
      { from: "assistant", text: "Hola Marta, ha quedado libre un turno de Sala hoy de 15:00 a 23:00. Puedes cubrirlo?" },
      { from: "employee", text: "puedo pero llego a las 15:15" },
      { from: "assistant", text: "Gracias Marta, se lo paso al encargado para que lo confirme." },
    ],
  },
  {
    employeeId: "emp_ivan",
    employeeName: "Ivan R.",
    initials: "IR",
    lastMessage: "no puedo, lo siento",
    intent: "OFFER_DECLINE",
    rescueLabel: "Sala 15:00",
    messages: [
      { from: "assistant", text: "Hola Ivan, ha quedado libre un turno de Sala hoy de 15:00 a 23:00. Puedes cubrirlo?" },
      { from: "employee", text: "no puedo, lo siento" },
    ],
  },
  {
    employeeId: "emp_iker",
    employeeName: "Iker M.",
    initials: "IM",
    lastMessage: "buenas, me encuentro fatal, hoy no puedo ir",
    intent: "ABSENCE_REPORT",
    rescueLabel: "Sala 15:00",
    messages: [
      { from: "employee", text: "buenas, me encuentro fatal, hoy no puedo ir" },
      { from: "assistant", text: "Recibido, que te mejores. Ya me encargo de buscar a alguien." },
    ],
  },
  {
    employeeId: "emp_sonia",
    employeeName: "Sonia P.",
    initials: "SP",
    lastMessage: "vale, cuento contigo entonces",
    intent: "SMALLTALK",
    rescueLabel: "Sin rescate",
    messages: [{ from: "employee", text: "vale, cuento contigo entonces" }],
  },
  {
    employeeId: "emp_pau",
    employeeName: "Pau S.",
    initials: "PS",
    lastMessage: "cuantos dias de vacaciones me quedan?",
    intent: "QUESTION",
    rescueLabel: "Sin rescate",
    messages: [{ from: "employee", text: "cuantos dias de vacaciones me quedan?" }],
  },
  {
    employeeId: "emp_diego",
    employeeName: "Diego F.",
    initials: "DF",
    lastMessage: "oferta recibida, dejame pensarlo",
    intent: "UNCLEAR",
    rescueLabel: "Sala 15:00",
    messages: [{ from: "employee", text: "oferta recibida, dejame pensarlo" }],
  },
];

export const AGENT_DECISIONS: AgentDecision[] = [
  { time: "15:03", employeeName: "Marta L.", intent: "OFFER_ACCEPT", confidence: 0.92, model: "nan/deepseek-v4", costUsd: 0.001, latencyMs: 410, validation: "OK" },
  { time: "15:04", employeeName: "Ivan R.", intent: "OFFER_DECLINE", confidence: 0.96, model: "nan/deepseek-v4", costUsd: 0.001, latencyMs: 380, validation: "OK" },
  { time: "15:07", employeeName: "Diego F.", intent: "UNCLEAR", confidence: 0.41, model: "nan/deepseek-v4", costUsd: 0.001, latencyMs: 520, validation: "retry" },
  { time: "15:09", employeeName: "Sonia P.", intent: "OFFER_CONDITIONAL", confidence: 0.78, model: "claude-haiku-4.5", costUsd: 0.004, latencyMs: 640, validation: "OK" },
  { time: "15:11", employeeName: "Pau S.", intent: "QUESTION", confidence: 0.88, model: "nan/deepseek-v4", costUsd: 0.001, latencyMs: 395, validation: "OK" },
  { time: "15:12", employeeName: "Lucia G.", intent: "SMALLTALK", confidence: 0.95, model: "nan/deepseek-v4", costUsd: 0.001, latencyMs: 360, validation: "OK" },
  { time: "15:14", employeeName: "Noa S.", intent: "ABSENCE_RETRACT", confidence: 0.69, model: "claude-haiku-4.5", costUsd: 0.004, latencyMs: 710, validation: "OK" },
];

export const EVAL_RUN: EvalRunSummary = {
  passed: true,
  commit: "7fa21e",
  ranAgo: "hace 40 min",
  accuracyHistory: [0.88, 0.87, 0.9, 0.89, 0.92, 0.91, 0.93, 0.93, 0.94, 0.94],
  threshold: 0.92,
  latestAccuracy: 0.94,
  scenarios: [
    { id: "quick_yes", passed: true },
    { id: "race_two_accepts", passed: true },
    { id: "manipulator", passed: true },
    { id: "oversharer_health_details", passed: true },
    { id: "llm_provider_down", passed: true },
  ],
  models: [
    { name: "claude-haiku-4.5", accuracy: 0.95, costPerMessage: "$0.004/msg" },
    { name: "nan/deepseek-v4-flash", accuracy: 0.94, costPerMessage: "$0.001/msg" },
    { name: "nan/qwen3.6-flash", accuracy: 0.89, costPerMessage: "$0.001/msg" },
  ],
  invariantViolations: 0,
};

export const OPS_METRICS: OpsMetrics = {
  costToday: 4.12,
  rescuesCount: 38,
  p95LatencyMs: 820,
  latencyTargetMs: 1200,
  lowConfidencePct: 6,
  lowConfidenceTotal: 340,
  stuckCount: 1,
  costHistory: [2.9, 3.1, 3.0, 3.3, 3.2, 3.6, 3.5, 3.9, 3.7, 4.1, 4.0, 4.05, 4.02, 4.04],
  alerts: [
    { severity: "error", title: "Rescate atascado", detail: "Barra 19:00-23:00, sin eventos desde hace 18 min." },
    { severity: "warning", title: "Tasa de baja confianza alta", detail: "22% en la ultima hora, por encima del umbral." },
    { severity: "warning", title: "Fallo de entrega", detail: "Un mensaje a Pau S. no se pudo entregar." },
  ],
};

export const DEFAULT_SETTINGS: LocationSettings = {
  agentPaused: false,
  rankingWeights: [
    { label: "Equidad de coberturas", level: "high" },
    { label: "Proximidad (misma zona)", level: "medium" },
    { label: "Preferencia por horas extra", level: "medium" },
    { label: "Sin horas extra primero", level: "high" },
  ],
  waveSize: 3,
  waveIntervalMinutes: 10,
  quietStart: "23:00",
  quietEnd: "07:00",
};
