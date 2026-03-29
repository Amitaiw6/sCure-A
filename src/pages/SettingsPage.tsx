import { useState } from 'react'
import { Settings, Pencil } from 'lucide-react'

export default function SettingsPage() {
  const [timezone] = useState('None')
  const [networkTime, setNetworkTime] = useState(true)

  return (
    <main className="px-6 pb-8">
      {/* Date & Time header */}
      <div className="bg-gray-900/60 rounded-2xl p-5 mt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-gray-500 text-sm">Date & time</p>
            <h2 className="text-white text-lg font-semibold mt-1">Time zone</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-sm">Mar 2026,12:21 AM</span>
            <button className="text-gray-500 hover:text-white transition-colors">
              <Settings size={20} />
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mt-6">
        {/* Left column */}
        <div className="space-y-4">
          {/* Support */}
          <div className="bg-gray-900/60 rounded-2xl p-5">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-gray-700 rounded-xl flex items-center justify-center">
                <Settings size={24} className="text-gray-400" />
              </div>
              <span className="text-gray-400">Support</span>
              <button className="ml-auto bg-sky-500 hover:bg-sky-400 text-white text-sm font-semibold px-4 py-2 rounded-full transition-colors">
                Dump Logs (USB)
              </button>
            </div>

            <div className="mt-4 border-t border-gray-700 pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-gray-500 text-sm">Firmware Version</span>
                <span className="text-white text-sm font-medium">0.63.0-35676c1e-dev</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500 text-sm">Last Boot Time</span>
                <span className="text-white text-sm font-medium">2/25/2026, 8:23 AM</span>
              </div>
            </div>
          </div>

          {/* Name */}
          <div className="bg-gray-900/60 rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <span className="text-white font-semibold">Name:</span>
              <div className="flex items-center gap-2">
                <span className="text-white">Amitai</span>
                <button className="text-gray-500 hover:text-white transition-colors">
                  <Pencil size={16} />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right column - Date & Time */}
        <div className="bg-gray-900/60 rounded-2xl p-5">
          <h3 className="text-white font-bold mb-4">Date & Time</h3>

          <div className="space-y-4">
            {/* Time Zone */}
            <div>
              <label className="text-gray-400 text-sm block mb-2">Time Zone</label>
              <div className="bg-gray-800 border border-gray-600 rounded-xl px-4 py-2.5 text-white text-sm text-center">
                {timezone}
              </div>
            </div>

            {/* Automatic Sync */}
            <div className="flex items-center justify-between">
              <span className="text-gray-400 text-sm">Automatic Sync</span>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={networkTime}
                  onChange={e => setNetworkTime(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-sky-500 focus:ring-sky-500"
                />
                <span className="text-white text-sm">Network time</span>
              </label>
            </div>

            {/* Date / Time inputs */}
            <div className="flex gap-3">
              <div className="bg-gray-800 border border-gray-600 rounded-xl px-4 py-2.5 text-gray-300 text-sm">
                1 Mar 2026
              </div>
              <div className="bg-gray-800 border border-gray-600 rounded-xl px-4 py-2.5 text-gray-300 text-sm">
                12:17 AM
              </div>
            </div>

            {/* Buttons */}
            <div className="flex gap-3 mt-4">
              <button className="flex-1 py-2.5 rounded-xl bg-gray-600 text-white font-semibold hover:bg-gray-500 transition-colors">
                Cancel
              </button>
              <button className="flex-1 py-2.5 rounded-xl bg-orange-400 text-white font-semibold hover:bg-orange-300 transition-colors">
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
