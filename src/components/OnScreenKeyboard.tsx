import { useState } from 'react'

interface OnScreenKeyboardProps {
  isOpen: boolean
  value: string
  onChange: (value: string) => void
  onClose: () => void
}

const rows = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', '!', '?'],
]

export default function OnScreenKeyboard({ isOpen, value, onChange, onClose }: OnScreenKeyboardProps) {
  const [shifted, setShifted] = useState(false)

  if (!isOpen) return null

  const handleKey = (key: string) => {
    onChange(value + (shifted ? key.toUpperCase() : key))
    setShifted(false)
  }

  const handleBackspace = () => {
    onChange(value.slice(0, -1))
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 bg-[#2a2a3e] border-t border-gray-700 p-4">
      {/* Input display */}
      <div className="flex items-center justify-between mb-4 px-2">
        <p className="text-white text-lg font-semibold">{value}<span className="animate-pulse">|</span></p>
        <button
          onClick={onClose}
          className="bg-gray-300 text-gray-800 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-white transition-colors"
        >
          Close Keyboard
        </button>
      </div>

      {/* Keys */}
      <div className="flex flex-col items-center gap-2">
        {/* Row 1 */}
        <div className="flex gap-1.5">
          {rows[0].map(key => (
            <button key={key} onClick={() => handleKey(key)}
              className="w-[72px] h-[52px] bg-gray-600 rounded-lg text-white text-lg font-medium hover:bg-gray-500 transition-colors relative">
              {shifted ? key.toUpperCase() : key}
              <span className="absolute top-1 right-2 text-[10px] text-gray-400">
                {rows[0].indexOf(key) + 1 <= 9 ? rows[0].indexOf(key) + 1 : 0}
              </span>
            </button>
          ))}
          <button onClick={handleBackspace}
            className="w-[72px] h-[52px] bg-red-500 rounded-lg text-white text-lg hover:bg-red-400 transition-colors flex items-center justify-center">
            ⌫
          </button>
        </div>

        {/* Row 2 */}
        <div className="flex gap-1.5 ml-8">
          {rows[1].map(key => (
            <button key={key} onClick={() => handleKey(key)}
              className="w-[72px] h-[52px] bg-gray-600 rounded-lg text-white text-lg font-medium hover:bg-gray-500 transition-colors">
              {shifted ? key.toUpperCase() : key}
            </button>
          ))}
        </div>

        {/* Row 3 */}
        <div className="flex gap-1.5">
          <button onClick={() => setShifted(!shifted)}
            className={`w-[72px] h-[52px] rounded-lg text-white text-lg hover:bg-gray-500 transition-colors ${shifted ? 'bg-gray-500' : 'bg-gray-700'}`}>
            ⇧
          </button>
          {rows[2].map(key => (
            <button key={key} onClick={() => handleKey(key)}
              className="w-[72px] h-[52px] bg-gray-600 rounded-lg text-white text-lg font-medium hover:bg-gray-500 transition-colors">
              {shifted ? key.toUpperCase() : key}
            </button>
          ))}
          <button onClick={() => setShifted(!shifted)}
            className={`w-[72px] h-[52px] rounded-lg text-white text-lg hover:bg-gray-500 transition-colors ${shifted ? 'bg-gray-500' : 'bg-gray-700'}`}>
            ⇧
          </button>
        </div>

        {/* Row 4 - Space bar */}
        <div className="flex gap-1.5">
          <button className="w-[72px] h-[52px] bg-gray-700 rounded-lg text-white text-sm hover:bg-gray-500 transition-colors">
            ?123
          </button>
          <button onClick={() => handleKey(',')}
            className="w-[52px] h-[52px] bg-gray-600 rounded-lg text-white text-lg hover:bg-gray-500 transition-colors">
            ,
          </button>
          <button onClick={() => handleKey(' ')}
            className="w-[360px] h-[52px] bg-gray-600 rounded-lg text-white hover:bg-gray-500 transition-colors" />
          <button className="w-[52px] h-[52px] bg-gray-600 rounded-lg text-white text-lg hover:bg-gray-500 transition-colors">
            😊
          </button>
          <button onClick={() => handleKey('.')}
            className="w-[52px] h-[52px] bg-gray-600 rounded-lg text-white text-lg hover:bg-gray-500 transition-colors">
            .
          </button>
          <button onClick={onClose}
            className="w-[90px] h-[52px] bg-sky-500 rounded-lg text-white text-sm font-semibold hover:bg-sky-400 transition-colors">
            Return
          </button>
        </div>
      </div>
    </div>
  )
}
