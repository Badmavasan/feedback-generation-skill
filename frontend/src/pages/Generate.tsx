import { useState, useEffect } from 'react'
import { Sparkles, Loader2, AlertCircle } from 'lucide-react'
import {
  listPlatforms, listAlgoTaskTypes, listAlgoExercises, listAlgoErrors,
  generateFeedbackKC, generateFeedbackExercise, generateFeedbackError, generateFeedbackImage,
} from '../api/client'
import type { Platform, AlgoTaskType, AlgoExercise, AlgoError, FeedbackCharacteristic } from '../types'
import { CHARACTERISTIC_LABELS, CHARACTERISTIC_DESCRIPTIONS } from '../types'
import DragDropImage from '../components/DragDropImage'

const ALL_CHARS: FeedbackCharacteristic[] = [
  'logos','technical','error_pointed',
  'with_example_unrelated_to_exercise','with_example_related_to_exercise',
]

export default function Generate() {
  const [platforms, setPlatforms] = useState<Platform[]>([])
  const [taskTypes, setTaskTypes] = useState<AlgoTaskType[]>([])
  const [algoExercises, setAlgoExercises] = useState<AlgoExercise[]>([])
  const [algoErrors, setAlgoErrors] = useState<AlgoError[]>([])

  const [platformId, setPlatformId] = useState('algopython')
  const [language, setLanguage] = useState('fr')
  const [kcName, setKcName] = useState('')
  const [kcDesc, setKcDesc] = useState('')
  const [kcSearch, setKcSearch] = useState('')
  const [exerciseId, setExerciseId] = useState('')
  const [exerciseSearch, setExerciseSearch] = useState('')
  const [errorTag, setErrorTag] = useState('')
  const [errorDesc, setErrorDesc] = useState('')
  const [selected, setSelected] = useState<Set<FeedbackCharacteristic>>(new Set(['logos']))
  const [imageB64, setImageB64] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [xml, setXml] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { listPlatforms().then(r => setPlatforms(r.data)) }, [])
  useEffect(() => {
    listAlgoTaskTypes()
      .then(r => setTaskTypes(r.data))
      .catch(() => setTaskTypes([]))
    listAlgoExercises()
      .then(r => setAlgoExercises(r.data))
      .catch(() => setAlgoExercises([]))
    listAlgoErrors()
      .then(r => setAlgoErrors(r.data))
      .catch(() => setAlgoErrors([]))
  }, [])

  const toggleChar = (c: FeedbackCharacteristic) =>
    setSelected(prev => { const n = new Set(prev); n.has(c) ? n.delete(c) : n.add(c); return n })

  const filteredKCs = taskTypes.filter(k =>
    k.task_code.toLowerCase().includes(kcSearch.toLowerCase()) ||
    k.task_name.toLowerCase().includes(kcSearch.toLowerCase()))

  const selectedAlgoExercise = algoExercises.find(ex => ex.platform_exercise_id === exerciseId)

  const filteredAlgoExercises = algoExercises.filter(ex =>
    ex.title.toLowerCase().includes(exerciseSearch.toLowerCase()) ||
    ex.platform_exercise_id.includes(exerciseSearch)
  )

  const endpoint = (() => {
    if (selected.has('with_example_related_to_exercise') && exerciseId && imageB64) return 'image'
    if (errorTag) return 'error'
    if (exerciseId) return 'exercise'
    return 'kc'
  })()

  const endpointLabel: Record<string,string> = {
    kc: '/feedback/kc — task_type',
    exercise: '/feedback/exercise — exercise',
    error: '/feedback/error — error/error_exercise',
    image: '/feedback/image — image annotée',
  }

  const handleGenerate = async () => {
    if (!kcName.trim() || !kcDesc.trim()) { setErr('Sélectionne un KC.'); return }
    if (selected.size === 0) { setErr('Sélectionne au moins une caractéristique.'); return }
    setLoading(true); setErr(null); setXml(null)
    const kc_obj = { name: kcName.trim(), description: kcDesc.trim() }
    const chars = [...selected]
    try {
      let res: any
      const base = { language, knowledge_component: kc_obj, characteristics: chars }
      if (endpoint === 'image') {
        res = await generateFeedbackImage(platformId, {
          language, knowledge_component: kc_obj,
          exercise_id: exerciseId || undefined,
          error: errorTag ? { tag: errorTag, description: errorDesc } : undefined,
          base_image: imageB64!,
        })
      } else if (endpoint === 'error') {
        res = await generateFeedbackError(platformId, {
          ...base, exercise_id: exerciseId || undefined,
          error: { tag: errorTag, description: errorDesc },
        })
      } else if (endpoint === 'exercise') {
        res = await generateFeedbackExercise(platformId, { ...base, exercise_id: exerciseId || undefined })
      } else {
        res = await generateFeedbackKC(platformId, base)
      }
      setXml(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail ?? e.message ?? 'Erreur inconnue')
    } finally { setLoading(false) }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Générer un feedback</h1>
        <p className="text-sm text-gray-500 mt-1">
          Endpoint :{' '}
          <code className="bg-gray-100 px-1.5 py-0.5 rounded text-indigo-700 text-xs">
            {endpointLabel[endpoint]}
          </code>
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left */}
        <div className="space-y-4">
          {/* Platform */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Plateforme</h2>
            <div className="flex gap-2">
              <select value={platformId} onChange={e => setPlatformId(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                {platforms.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select value={language} onChange={e => setLanguage(e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                <option value="fr">FR</option>
                <option value="en">EN</option>
              </select>
            </div>
          </div>

          {/* KC */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">KC <span className="text-red-400">*</span></h2>
            <input placeholder="Rechercher un KC…" value={kcSearch} onChange={e => setKcSearch(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
            {kcSearch && filteredKCs.length > 0 && (
              <ul className="border border-gray-200 rounded-lg divide-y max-h-36 overflow-y-auto shadow-sm">
                {filteredKCs.slice(0,10).map(k => (
                  <li key={k.id}>
                    <button type="button" onClick={() => { setKcName(k.task_code); setKcDesc(k.task_name); setKcSearch('') }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50">
                      <span className="font-medium text-indigo-700">{k.task_code}</span>{' — '}
                      <span className="text-gray-600 text-xs">{k.task_name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <input placeholder="Nom ex: FO.4.2.1" value={kcName} onChange={e => setKcName(e.target.value)}
                className="w-1/3 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
              <input placeholder="Description du KC" value={kcDesc} onChange={e => setKcDesc(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
            </div>
          </div>

          {/* Exercise */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Exercice <span className="text-gray-400 font-normal">(optionnel)</span>
            </h2>
            <input
              placeholder="Rechercher par titre ou ID…"
              value={exerciseSearch}
              onChange={e => setExerciseSearch(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
            {exerciseSearch && filteredAlgoExercises.length > 0 && (
              <ul className="border border-gray-200 rounded-lg divide-y max-h-40 overflow-y-auto shadow-sm">
                {filteredAlgoExercises.slice(0, 8).map(ex => (
                  <li key={ex.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setExerciseId(ex.platform_exercise_id)
                        setExerciseSearch('')
                      }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50"
                    >
                      <span className="font-medium text-indigo-700">[{ex.platform_exercise_id}]</span>{' '}
                      <span className="text-gray-700">{ex.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {exerciseId ? (
              <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-indigo-800">
                        [{exerciseId}]{selectedAlgoExercise ? ` ${selectedAlgoExercise.title}` : ''}
                      </p>
                      {selectedAlgoExercise?.exercise_type && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-600 font-mono">
                          {selectedAlgoExercise.exercise_type}
                        </span>
                      )}
                    </div>
                    {selectedAlgoExercise?.description && (
                      <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">{selectedAlgoExercise.description}</p>
                    )}
                    {selectedAlgoExercise && selectedAlgoExercise.task_types.length > 0 && (
                      <p className="text-xs text-indigo-600 mt-0.5">
                        {selectedAlgoExercise.task_types.map(tt => `${tt.task_code}`).join(' · ')}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setExerciseId('')}
                    className="text-xs text-indigo-500 hover:text-indigo-700 shrink-0 mt-0.5"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-400">Aucun exercice sélectionné</p>
            )}
          </div>

          {/* Error */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Erreur <span className="text-gray-400 font-normal">(optionnel)</span></h2>
            <select value={errorTag} onChange={e => {
              const found = algoErrors.find(er => er.tag === e.target.value)
              setErrorTag(e.target.value); setErrorDesc(found?.description ?? '')
            }} className="w-full border border-gray-300 rounded-lg px-3 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none">
              <option value="">— Aucune —</option>
              {algoErrors.map(e => <option key={e.id} value={e.tag}>{e.tag}</option>)}
            </select>
            {errorTag && (
              <pre className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg p-3 whitespace-pre-wrap break-words max-h-48 overflow-y-auto leading-relaxed">{errorDesc}</pre>
            )}
          </div>
        </div>

        {/* Right */}
        <div className="space-y-4">
          {/* Characteristics */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Caractéristiques <span className="text-red-400">*</span></h2>
            {ALL_CHARS.map(c => {
              const disEx = c === 'with_example_related_to_exercise' && !exerciseId
              const disErr = c === 'error_pointed' && !errorTag
              const disabled = disEx || disErr
              return (
                <label key={c} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selected.has(c) ? 'border-indigo-300 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'
                } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}>
                  <input type="checkbox" checked={selected.has(c)} disabled={disabled}
                    onChange={() => !disabled && toggleChar(c)} className="mt-0.5 accent-indigo-600" />
                  <div>
                    <p className="text-sm font-medium text-gray-800">{CHARACTERISTIC_LABELS[c]}</p>
                    <p className="text-xs text-gray-500">{CHARACTERISTIC_DESCRIPTIONS[c]}</p>
                    {disabled && <p className="text-xs text-amber-600">{disEx ? 'Requiert un exercice' : 'Requiert une erreur'}</p>}
                  </div>
                </label>
              )
            })}
          </div>

          {/* Image drop */}
          {selected.has('with_example_related_to_exercise') && exerciseId && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Screenshot <span className="text-gray-400 font-normal">(feedback image)</span></h2>
              <DragDropImage value={imageB64} onChange={setImageB64} />
            </div>
          )}
        </div>
      </div>

      {err && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <pre className="whitespace-pre-wrap font-sans">{err}</pre>
        </div>
      )}

      <button onClick={handleGenerate} disabled={loading}
        className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-semibold py-3 rounded-xl transition-colors">
        {loading
          ? <><Loader2 size={18} className="animate-spin" />Génération en cours…</>
          : <><Sparkles size={18} />Générer le feedback</>}
      </button>

      {xml && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Résultat XML</h2>
            <button onClick={() => navigator.clipboard.writeText(xml)} className="text-xs text-indigo-600 hover:underline">Copier</button>
          </div>
          <pre className="text-xs bg-gray-50 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap text-gray-800 font-mono">{xml}</pre>
        </div>
      )}
    </div>
  )
}
