import { useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'

interface OnScreenKeyboardProps {
  isOpen: boolean
  value: string
  onChange: (value: string) => void
  onClose: () => void
}

const letterRows = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', '!', '?'],
]

const numRows = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['@', '#', '$', '%', '&', '*', '-', '+', '(', ')'],
  ['"', "'", ':', ';', '/', '\\', '=', '_', '~'],
]

function KeyboardUI({ value, onKey, onBackspace, onShift, shifted, onSpace, onChar, onClose, numMode, onToggleNum }: {
  value: string
  onKey: (key: string) => void
  onBackspace: () => void
  onShift: () => void
  shifted: boolean
  onSpace: () => void
  onChar: (c: string) => void
  onClose: () => void
  numMode: boolean
  onToggleNum: () => void
}) {
  const keyClass = "flex-1 bg-[#1a1a1a] rounded-lg text-white text-lg font-medium active:bg-[#333] transition-colors select-none"
  const rows = numMode ? numRows : letterRows

  return (
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 99999, background: '#0a0a0a' }}>
      {/* Input display */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid #222' }}>
        <p className="text-white text-xl font-semibold flex-1 truncate">
          {value}<span style={{ color: '#0ea5e9' }} className="animate-pulse">|</span>
        </p>
        <button onClick={onClose} className="ml-4 shrink-0 px-4 py-2 bg-[#1a1a1a] rounded-lg text-white text-sm active:bg-[#333]">
          Close Keyboard
        </button>
      </div>

      {/* Keys */}
      <div className="flex-1 flex flex-col gap-2 p-3">
        <div className="flex-1 flex gap-1.5">
          {rows[0].map(key => (
            <button key={key} onClick={() => onKey(key)} className={cn(keyClass, 'relative')}>
              {!numMode && shifted ? key.toUpperCase() : key}
            </button>
          ))}
          <button onClick={onBackspace} className="flex-1 bg-red-600 rounded-lg text-white text-lg active:bg-red-500 flex items-center justify-center select-none">
            ⌫
          </button>
        </div>

        <div className="flex-1 flex gap-1.5 px-[3%]">
          {rows[1].map(key => (
            <button key={key} onClick={() => onKey(key)} className={keyClass}>
              {!numMode && shifted ? key.toUpperCase() : key}
            </button>
          ))}
        </div>

        <div className="flex-1 flex gap-1.5">
          {numMode ? (
            <div className="flex-1" />
          ) : (
            <button onClick={onShift} className={cn("flex-1 rounded-lg text-white text-lg select-none", shifted ? 'bg-[#333]' : 'bg-[#1a1a1a]')}>
              ⇧
            </button>
          )}
          {rows[2].map(key => (
            <button key={key} onClick={() => onKey(key)} className={keyClass}>
              {!numMode && shifted ? key.toUpperCase() : key}
            </button>
          ))}
          {numMode ? (
            <div className="flex-1" />
          ) : (
            <button onClick={onShift} className={cn("flex-1 rounded-lg text-white text-lg select-none", shifted ? 'bg-[#333]' : 'bg-[#1a1a1a]')}>
              ⇧
            </button>
          )}
        </div>

        <div className="flex-1 flex gap-1.5">
          <button onClick={onToggleNum} className={cn("w-[60px] rounded-lg text-white text-sm shrink-0 select-none active:bg-[#333]", numMode ? 'bg-[#333]' : 'bg-[#1a1a1a]')}>
            {numMode ? 'ABC' : '?123'}
          </button>
          <button onClick={() => onChar(',')} className="w-[48px] bg-[#1a1a1a] rounded-lg text-white text-lg active:bg-[#333] shrink-0 select-none">,</button>
          <button onClick={onSpace} className="flex-1 bg-[#1a1a1a] rounded-lg active:bg-[#333] select-none" />
          <button onClick={() => onChar('.')} className="w-[48px] bg-[#1a1a1a] rounded-lg text-white text-lg active:bg-[#333] shrink-0 select-none">.</button>
          <button onClick={onClose} className="w-[90px] bg-sky-500 text-white rounded-lg text-sm font-semibold shrink-0 select-none active:bg-sky-400">Done</button>
        </div>
      </div>
    </div>
  )
}

export default function OnScreenKeyboard({ isOpen, value, onChange, onClose }: OnScreenKeyboardProps) {
  const [shifted, setShifted] = useState(false)
  const [numMode, setNumMode] = useState(false)

  const handleKey = useCallback((key: string) => {
    const char = !numMode && shifted ? key.toUpperCase() : key
    onChange(value + char)
    setShifted(false)
  }, [value, shifted, numMode, onChange])

  const handleBackspace = useCallback(() => {
    onChange(value.slice(0, -1))
  }, [value, onChange])

  const handleSpace = useCallback(() => {
    onChange(value + ' ')
  }, [value, onChange])

  const handleChar = useCallback((c: string) => {
    onChange(value + c)
  }, [value, onChange])

  const handleShift = useCallback(() => {
    setShifted(s => !s)
  }, [])

  const handleToggleNum = useCallback(() => {
    setNumMode(n => !n)
    setShifted(false)
  }, [])

  if (!isOpen) return null

  return createPortal(
    <KeyboardUI
      value={value}
      onKey={handleKey}
      onBackspace={handleBackspace}
      onShift={handleShift}
      shifted={shifted}
      onSpace={handleSpace}
      onChar={handleChar}
      onClose={onClose}
      numMode={numMode}
      onToggleNum={handleToggleNum}
    />,
    document.body
  )
}
