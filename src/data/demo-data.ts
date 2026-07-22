// AUTO-GENERATED demo dataset (tools/_gen-demo.mjs).
// Fallback used ONLY when the backend API is unreachable, so the app shows data
// in dev / offline. When the Flask API + PostgreSQL run, the API is authoritative.
import type { Material } from '@/context/MaterialContext'
import type { PrintLog } from '@/context/PrintHistoryContext'

export const DEMO_PRESETS: Material[] = [
  {
    "id": "preset-ST45",
    "name": "ST45",
    "steps": [
      {
        "intensity": null,
        "time": 10,
        "step": 1,
        "process": "Drying",
        "temperature": 45
      },
      {
        "intensity": null,
        "time": 5,
        "step": 2,
        "process": "Heating",
        "temperature": 60
      },
      {
        "intensity": null,
        "time": 15,
        "step": 3,
        "process": "Cure",
        "temperature": 60,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      },
      {
        "intensity": null,
        "time": 5,
        "step": 5,
        "process": "Drying",
        "temperature": 40
      }
    ],
    "totalDuration": 35,
    "createdAt": "",
    "isPreset": true
  },
  {
    "id": "preset-Carbon Fiber",
    "name": "Carbon Fiber",
    "steps": [
      {
        "intensity": null,
        "time": 15,
        "step": 1,
        "process": "Drying",
        "temperature": 50
      },
      {
        "intensity": null,
        "time": 8,
        "step": 2,
        "process": "Heating",
        "temperature": 70
      },
      {
        "intensity": null,
        "time": 20,
        "step": 3,
        "process": "Cure",
        "temperature": 70,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-start"
      },
      {
        "intensity": null,
        "time": 10,
        "step": 4,
        "process": "Bleacher",
        "temperature": 70,
        "uvIntensity": 40,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 5,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "slow"
      },
      {
        "intensity": null,
        "time": 5,
        "step": 6,
        "process": "Drying",
        "temperature": 35
      }
    ],
    "totalDuration": 58,
    "createdAt": "",
    "isPreset": true
  },
  {
    "id": "preset-Fiberglass",
    "name": "Fiberglass",
    "steps": [
      {
        "intensity": null,
        "time": 8,
        "step": 1,
        "process": "Drying",
        "temperature": 45
      },
      {
        "intensity": null,
        "time": 5,
        "step": 2,
        "process": "Heating",
        "temperature": 55
      },
      {
        "intensity": null,
        "time": 15,
        "step": 3,
        "process": "Cure",
        "temperature": 55,
        "uvIntensity": 20,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      },
      {
        "intensity": null,
        "time": 5,
        "step": 5,
        "process": "Drying",
        "temperature": 30
      }
    ],
    "totalDuration": 33,
    "createdAt": "",
    "isPreset": true
  },
  {
    "id": "preset-ABS-Like",
    "name": "ABS-Like",
    "steps": [
      {
        "intensity": null,
        "time": 10,
        "step": 1,
        "process": "Drying",
        "temperature": 40
      },
      {
        "intensity": null,
        "time": 5,
        "step": 2,
        "process": "Heating",
        "temperature": 60
      },
      {
        "intensity": null,
        "time": 15,
        "step": 3,
        "process": "Cure",
        "temperature": 60,
        "uvIntensity": 40,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "slow"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 5,
        "process": "Nitrogen",
        "temperature": null
      },
      {
        "intensity": null,
        "time": 10,
        "step": 6,
        "process": "Heating",
        "temperature": 50
      },
      {
        "intensity": null,
        "time": 0,
        "step": 7,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 40,
    "createdAt": "",
    "isPreset": true
  },
  {
    "id": "preset-Dental Model",
    "name": "Dental Model",
    "steps": [
      {
        "intensity": null,
        "time": 5,
        "step": 1,
        "process": "Drying",
        "temperature": 35
      },
      {
        "intensity": null,
        "time": 20,
        "step": 2,
        "process": "Cure",
        "temperature": 40,
        "uvIntensity": 60,
        "timerMode": "on-target",
        "uvStartMode": "at-start"
      },
      {
        "intensity": null,
        "time": 10,
        "step": 3,
        "process": "Bleacher",
        "temperature": 40,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "slow"
      },
      {
        "intensity": null,
        "time": 5,
        "step": 5,
        "process": "Drying",
        "temperature": 30
      }
    ],
    "totalDuration": 40,
    "createdAt": "",
    "isPreset": true
  },
  {
    "id": "preset-Flexible",
    "name": "Flexible",
    "steps": [
      {
        "intensity": null,
        "time": 8,
        "step": 1,
        "process": "Drying",
        "temperature": 35
      },
      {
        "intensity": null,
        "time": 5,
        "step": 2,
        "process": "Heating",
        "temperature": 45
      },
      {
        "intensity": null,
        "time": 25,
        "step": 3,
        "process": "Cure",
        "temperature": 45,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "slow"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 5,
        "process": "Nitrogen",
        "temperature": null
      },
      {
        "intensity": null,
        "time": 10,
        "step": 6,
        "process": "Bleacher",
        "temperature": 40,
        "uvIntensity": 20,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 7,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      },
      {
        "intensity": null,
        "time": 5,
        "step": 8,
        "process": "Drying",
        "temperature": 30
      }
    ],
    "totalDuration": 53,
    "createdAt": "",
    "isPreset": true
  }
]

export const DEMO_USER_PROGRAMS: Material[] = [
  {
    "id": "demo-rigid-pa",
    "name": "Demo Rigid PA",
    "steps": [
      {
        "intensity": null,
        "time": 8,
        "step": 1,
        "process": "Heating",
        "temperature": 55
      },
      {
        "intensity": null,
        "time": 20,
        "step": 2,
        "process": "Cure",
        "temperature": 60,
        "uvIntensity": 40,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 3,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "slow"
      }
    ],
    "totalDuration": 28,
    "createdAt": "2026-06-20T09:00:00Z",
    "isPreset": false
  },
  {
    "id": "demo-flex-tpu",
    "name": "Demo Flexible TPU",
    "steps": [
      {
        "intensity": null,
        "time": 10,
        "step": 1,
        "process": "Drying",
        "temperature": 45
      },
      {
        "intensity": null,
        "time": 5,
        "step": 2,
        "process": "Heating",
        "temperature": 50
      },
      {
        "intensity": null,
        "time": 12,
        "step": 3,
        "process": "Cure",
        "temperature": 50,
        "uvIntensity": 25,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 27,
    "createdAt": "2026-06-20T09:00:00Z",
    "isPreset": false
  },
  {
    "id": "demo-tough-1500",
    "name": "Demo Tough 1500",
    "steps": [
      {
        "intensity": null,
        "time": 8,
        "step": 1,
        "process": "Heating",
        "temperature": 70
      },
      {
        "intensity": null,
        "time": 25,
        "step": 2,
        "process": "Cure",
        "temperature": 70,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-start"
      },
      {
        "intensity": null,
        "time": 10,
        "step": 3,
        "process": "Bleacher",
        "temperature": 70,
        "uvIntensity": 40,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "slow"
      }
    ],
    "totalDuration": 43,
    "createdAt": "2026-06-20T09:00:00Z",
    "isPreset": false
  },
  {
    "id": "demo-dental",
    "name": "Demo Dental Model",
    "steps": [
      {
        "intensity": null,
        "time": 5,
        "step": 1,
        "process": "Heating",
        "temperature": 40
      },
      {
        "intensity": null,
        "time": 0,
        "step": 2,
        "process": "Nitrogen",
        "temperature": null
      },
      {
        "intensity": null,
        "time": 15,
        "step": 3,
        "process": "Cure",
        "temperature": 40,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 20,
    "createdAt": "2026-06-20T09:00:00Z",
    "isPreset": false
  },
  {
    "id": "demo-castable",
    "name": "Demo Castable Wax",
    "steps": [
      {
        "intensity": null,
        "time": 8,
        "step": 1,
        "process": "Drying",
        "temperature": 40
      },
      {
        "intensity": null,
        "time": 4,
        "step": 2,
        "process": "Heating",
        "temperature": 45
      },
      {
        "intensity": null,
        "time": 10,
        "step": 3,
        "process": "Cure",
        "temperature": 45,
        "uvIntensity": 20,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "intensity": null,
        "time": 0,
        "step": 4,
        "process": "Cooling",
        "temperature": 25,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 22,
    "createdAt": "2026-06-20T09:00:00Z",
    "isPreset": false
  }
]

export const DEMO_PRINTS: PrintLog[] = [
  {
    "id": "log-001",
    "printName": "Print #008",
    "materialName": "st45",
    "printerName": "OR200001",
    "date": "2026-03-29T10:30:00",
    "duration": 20,
    "status": "completed",
    "steps": 3,
    "csvFile": "presets/st45.csv"
  },
  {
    "id": "log-002",
    "printName": "Print #007",
    "materialName": "Carbon Fiber",
    "printerName": "OR200001",
    "date": "2026-03-28T14:15:00",
    "duration": 48,
    "status": "completed",
    "steps": 4,
    "csvFile": "presets/carbon_fiber.csv"
  },
  {
    "id": "log-003",
    "printName": "Print #006",
    "materialName": "Fiberglass",
    "printerName": "OR200001",
    "date": "2026-03-27T09:00:00",
    "duration": 35,
    "status": "aborted",
    "steps": 4,
    "csvFile": "presets/fiberglass.csv"
  },
  {
    "id": "log-004",
    "printName": "Print #005",
    "materialName": "st45",
    "printerName": "OR200001",
    "date": "2026-03-26T16:45:00",
    "duration": 20,
    "status": "completed",
    "steps": 3,
    "csvFile": "presets/st45.csv"
  },
  {
    "id": "log-005",
    "printName": "Print #004",
    "materialName": "Carbon Fiber",
    "printerName": "OR200002",
    "date": "2026-03-25T11:20:00",
    "duration": 48,
    "status": "completed",
    "steps": 4,
    "csvFile": "presets/carbon_fiber.csv"
  },
  {
    "id": "log-006",
    "printName": "Print #003",
    "materialName": "Fiberglass",
    "printerName": "OR200001",
    "date": "2026-03-24T08:00:00",
    "duration": 35,
    "status": "completed",
    "steps": 4,
    "csvFile": "presets/fiberglass.csv"
  },
  {
    "id": "log-007",
    "printName": "Print #002",
    "materialName": "st45",
    "printerName": "OR200001",
    "date": "2026-03-23T13:30:00",
    "duration": 20,
    "status": "error",
    "steps": 3,
    "csvFile": "presets/st45.csv"
  },
  {
    "id": "log-008",
    "printName": "Print #001",
    "materialName": "Carbon Fiber",
    "printerName": "OR200002",
    "date": "2026-03-22T10:00:00",
    "duration": 48,
    "status": "completed",
    "steps": 4,
    "csvFile": "presets/carbon_fiber.csv"
  }
]
