import axios from 'axios'
import type {
  Exercise, ExerciseIn, KC, KCIn, ErrorEntry, ErrorEntryIn,
  FeedbackRecord, FeedbackRecordDetail,
  AlgoExercise, AlgoError, AlgoTaskType,
  Platform, PlatformUpdate, GeneralConfig,
  PlatformConfig, PlatformConfigCreate, PlatformConfigUpdate,
} from '../types'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username: string, password: string) =>
  api.post<{ access_token: string }>('/auth/login', { username, password })

// ── Platforms ─────────────────────────────────────────────────────────────────
export const listPlatforms = () => api.get<Platform[]>('/platforms')
export const getPlatform = (id: string) => api.get<Platform>(`/platforms/${id}`)
export const createPlatform = (data: object) => api.post<Platform>('/platforms', data)
export const updatePlatform = (id: string, data: PlatformUpdate) =>
  api.patch<Platform>(`/platforms/${id}`, data)
export const deletePlatform = (id: string) => api.delete(`/platforms/${id}`)
export const getContextChunks = (id: string) =>
  api.get<{ platform_id: string; chunks: Record<string, string[]> }>(`/platforms/${id}/context`)
export const upsertContext = (id: string, data: object) =>
  api.post(`/platforms/${id}/context`, data)

// ── Platform Configurations ───────────────────────────────────────────────────
export const listPlatformConfigs = (platformId: string) =>
  api.get<PlatformConfig[]>(`/platforms/${platformId}/configs`)
export const createPlatformConfig = (platformId: string, data: PlatformConfigCreate) =>
  api.post<PlatformConfig>(`/platforms/${platformId}/configs`, data)
export const updatePlatformConfig = (platformId: string, configId: number, data: PlatformConfigUpdate) =>
  api.patch<PlatformConfig>(`/platforms/${platformId}/configs/${configId}`, data)
export const deletePlatformConfig = (platformId: string, configId: number) =>
  api.delete(`/platforms/${platformId}/configs/${configId}`)
export const activatePlatformConfig = (platformId: string, configId: number) =>
  api.post<PlatformConfig>(`/platforms/${platformId}/configs/${configId}/activate`)

export const getGeneralConfig = () => api.get<GeneralConfig>('/platforms/config/general')
export const updateGeneralConfig = (data: { general_feedback_instructions: string }) =>
  api.patch<GeneralConfig>('/platforms/config/general', data)

// ── Exercises ─────────────────────────────────────────────────────────────────
export const listExercises = (platformId = 'algopython') =>
  api.get<Exercise[]>(`/exercises?platform_id=${platformId}`)

export const getExercise = (exerciseId: string) =>
  api.get<Exercise>(`/exercises/${exerciseId}`)

export const createExercise = (data: ExerciseIn) =>
  api.post<Exercise>('/exercises', data)

export const updateExercise = (exerciseId: string, data: ExerciseIn) =>
  api.patch<Exercise>(`/exercises/${exerciseId}`, data)

export const deleteExercise = (exerciseId: string) =>
  api.delete(`/exercises/${exerciseId}`)

// ── Knowledge Components ──────────────────────────────────────────────────────
export const listKCs = (platformId = 'algopython') =>
  api.get<KC[]>(`/kcs?platform_id=${platformId}`)

export const createKC = (data: KCIn) =>
  api.post<KC>('/kcs', data)

export const updateKC = (id: number, data: KCIn) =>
  api.patch<KC>(`/kcs/${id}`, data)

export const deleteKC = (id: number) =>
  api.delete(`/kcs/${id}`)

// ── Error Catalog ─────────────────────────────────────────────────────────────
export const listErrors = (platformId = 'algopython') =>
  api.get<ErrorEntry[]>(`/error-catalog?platform_id=${platformId}`)

export const createError = (data: ErrorEntryIn) =>
  api.post<ErrorEntry>('/error-catalog', data)

export const updateError = (id: number, data: ErrorEntryIn) =>
  api.patch<ErrorEntry>(`/error-catalog/${id}`, data)

export const deleteError = (id: number) =>
  api.delete(`/error-catalog/${id}`)

// ── Feedback Generation ───────────────────────────────────────────────────────
// All endpoints accept { mode: "offline" | "live", ... } in the body.
// The admin frontend always sends mode="offline"; live_context is for platform clients.

export const generateFeedbackKC = (platformId: string, data: object) =>
  api.post(`/feedback/kc?platform_id=${platformId}`, data, {
    responseType: 'text',
    headers: { Accept: 'application/xml' },
  })

export const generateFeedbackExercise = (platformId: string, data: object) =>
  api.post(`/feedback/exercise?platform_id=${platformId}`, data, {
    responseType: 'text',
    headers: { Accept: 'application/xml' },
  })

export const generateFeedbackError = (platformId: string, data: object) =>
  api.post(`/feedback/error?platform_id=${platformId}`, data, {
    responseType: 'text',
    headers: { Accept: 'application/xml' },
  })

export const generateFeedbackImage = (platformId: string, data: object) =>
  api.post(`/feedback/image?platform_id=${platformId}`, data, {
    responseType: 'text',
    headers: { Accept: 'application/xml' },
  })

// ── AlgoPython source DB (read-only) ─────────────────────────────────────────
export const listAlgoExercises = () =>
  api.get<AlgoExercise[]>('/algopython/exercises')

export const getAlgoExercise = (platformExerciseId: string) =>
  api.get<AlgoExercise>(`/algopython/exercises/${platformExerciseId}`)

export const listAlgoErrors = () =>
  api.get<AlgoError[]>('/algopython/errors')

export const listAlgoTaskTypes = () =>
  api.get<AlgoTaskType[]>('/algopython/task-types')

// ── History ───────────────────────────────────────────────────────────────────
export const listHistory = (platformId?: string, limit = 50, offset = 0) => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (platformId) params.set('platform_id', platformId)
  return api.get<FeedbackRecord[]>(`/history?${params}`)
}

export const getHistoryRecord = (id: string) =>
  api.get<FeedbackRecordDetail>(`/history/${id}`)

export const deleteHistoryRecord = (id: string) =>
  api.delete(`/history/${id}`)

export default api
