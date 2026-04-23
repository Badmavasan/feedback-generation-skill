import { useState, useEffect } from 'react'
import { Plus, Pencil, Trash2, ChevronDown, ChevronUp, Save, X } from 'lucide-react'
import { listExercises, listKCs, createExercise, updateExercise, deleteExercise } from '../api/client'
import type { Exercise, ExerciseIn, ExerciseType, KC, RobotMap } from '../types'
import RobotMapInput from '../components/RobotMapInput'

const EXERCISE_TYPES: ExerciseType[] = ['console','design','robot']
const EMPTY: ExerciseIn = {
  platform_id: 'algopython', exercise_id: '', title: '', description: '',
  exercise_type: 'console', robot_map: null, possible_solutions: [], kc_names: [],
}

export default function Exercises() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [kcs, setKCs] = useState<KC[]>([])
  const [editing, setEditing] = useState<Exercise | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<ExerciseIn>(EMPTY)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    listExercises().then(r => setExercises(r.data))
    listKCs().then(r => setKCs(r.data))
  }
  useEffect(load, [])

  const openCreate = () => { setForm(EMPTY); setCreating(true); setEditing(null) }
  const openEdit = (ex: Exercise) => {
    setForm({
      platform_id: ex.platform_id, exercise_id: ex.exercise_id, title: ex.title,
      description: ex.description, exercise_type: ex.exercise_type,
      robot_map: ex.robot_map, possible_solutions: [...ex.possible_solutions],
      kc_names: [...ex.kc_names],
    })
    setEditing(ex); setCreating(false)
  }
  const cancel = () => { setCreating(false); setEditing(null); setError(null) }

  const save = async () => {
    if (!form.exercise_id || !form.title) { setError('ID et titre requis'); return }
    setSaving(true); setError(null)
    try {
      if (creating) await createExercise(form)
      else if (editing) await updateExercise(editing.exercise_id, form)
      load(); cancel()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? e.message)
    } finally { setSaving(false) }
  }

  const del = async (exerciseId: string) => {
    if (!confirm('Supprimer cet exercice ?')) return
    await deleteExercise(exerciseId); load()
  }

  const toggleKC = (name: string) => {
    setForm(f => ({
      ...f, kc_names: f.kc_names.includes(name)
        ? f.kc_names.filter(k => k !== name)
        : [...f.kc_names, name],
    }))
  }

  const addSolution = () => setForm(f => ({ ...f, possible_solutions: [...f.possible_solutions, ''] }))
  const setSolution = (i: number, v: string) =>
    setForm(f => { const s = [...f.possible_solutions]; s[i] = v; return { ...f, possible_solutions: s } })
  const removeSolution = (i: number) =>
    setForm(f => ({ ...f, possible_solutions: f.possible_solutions.filter((_, j) => j !== i) }))

  const isEditorOpen = creating || !!editing

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Exercices</h1>
        <button onClick={openCreate}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
          <Plus size={16} />Nouvel exercice
        </button>
      </div>

      {/* Editor */}
      {isEditorOpen && (
        <div className="bg-white rounded-xl border border-indigo-200 shadow-sm p-6 space-y-5">
          <h2 className="text-base font-semibold text-gray-800">{creating ? 'Nouvel exercice' : `Modifier ${editing?.exercise_id}`}</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">ID exercice *</label>
              <input value={form.exercise_id} onChange={e => setForm(f => ({ ...f, exercise_id: e.target.value }))} disabled={!!editing}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none disabled:bg-gray-50" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Titre *</label>
              <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none" />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
            <div className="flex gap-2">
              {EXERCISE_TYPES.map(t => (
                <button key={t} type="button" onClick={() => setForm(f => ({ ...f, exercise_type: t, robot_map: t === 'robot' ? f.robot_map ?? { rows: 6, cols: 6, grid: Array.from({length:6},()=>Array(6).fill('O')) } : null }))}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${form.exercise_type === t ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400'}`}>
                  {t}
                </button>
              ))}
            </div>
          </div>

          {form.exercise_type === 'robot' && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Carte robot</label>
              <RobotMapInput
                value={form.robot_map}
                onChange={(map: RobotMap) => setForm(f => ({ ...f, robot_map: map }))}
              />
            </div>
          )}

          {/* Solutions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-600">Solutions correctes</label>
              <button type="button" onClick={addSolution} className="text-xs text-indigo-600 hover:underline">+ Ajouter</button>
            </div>
            {form.possible_solutions.map((s, i) => (
              <div key={i} className="flex gap-2 mb-2">
                <input value={s} onChange={e => setSolution(i, e.target.value)}
                  placeholder={`Solution ${i+1}`}
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
                <button onClick={() => removeSolution(i)} className="text-gray-400 hover:text-red-500"><X size={14}/></button>
              </div>
            ))}
          </div>

          {/* KC multi-select */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-2">KCs associés</label>
            <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
              {kcs.map(k => (
                <button key={k.id} type="button" onClick={() => toggleKC(k.name)}
                  className={`px-2 py-1 rounded text-xs border transition-colors ${
                    form.kc_names.includes(k.name)
                      ? 'bg-indigo-100 border-indigo-400 text-indigo-800 font-medium'
                      : 'bg-white border-gray-300 text-gray-600 hover:border-indigo-300'
                  }`}>
                  {k.name}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3">
            <button onClick={save} disabled={saving}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-medium px-4 py-2 rounded-lg">
              <Save size={14}/>{saving ? 'Sauvegarde…' : 'Sauvegarder'}
            </button>
            <button onClick={cancel} className="flex items-center gap-2 border border-gray-300 text-gray-700 text-sm px-4 py-2 rounded-lg hover:bg-gray-50">
              <X size={14}/>Annuler
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">ID</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Titre</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Type</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">KCs</th>
              <th className="text-right px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {exercises.map(ex => (
              <>
                <tr key={ex.exercise_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-indigo-700 font-medium">{ex.exercise_id}</td>
                  <td className="px-4 py-3 text-gray-800">{ex.title}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      ex.exercise_type === 'robot' ? 'bg-purple-100 text-purple-700' :
                      ex.exercise_type === 'design' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'
                    }`}>{ex.exercise_type}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{ex.kc_names.slice(0,3).join(', ')}{ex.kc_names.length > 3 ? ` +${ex.kc_names.length-3}` : ''}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setExpanded(expanded === ex.exercise_id ? null : ex.exercise_id)}
                        className="p-1.5 text-gray-400 hover:text-gray-600 rounded">
                        {expanded === ex.exercise_id ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
                      </button>
                      <button onClick={() => openEdit(ex)} className="p-1.5 text-gray-400 hover:text-indigo-600 rounded"><Pencil size={14}/></button>
                      <button onClick={() => del(ex.exercise_id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded"><Trash2 size={14}/></button>
                    </div>
                  </td>
                </tr>
                {expanded === ex.exercise_id && (
                  <tr key={`${ex.exercise_id}-expanded`}>
                    <td colSpan={5} className="px-4 py-3 bg-gray-50 text-xs text-gray-600 space-y-1">
                      <p><strong>Description :</strong> {ex.description || '—'}</p>
                      <p><strong>Solutions :</strong> {ex.possible_solutions.join(' | ') || '—'}</p>
                      {ex.robot_map && <p><strong>Carte :</strong> {ex.robot_map.rows}×{ex.robot_map.cols}</p>}
                    </td>
                  </tr>
                )}
              </>
            ))}
            {exercises.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400 text-sm">Aucun exercice</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
