import { useCallback, useState } from 'react'
import { ImageIcon, X } from 'lucide-react'

interface Props {
  value: string | null   // base64 string
  onChange: (b64: string | null) => void
}

export default function DragDropImage({ value, onChange }: Props) {
  const [dragging, setDragging] = useState(false)

  const processFile = (file: File) => {
    if (!file.type.startsWith('image/')) return
    const reader = new FileReader()
    reader.onload = (e) => {
      const result = e.target?.result as string
      // Strip the data:image/...;base64, prefix
      const b64 = result.split(',')[1]
      onChange(b64)
    }
    reader.readAsDataURL(file)
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) processFile(file)
  }, [])

  const onFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) processFile(file)
  }

  if (value) {
    return (
      <div className="relative inline-block">
        <img
          src={`data:image/png;base64,${value}`}
          alt="Screenshot"
          className="max-h-48 rounded-lg border border-gray-200 object-contain"
        />
        <button
          type="button"
          onClick={() => onChange(null)}
          className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-0.5 hover:bg-red-600"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`flex flex-col items-center justify-center gap-2 w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
        dragging
          ? 'border-indigo-500 bg-indigo-50'
          : 'border-gray-300 bg-gray-50 hover:border-indigo-400 hover:bg-indigo-50/50'
      }`}
    >
      <input type="file" accept="image/*" className="hidden" onChange={onFileInput} />
      <ImageIcon size={24} className="text-gray-400" />
      <span className="text-sm text-gray-500">
        Glisser-déposer ou <span className="text-indigo-600 font-medium">parcourir</span>
      </span>
      <span className="text-xs text-gray-400">PNG, JPG</span>
    </label>
  )
}
