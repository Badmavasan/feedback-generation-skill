// ── Auth ──────────────────────────────────────────────────────────────────────
export interface LoginResponse {
  access_token: string
  token_type: string
}

// ── Platforms ─────────────────────────────────────────────────────────────────
export interface Platform {
  id: string
  name: string
  language: string
  description: string
  feedback_mode: 'offline' | 'live'
  platform_context: string | null
  live_student_prompt: string | null
  created_at: string
  context_chunk_count: number
}

export interface PlatformCreate {
  id: string
  name: string
  language: string
  description: string
  feedback_mode?: 'offline' | 'live'
  platform_context?: string | null
  live_student_prompt?: string | null
}

export interface PlatformUpdate {
  name?: string
  language?: string
  description?: string
  feedback_mode?: 'offline' | 'live'
  platform_context?: string | null
  live_student_prompt?: string | null
}

export interface GeneralConfig {
  general_feedback_instructions: string
  updated_at: string | null
}

export interface ContextChunk {
  section: string
  content: string
}

export interface ContextUpload {
  chunks: ContextChunk[]
  replace_section?: string
}

// ── Exercises ─────────────────────────────────────────────────────────────────
export type ExerciseType = 'console' | 'design' | 'robot'

export interface RobotMap {
  rows: number
  cols: number
  grid: string[][]
}

export interface Exercise {
  id: number
  platform_id: string
  exercise_id: string
  title: string
  description: string
  exercise_type: ExerciseType
  robot_map: RobotMap | null
  possible_solutions: string[]
  kc_names: string[]
  created_at: string
  updated_at: string
}

export interface ExerciseIn {
  platform_id: string
  exercise_id: string
  title: string
  description: string
  exercise_type: ExerciseType
  robot_map: RobotMap | null
  possible_solutions: string[]
  kc_names: string[]
}

// ── Knowledge Components ──────────────────────────────────────────────────────
export interface KC {
  id: number
  platform_id: string
  name: string
  description: string
  series: string | null
  created_at: string
}

export interface KCIn {
  platform_id: string
  name: string
  description: string
  series: string | null
}

// ── Error Catalog ─────────────────────────────────────────────────────────────
export interface ErrorEntry {
  id: number
  platform_id: string
  tag: string
  description: string
  related_kc_names: string[]
  created_at: string
}

export interface ErrorEntryIn {
  platform_id: string
  tag: string
  description: string
  related_kc_names: string[]
}

// ── Feedback Generation ───────────────────────────────────────────────────────
export type FeedbackCharacteristic =
  | 'logos'
  | 'technical'
  | 'error_pointed'
  | 'with_example_unrelated_to_exercise'
  | 'with_example_related_to_exercise'

export type Characteristic = FeedbackCharacteristic

export const CHARACTERISTIC_LABELS: Record<FeedbackCharacteristic, string> = {
  logos: 'Logos — conceptuel',
  technical: 'Technical — procédural',
  error_pointed: 'Error pointed — erreur ciblée',
  with_example_unrelated_to_exercise: 'Exemple non lié',
  with_example_related_to_exercise: "Exemple lié à l'exercice",
}

export const CHARACTERISTIC_DESCRIPTIONS: Record<FeedbackCharacteristic, string> = {
  logos: 'Explication pure du concept — sans code ni direction procédurale',
  technical: 'Direction procédurale — quoi utiliser, quoi vérifier',
  error_pointed: "Nomme l'erreur précisément et redirige vers le concept sous-jacent",
  with_example_unrelated_to_exercise: 'Exemple code neutre illustrant le concept',
  with_example_related_to_exercise: "Exemple code ancré dans le contexte de l'exercice",
}

export type OfflineLevel = 'task_type' | 'exercise' | 'error' | 'error_exercise'

export interface OfflineFeedbackRequest {
  language: string
  characteristics: FeedbackCharacteristic[]
  level: OfflineLevel
  knowledge_component: { name: string; description: string }
  exercise_id?: string
  exercise?: { description: string; possible_solutions: string[] }
  error?: { tag: string; description: string }
  base_image?: string
}

export interface FeedbackResult {
  xml: string
  generatedAt: Date
  platformId: string
  characteristics: FeedbackCharacteristic[]
}

// ── Platform configurations ───────────────────────────────────────────────────
export interface PlatformConfig {
  id: number
  platform_id: string
  name: string
  is_active: boolean
  vocabulary_to_use: string | null
  vocabulary_to_avoid: string | null
  teacher_comments: string | null
  created_at: string
  updated_at: string
}

export interface PlatformConfigCreate {
  name: string
  vocabulary_to_use?: string | null
  vocabulary_to_avoid?: string | null
  teacher_comments?: string | null
}

export interface PlatformConfigUpdate {
  name?: string
  vocabulary_to_use?: string | null
  vocabulary_to_avoid?: string | null
  teacher_comments?: string | null
}

// ── AlgoPython source DB ──────────────────────────────────────────────────────

export interface AlgoTaskType {
  id: number
  task_code: string
  task_name: string
}

export interface AlgoExercise {
  id: number
  platform_exercise_id: string
  title: string
  description: string | null
  exercise_type: string | null
  task_types: AlgoTaskType[]
}

export interface AlgoError {
  id: number
  tag: string
  description: string
}

// ── History ───────────────────────────────────────────────────────────────────
export interface FeedbackRecord {
  id: string
  platform_id: string
  exercise_id: string | null
  kc_name: string
  kc_description: string
  mode: string
  level: string
  language: string
  characteristics: string[]
  status: 'pending' | 'completed' | 'failed'
  validation_status: 'generated' | 'validé'
  error_message: string | null
  total_iterations: number | null
  created_at: string
}

export interface AgentLog {
  id: number
  step_number: number
  agent: string
  role: string
  tool_name: string | null
  characteristic: string | null
  attempt: number | null
  verdict: string | null
  notes: string | null
  input_data: unknown
  output_data: unknown
  duration_ms: number | null
  created_at: string
}

export interface FeedbackRecordDetail extends FeedbackRecord {
  result_xml: string | null
  request_payload: unknown
  logs: AgentLog[]
}
