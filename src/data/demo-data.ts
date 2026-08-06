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

export const DEMO_PRINTS: PrintLog[] = [
  {
    "csvFile": "presets/st45.csv",
    "date": "2026-07-23T09:00:00",
    "duration": 20,
    "id": "log-009",
    "materialName": "Loctite 3D 3843™ White (100µm)",
    "printName": "Job 1 - Penrose",
    "printerName": "TZ",
    "status": "completed",
    "steps": 3
  }
]

// Machine user programs snapshot (baked for the standalone simulator)
export const DEMO_USER_PROGRAMS: Material[] = [
  {
    "createdAt": "2026-08-04T07:43:44.907Z",
    "id": "708c4407-0399-4b95-a715-005979a7b036",
    "isPreset": false,
    "name": "cooling Copy",
    "steps": [
      {
        "coolingMode": "medium",
        "intensity": null,
        "process": "Cooling",
        "step": 1,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 0
  },
  {
    "createdAt": "2026-08-04T07:44:37.020Z",
    "id": "fe77ae0c-4729-44a3-9030-a800bb4736dd",
    "isPreset": false,
    "name": "c",
    "steps": [
      {
        "coolingMode": "medium",
        "intensity": null,
        "process": "Cooling",
        "step": 1,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 0
  },
  {
    "createdAt": "2026-08-04T09:09:02.625Z",
    "id": "35876fe2-5139-4fdc-a8de-fcc15277c87c",
    "isPreset": false,
    "name": "cooling Copy 2",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 75,
        "time": 10
      },
      {
        "coolingMode": "slow",
        "intensity": null,
        "process": "Cooling",
        "step": 2,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 10
  },
  {
    "createdAt": "2026-08-04T09:34:53.913Z",
    "id": "c0c88913-0bf9-403a-9256-e7256786f097",
    "isPreset": false,
    "name": "cooling Copy 3",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 75,
        "time": 10
      },
      {
        "coolingMode": "medium",
        "intensity": null,
        "process": "Cooling",
        "step": 2,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 10
  },
  {
    "createdAt": "2026-08-04T12:14:42.062Z",
    "id": "c8886a1d-5690-475e-8505-27482b428ec3",
    "isPreset": false,
    "name": "rom",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 80,
        "time": 50
      }
    ],
    "totalDuration": 50
  },
  {
    "createdAt": "2026-08-04T13:04:24.370Z",
    "id": "d0c808ab-698b-49c0-9910-f8067471f164",
    "isPreset": false,
    "name": "cool",
    "steps": [
      {
        "coolingMode": "fast",
        "intensity": null,
        "process": "Cooling",
        "step": 1,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 0
  },
  {
    "createdAt": "2026-08-04T14:17:32.174Z",
    "id": "4d755650-0b86-498a-8c1b-c36ec9169df3",
    "isPreset": false,
    "name": "h",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 50,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 2,
        "temperature": 60,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 3,
        "temperature": 70,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 4,
        "temperature": 80,
        "time": 5
      }
    ],
    "totalDuration": 20
  },
  {
    "createdAt": "2026-08-05T08:24:13.531Z",
    "id": "75fb1175-dffb-4750-8e7b-8aac27952989",
    "isPreset": false,
    "name": "Full test cycle 5.8",
    "steps": [
      {
        "intensity": null,
        "process": "Drying",
        "step": 1,
        "temperature": 40,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 2,
        "temperature": 50,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 3,
        "temperature": 60,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 4,
        "temperature": 70,
        "time": 5
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 5,
        "temperature": 80,
        "time": 5
      },
      {
        "intensity": 30,
        "process": "Cure",
        "step": 6,
        "temperature": 80,
        "time": 15,
        "uvIntensity": 100
      },
      {
        "coolingMode": "fast",
        "intensity": null,
        "process": "Cooling",
        "step": 7,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 40
  },
  {
    "createdAt": "2026-08-05T12:11:14.422Z",
    "id": "c93e1c85-b3f4-4fff-a578-d87b1c93ec12",
    "isPreset": false,
    "name": "80 degrees 30 min",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 80,
        "time": 30
      }
    ],
    "totalDuration": 30
  },
  {
    "createdAt": "2026-08-06T03:51:46.601Z",
    "id": "902c7260-5f39-40b9-a62b-2366a500871c",
    "isPreset": false,
    "name": "rr",
    "steps": [
      {
        "intensity": 30,
        "process": "Cure",
        "step": 1,
        "temperature": 40,
        "time": 10,
        "timerMode": "on-ramp",
        "uvStartMode": "at-start"
      }
    ],
    "totalDuration": 10
  },
  {
    "createdAt": "2026-08-06T04:09:33.078Z",
    "id": "2680216b-7d34-43b9-9665-41772c6fa2c2",
    "isPreset": false,
    "name": "ggg",
    "steps": [
      {
        "intensity": 30,
        "process": "Cure",
        "step": 1,
        "temperature": 30,
        "time": 10
      }
    ],
    "totalDuration": 10
  },
  {
    "createdAt": "2026-08-06T05:07:42.204Z",
    "id": "64714f3b-4473-4ab6-b51d-55d7258ce64c",
    "isPreset": false,
    "name": "ddff",
    "steps": [
      {
        "intensity": null,
        "process": "Drying",
        "step": 1,
        "temperature": 40,
        "time": 10
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 2,
        "temperature": 50,
        "time": 10
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 3,
        "temperature": 60,
        "time": 10
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 4,
        "temperature": 70,
        "time": 10
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 5,
        "temperature": 80,
        "time": 10
      },
      {
        "coolingMode": "fast",
        "intensity": null,
        "process": "Cooling",
        "step": 6,
        "temperature": 30,
        "time": 0
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 7,
        "temperature": 80,
        "time": 10
      },
      {
        "coolingMode": "medium",
        "intensity": null,
        "process": "Cooling",
        "step": 8,
        "temperature": 30,
        "time": 0
      },
      {
        "intensity": null,
        "process": "Heating",
        "step": 9,
        "temperature": 80,
        "time": 10
      },
      {
        "coolingMode": "slow",
        "intensity": null,
        "process": "Cooling",
        "step": 10,
        "temperature": 40,
        "time": 0
      }
    ],
    "totalDuration": 70
  },
  {
    "createdAt": "2026-08-06T05:37:27.179Z",
    "id": "e699c41a-86b2-4154-8d4f-09b919b02287",
    "isPreset": false,
    "name": "cooling",
    "steps": [
      {
        "intensity": null,
        "process": "Heating",
        "step": 1,
        "temperature": 70,
        "time": 10
      },
      {
        "coolingMode": "medium",
        "intensity": null,
        "process": "Cooling",
        "step": 2,
        "temperature": 30,
        "time": 0
      }
    ],
    "totalDuration": 10
  }
]
