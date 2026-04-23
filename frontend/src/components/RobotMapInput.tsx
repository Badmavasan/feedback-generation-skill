import { useState } from 'react'
import type { RobotMap } from '../types'

const CELL_TYPES = ['O', 'X', 'I', 'G'] as const
type CellType = typeof CELL_TYPES[number]

const CELL_COLORS: Record<CellType, string> = {
  O: 'bg-white border-gray-300',
  X: 'bg-gray-800 border-gray-900',
  I: 'bg-green-400 border-green-600',
  G: 'bg-yellow-400 border-yellow-600',
}

const CELL_LABELS: Record<CellType, string> = {
  O: 'O',
  X: '■',
  I: 'S',
  G: 'G',
}

interface Props {
  value: RobotMap | null
  onChange: (map: RobotMap) => void
}

const DEFAULT_ROWS = 6
const DEFAULT_COLS = 6

function makeGrid(rows: number, cols: number): string[][] {
  return Array.from({ length: rows }, () => Array(cols).fill('O'))
}

export default function RobotMapInput({ value, onChange }: Props) {
  const [selectedType, setSelectedType] = useState<CellType>('O')

  const rows = value?.rows ?? DEFAULT_ROWS
  const cols = value?.cols ?? DEFAULT_COLS
  const grid = value?.grid ?? makeGrid(rows, cols)

  const updateGrid = (newGrid: string[][]) => {
    onChange({ rows, cols, grid: newGrid })
  }

  const toggleCell = (r: number, c: number) => {
    const newGrid = grid.map((row) => [...row])
    // Only one I and one G allowed
    if (selectedType === 'I' || selectedType === 'G') {
      for (let i = 0; i < rows; i++)
        for (let j = 0; j < cols; j++)
          if (newGrid[i][j] === selectedType) newGrid[i][j] = 'O'
    }
    newGrid[r][c] = selectedType
    updateGrid(newGrid)
  }

  const resize = (newRows: number, newCols: number) => {
    const newGrid = Array.from({ length: newRows }, (_, r) =>
      Array.from({ length: newCols }, (_, c) => grid[r]?.[c] ?? 'O')
    )
    onChange({ rows: newRows, cols: newCols, grid: newGrid })
  }

  return (
    <div className="space-y-3">
      {/* Palette */}
      <div className="flex gap-2 items-center">
        <span className="text-xs text-gray-500 font-medium">Pinceau :</span>
        {CELL_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSelectedType(t)}
            className={`w-8 h-8 rounded border-2 text-xs font-bold transition-all ${CELL_COLORS[t]} ${
              selectedType === t ? 'ring-2 ring-indigo-500 ring-offset-1 scale-110' : ''
            }`}
          >
            {CELL_LABELS[t]}
          </button>
        ))}
        <span className="text-xs text-gray-400 ml-2">
          O=libre · ■=mur · S=départ · G=arrivée
        </span>
      </div>

      {/* Size controls */}
      <div className="flex gap-4 text-xs text-gray-500">
        <label className="flex items-center gap-1">
          Lignes:
          <input
            type="number" min={2} max={16} value={rows}
            onChange={(e) => resize(Number(e.target.value), cols)}
            className="w-12 border rounded px-1 py-0.5 text-gray-800"
          />
        </label>
        <label className="flex items-center gap-1">
          Colonnes:
          <input
            type="number" min={2} max={16} value={cols}
            onChange={(e) => resize(rows, Number(e.target.value))}
            className="w-12 border rounded px-1 py-0.5 text-gray-800"
          />
        </label>
      </div>

      {/* Grid */}
      <div
        className="inline-grid gap-0.5 border border-gray-200 rounded p-1 bg-gray-100"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {grid.map((row, r) =>
          row.map((cell, c) => (
            <button
              key={`${r}-${c}`}
              type="button"
              onClick={() => toggleCell(r, c)}
              className={`w-8 h-8 rounded-sm border text-xs font-bold transition-colors ${
                CELL_COLORS[cell as CellType] ?? 'bg-white border-gray-300'
              }`}
            >
              {cell !== 'O' ? CELL_LABELS[cell as CellType] : ''}
            </button>
          ))
        )}
      </div>
    </div>
  )
}
