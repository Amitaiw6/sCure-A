import TopBar from './components/TopBar'
import SectionHeader from './components/SectionHeader'
import MaterialItem from './components/MaterialItem'
import StartCureButton from './components/StartCureButton'

function App() {
  return (
    <div className="min-h-screen bg-[#1a1a2e]">
      <div className="max-w-4xl mx-auto">
        <TopBar />

        <main className="px-6 pb-24">
          {/* NFC Section */}
          <SectionHeader title="NFC" />
          <MaterialItem label="Label text" duration="15min" />

          {/* Material List Section */}
          <SectionHeader title="Material List" showActions />
          <MaterialItem label="st45" duration="20min" />
          <MaterialItem label="Label text" duration="30min" />
          <MaterialItem label="Label text" duration="⌘C" isCommand />
          <MaterialItem label="Label text" duration="⌘C" isCommand />
          <MaterialItem label="Label text" />
        </main>

        <StartCureButton />
      </div>
    </div>
  )
}

export default App
