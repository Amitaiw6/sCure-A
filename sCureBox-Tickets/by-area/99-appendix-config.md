## Appendix A — shipped config files (verbatim, sCureBox-CS 1.0.152)

Create these files exactly as below under config/. They are the data the Domain, Hardware and UI tickets refer to. config/versions.json (release history, 256 KB) is not reproduced: start it with a single entry for your first version (format in the Deploy-Ops versioning ticket).

### config/errors.json

```json
{
  "_meta": {
    "version": "4.0.0",
    "lastUpdated": "2026-10-25",
    "description": "sCure central Error Registry — the single source of truth for every error/warning. Each record has a stable, unique numeric code whose FIRST DIGIT identifies the SRS section/screen the error is documented in (3=Setup, 4=Setup Name, 5=Connect Organization, 6=Home, 7=Cure Process, 8=Cure History, 9=Error Management: device/hardware alerts + cross-cutting system faults). The code is carried UNCHANGED across every layer (C++ driver/daemon -> Flask backend -> React UI); the originating subsystem is recorded in the per-record \"layer\" field. CS may edit message, description, troubleshooting and supportUrl; code, key, severity, category and layer are system-defined.",
    "editableFields": [
      "message",
      "description",
      "troubleshooting",
      "supportUrl"
    ],
    "systemFields": [
      "code",
      "key",
      "severity",
      "category",
      "layer"
    ],
    "ranges": [
      {
        "from": 3000,
        "to": 3999,
        "section": "3",
        "label": "Setup Screen"
      },
      {
        "from": 4000,
        "to": 4999,
        "section": "4",
        "label": "Setup Name Screen"
      },
      {
        "from": 5000,
        "to": 5999,
        "section": "5",
        "label": "Connect Organization Screen"
      },
      {
        "from": 6000,
        "to": 6999,
        "section": "6",
        "label": "Home Screen (material list, recipe builder, CSV import, view-all, start cure)"
      },
      {
        "from": 7000,
        "to": 7999,
        "section": "7",
        "label": "Cure Process Screen"
      },
      {
        "from": 8000,
        "to": 8999,
        "section": "8",
        "label": "Cure History Screen"
      },
      {
        "from": 9000,
        "to": 9999,
        "section": "9",
        "label": "Error Management — device/hardware alerts (9001-9079) + cross-cutting system/backend faults (9080-9099)"
      }
    ]
  },
  "support": {
    "email": "support@scure.com",
    "phone": "+1-800-123-4567",
    "chat": "https://scure.com/support/chat",
    "docsBase": "https://docs.scure.com/errors"
  },
  "errors": [
    {
      "code": 3001,
      "key": "SERIAL_RESTORE_FAILED",
      "message": "Serial Number Restore Failed",
      "severity": "critical",
      "category": "provisioning",
      "layer": "daemon",
      "description": "During setup the serial number could not be restored from the SD backup to device storage. Provisioning cannot continue until a valid serial number is available.",
      "troubleshooting": [
        "Check the SD card is seated and readable",
        "Verify the backup configuration file exists on SD",
        "Reboot and retry setup",
        "Contact support to re-provision the serial number"
      ],
      "supportUrl": "https://docs.scure.com/errors/3001",
      "videoUrl": ""
    },
    {
      "code": 3002,
      "key": "CLOUD_COMM_FAILED",
      "message": "Cloud Communication Failed",
      "severity": "critical",
      "category": "provisioning",
      "layer": "backend",
      "description": "During setup, the device could not obtain a serial number from the cloud within the allowed number of attempts due to a communication problem.",
      "troubleshooting": [
        "Check the internet connection",
        "Verify the device can reach the sCure cloud service",
        "Retry the request",
        "Contact support if the cloud remains unreachable"
      ],
      "supportUrl": "https://docs.scure.com/errors/3002",
      "videoUrl": ""
    },
    {
      "code": 3003,
      "key": "SETUP_NO_INTERNET",
      "message": "No Internet Connection",
      "severity": "warning",
      "category": "network",
      "layer": "backend",
      "description": "During setup the device has no internet connection, so it cannot request a serial number from the cloud. Restore the network connection and retry.",
      "troubleshooting": [
        "Connect the Ethernet cable",
        "Verify the network/router is online",
        "Retry once the connection is restored"
      ],
      "supportUrl": "https://docs.scure.com/errors/3003",
      "videoUrl": ""
    },
    {
      "code": 4001,
      "key": "INVALID_DEVICE_NAME",
      "message": "Invalid Device Name",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "The device name entered on the Setup Name screen is empty. A non-empty name is required to continue.",
      "troubleshooting": [
        "Enter a name for the device",
        "The name cannot consist of spaces only"
      ],
      "supportUrl": "https://docs.scure.com/errors/4001",
      "videoUrl": ""
    },
    {
      "code": 4002,
      "key": "DATA_FILE_WRITE_FAILED",
      "message": "Data File Write Failed",
      "severity": "critical",
      "category": "storage",
      "layer": "backend",
      "description": "The backend could not persist a data file (user materials or print history) to the device storage.",
      "troubleshooting": [
        "Check available space on the device",
        "Reboot the system and retry",
        "Contact support if the fault persists"
      ],
      "supportUrl": "https://docs.scure.com/errors/4002",
      "videoUrl": ""
    },
    {
      "code": 4003,
      "key": "SD_BACKUP_WRITE_FAILED",
      "message": "SD Backup Write Failed",
      "severity": "warning",
      "category": "storage",
      "layer": "backend",
      "description": "The configuration was saved to primary storage but the secondary backup copy to the SD card failed. Whether this blocks setup or is only a warning is determined by system policy.",
      "troubleshooting": [
        "Check the SD card is inserted and writable",
        "Verify free space on the SD card",
        "Reboot and retry; the primary configuration is already saved"
      ],
      "supportUrl": "https://docs.scure.com/errors/4003",
      "videoUrl": ""
    },
    {
      "code": 5001,
      "key": "ORG_ID_NOT_FOUND",
      "message": "No Organization ID in File",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "The selected organization CSV file does not contain a valid organization ID (UUID).",
      "troubleshooting": [
        "Select the correct organization CSV exported from the portal",
        "Verify the file contains a valid organization UUID"
      ],
      "supportUrl": "https://docs.scure.com/errors/5001",
      "videoUrl": ""
    },
    {
      "code": 6001,
      "key": "PROGRAM_NAME_REQUIRED",
      "message": "Program Name Required",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "The recipe builder cannot save a program without a name.",
      "troubleshooting": [
        "Enter a program name before saving"
      ],
      "supportUrl": "https://docs.scure.com/errors/6001",
      "videoUrl": ""
    },
    {
      "code": 6002,
      "key": "NO_STEPS_DEFINED",
      "message": "No Steps Defined",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "The recipe builder cannot save a program with zero steps.",
      "troubleshooting": [
        "Add at least one step to the program"
      ],
      "supportUrl": "https://docs.scure.com/errors/6002",
      "videoUrl": ""
    },
    {
      "code": 6003,
      "key": "N2_SEQUENCE_INVALID",
      "message": "Invalid N₂ Purge Sequence",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "An N₂ purge step is not followed by the required sequence: N₂ → (Cure | Bleaching) → Cooling.",
      "troubleshooting": [
        "After an N₂ purge, add a Cure or Bleaching step",
        "After that Cure/Bleaching, add a Cooling step"
      ],
      "supportUrl": "https://docs.scure.com/errors/6003",
      "videoUrl": ""
    },
    {
      "code": 6004,
      "key": "STEP_TEMP_TOO_LOW",
      "message": "Step Temperature Too Low",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "A non-cooling step's temperature is lower than the previous non-cooling step. Temperatures must not decrease except in a Cooling step.",
      "troubleshooting": [
        "Raise the step temperature to at least the previous step's temperature",
        "Use a Cooling step to lower the temperature"
      ],
      "supportUrl": "https://docs.scure.com/errors/6004",
      "videoUrl": ""
    },
    {
      "code": 6005,
      "key": "COOLING_TEMP_INVALID",
      "message": "Invalid Cooling Temperature",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "A Cooling step's target temperature is not lower than the temperature of the preceding step.",
      "troubleshooting": [
        "Set the Cooling target below the previous step's temperature"
      ],
      "supportUrl": "https://docs.scure.com/errors/6005",
      "videoUrl": ""
    },
    {
      "code": 6006,
      "key": "CSV_STRUCTURE_INVALID",
      "message": "Invalid CSV Structure",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "An imported program CSV is missing a required header or contains no data row.",
      "troubleshooting": [
        "Use a CSV exported by the recipe builder",
        "Check the header row and that at least one step is present"
      ],
      "supportUrl": "https://docs.scure.com/errors/6006",
      "videoUrl": ""
    },
    {
      "code": 6007,
      "key": "CSV_INVALID_PROCESS",
      "message": "Invalid CSV Process",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "A row in the imported CSV names a process that is not recognized (expected Heating, Drying, Cure, Bleaching, Cooling, or Nitrogen).",
      "troubleshooting": [
        "Correct the process name in the offending row",
        "Re-export the CSV from the recipe builder"
      ],
      "supportUrl": "https://docs.scure.com/errors/6007",
      "videoUrl": ""
    },
    {
      "code": 6008,
      "key": "CSV_INVALID_TEMP",
      "message": "Invalid CSV Temperature",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "A row in the imported CSV has a temperature outside the accepted range (30–80°C; Cooling steps 20–75°C).",
      "troubleshooting": [
        "Set the row temperature between 30°C and 80°C (20–75°C for Cooling steps)"
      ],
      "supportUrl": "https://docs.scure.com/errors/6008",
      "videoUrl": ""
    },
    {
      "code": 6009,
      "key": "CSV_INVALID_TIME",
      "message": "Invalid CSV Time",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "A row in the imported CSV has a time outside the accepted range (1–120 minutes; Bleaching: 1–720 minutes). Note: per-step time has since been removed from the recipe model; this check is retained only for legacy CSV files.",
      "troubleshooting": [
        "Correct the time value in the offending row",
        "Re-export the CSV from the current recipe builder"
      ],
      "supportUrl": "https://docs.scure.com/errors/6009",
      "videoUrl": ""
    },
    {
      "code": 6010,
      "key": "CSV_TOO_MANY_N2",
      "message": "Too Many Nitrogen Steps",
      "severity": "warning",
      "category": "validation",
      "layer": "ui",
      "description": "The imported CSV defines more than the maximum of 2 nitrogen purge steps.",
      "troubleshooting": [
        "Reduce the program to at most 2 nitrogen purge steps"
      ],
      "supportUrl": "https://docs.scure.com/errors/6010",
      "videoUrl": ""
    },
    {
      "code": 6011,
      "key": "CSV_SAVE_FAILED",
      "message": "CSV Save Failed",
      "severity": "warning",
      "category": "io",
      "layer": "ui",
      "description": "The recipe builder could not save the generated program CSV to USB; the file was downloaded in the browser instead.",
      "troubleshooting": [
        "Insert a writable USB drive and retry",
        "Use the downloaded file from the browser instead"
      ],
      "supportUrl": "https://docs.scure.com/errors/6011",
      "videoUrl": ""
    },
    {
      "code": 6012,
      "key": "MIXED_MATERIALS_SELECTED",
      "message": "Mixed Materials Selected",
      "severity": "warning",
      "category": "selection",
      "layer": "ui",
      "description": "A Cure Together batch may only combine prints of the same material. Two or more different materials were selected.",
      "troubleshooting": [
        "Select prints that all use the same material",
        "Run different materials as separate cures"
      ],
      "supportUrl": "https://docs.scure.com/errors/6012",
      "videoUrl": ""
    },
    {
      "code": 6013,
      "key": "NO_MATERIAL_SELECTED",
      "message": "No Material Selected",
      "severity": "warning",
      "category": "selection",
      "layer": "ui",
      "description": "Start Cure was pressed with no material or print selected.",
      "troubleshooting": [
        "Select a material or a recent print before starting a cure"
      ],
      "supportUrl": "https://docs.scure.com/errors/6013",
      "videoUrl": ""
    },
    {
      "code": 6014,
      "key": "PROGRAM_NOT_RUNNABLE",
      "message": "Cannot Start Program",
      "severity": "warning",
      "category": "selection",
      "layer": "ui",
      "description": "The selected program cannot run as configured — e.g. it is nitrogen-only while nitrogen is disabled, so every step would be skipped.",
      "troubleshooting": [
        "Enable nitrogen in Settings, or",
        "Choose a program that has non-nitrogen steps"
      ],
      "supportUrl": "https://docs.scure.com/errors/6014",
      "videoUrl": ""
    },
    {
      "code": 6015,
      "key": "PRECURE_CHECK_FAILED",
      "message": "Pre-Cure Check Failed",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The pre-cure hardware check did not pass (e.g. chamber not ready, door/seal open, or N₂ line not pressurized). The cure was not started and no outputs were energized.",
      "troubleshooting": [
        "Close and seal the chamber door",
        "Verify the N₂ line pressure (if nitrogen is enabled)",
        "Wait for the chamber to report ready, then retry",
        "Run diagnostics from Settings if the check keeps failing"
      ],
      "supportUrl": "https://docs.scure.com/errors/6015",
      "videoUrl": ""
    },
    {
      "code": 6016,
      "key": "DOOR_OPENED_MID_PROCESS",
      "message": "Door Opened — Process Aborted",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The chamber door was opened during an active process and remained open for more than 10 seconds. The process cannot continue while the door is open, so for your safety it was stopped and all outputs were switched off (heater, UV, cooling, fans, nitrogen). The interrupted cure cannot be resumed.",
      "troubleshooting": [
        "Close and seal the chamber door",
        "Inspect the part — an interrupted cure may be incomplete",
        "Start a new cure program from the beginning",
        "If the door was not physically opened, check the door sensor (GPIO27)"
      ],
      "supportUrl": "https://docs.scure.com/errors/6016",
      "videoUrl": ""
    },
    {
      "code": 7001,
      "key": "INVALID_TARGET_TEMP",
      "message": "Invalid Target Temperature",
      "severity": "warning",
      "category": "validation",
      "layer": "backend",
      "description": "A cure operation requested a target temperature outside the accepted range (heating 30–80°C; cooling 20–80°C). The backend rejected the command and no outputs were energized.",
      "troubleshooting": [
        "Edit the recipe step so the heating target is between 30°C and 80°C (cooling 20–80°C)",
        "Re-import the program CSV if the value came from a file"
      ],
      "supportUrl": "https://docs.scure.com/errors/7001",
      "videoUrl": ""
    },
    {
      "code": 7002,
      "key": "INVALID_UV_INTENSITY",
      "message": "Invalid UV Intensity",
      "severity": "warning",
      "category": "validation",
      "layer": "backend",
      "description": "A Cure (405 nm) or Bleaching (450 nm) step requested a UV intensity outside the accepted 10–100% range. The backend rejected the command.",
      "troubleshooting": [
        "Set the UV intensity between 10% and 100%",
        "Re-import the program CSV if the value came from a file"
      ],
      "supportUrl": "https://docs.scure.com/errors/7002",
      "videoUrl": ""
    },
    {
      "code": 7003,
      "key": "INVALID_COOLING_MODE",
      "message": "Invalid Cooling Mode",
      "severity": "warning",
      "category": "validation",
      "layer": "backend",
      "description": "A cooling step requested a mode other than fast, medium or slow. The backend rejected the command.",
      "troubleshooting": [
        "Set the cooling mode to fast, medium or slow",
        "Re-import the program CSV if the value came from a file"
      ],
      "supportUrl": "https://docs.scure.com/errors/7003",
      "videoUrl": ""
    },
    {
      "code": 7004,
      "key": "CURE_TEMP_STALL",
      "message": "Cure Temperature Stall",
      "severity": "warning",
      "category": "process",
      "layer": "ui",
      "description": "During a cure, the chamber temperature failed to move toward its target across five consecutive 5-minute stall checks. The user is warned that continuing may distort the printed models, and may Continue or Abort.",
      "troubleshooting": [
        "Choose Abort to stop, or Continue at your own risk",
        "If the chamber does not heat at all, check the voltage selector next to the mains inlet: it must sit fully in the 230 V or 115 V detent that matches your country's mains — a mid position is an open circuit and the heater receives no power",
        "Check heater/cooling operation and chamber insulation",
        "Run diagnostics from Settings"
      ],
      "supportUrl": "https://docs.scure.com/errors/7004",
      "videoUrl": ""
    },
    {
      "code": 7005,
      "key": "CURE_ABORTED",
      "message": "Cure Aborted",
      "severity": "warning",
      "category": "process",
      "layer": "ui",
      "description": "A cure run was aborted (by the user from the active phase, or from the Temperature Warning). The session is logged with status aborted and the device returns to Home.",
      "troubleshooting": [
        "Review the cure history entry for the aborted run",
        "Restart the cure when ready"
      ],
      "supportUrl": "https://docs.scure.com/errors/7005",
      "videoUrl": ""
    },
    {
      "code": 9001,
      "key": "TEMP_SENSOR_DISCONNECTED",
      "message": "Temperature Sensor Disconnected",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9010 (chamber), 9011 (left), 9012 (right), one code per component. Kept so older reports and logs still show a title. A required temperature sensor has read open-circuit for at least 60 seconds - the input sits at the 3.3 V pull-up rail, so there is no temperature. The line above names every sensor that is not reading, by its place in the machine. The check runs at system start-up, every second while running, and again right before every process start. No process can start while a required sensor is open. The heater is never switched on while its own sensor (the chamber NTC) is not reading: a heating step or the Settings heating slider is refused and the screen pops the fault (no continue-anyway), and a heater that is already running is switched off at once - in that case the alert is raised immediately, not after the minute.",
      "troubleshooting": [
        "Check the cable and IO-board connector of the sensor named above",
        "Check the common ground of the thermistor harness - all sensors jump to 3.3 V together when it opens",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The alert clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9001",
      "videoUrl": ""
    },
    {
      "code": 9002,
      "key": "FAN_FAILURE",
      "message": "Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9020-9025 (one per fan), one code per component. Kept so older reports and logs still show a title. A fan has been running at least 20 % below its nominal speed for a full minute (measured by its tachometer against the nominal RPM table for the commanded duty); a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is replaced. The line above names every fan that failed, with its measured and expected RPM.",
      "troubleshooting": [
        "Find the fan named in the line above",
        "Check the fan connector and that the blades turn freely",
        "Replace the fan; the alert clears by itself once the fan runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9002",
      "videoUrl": ""
    },
    {
      "code": 9003,
      "key": "LED_FAN_NOT_SPINNING",
      "message": "Cooling Fan Not Spinning - Job Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9030-9033 (LED fans), 9034 (chamber cooling fan), one code per component. Kept so older reports and logs still show a title. Before the UV LEDs are switched on, every LED cooling fan is spun up and its tachometer is read. An LED fan did not turn (disconnected, blocked or dead), so the LEDs were not switched on and the job did not start. The line above names every LED fan that did not spin. Since 1.0.62 the same spin test runs on the chamber cooling fan (FAN_COOLING) before a DRYING or COOLING step starts - the steps that use that fan - so such a step cannot start with the chamber fan unplugged (DVT-SAF-006); heating and UV steps do not test it; the alert then reads 'Chamber cooling fan not spinning: Chamber cooling fan (FAN_COOLING): 0 RPM - job start refused'.",
      "troubleshooting": [
        "The alert names the fan: one of the four LED fans, or the chamber cooling fan (FAN_COOLING) - check that fan's connector and that its blades turn freely",
        "Find the fan named in the line above",
        "Check the fan connector on the LED module and that the blades turn freely",
        "Run the LED fan test in Settings - every one of the four fans is reported",
        "Replace the fan; the job can start as soon as all four fans spin"
      ],
      "supportUrl": "https://docs.scure.com/errors/9003",
      "videoUrl": ""
    },
    {
      "code": 9004,
      "key": "LED_NOT_HEATING",
      "message": "LED Panel Not Heating - Check LED Connection",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9040 (left), 9041 (right), 9044 (back), 9045 (door), one code per component. Kept so older reports and logs still show a title. A lit Left or Right LED panel has not warmed its thermistor: after 90 seconds of light at 30 % system power or more, the panel temperature (regular Left / Right thermistor) has risen by less than 1.0 C above its temperature when the light started (a working panel rises by about 1.7 C in that time, LED fans on). The panel is therefore not receiving current - its power connector or driver output is open - and it is not curing. The alert names the panel and its measured rise. The process keeps running; the panel is re-checked on every UV step and the alert clears by itself as soon as the panel heats again.",
      "troubleshooting": [
        "Check that the power connector of the LED panel named in the alert (Left or Right) is plugged in and locked (LED_OUT connector on the driver side and the panel side)",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay)",
        "Run Diagnostics > LED test and watch the Left / Right temperatures: they must rise within 90 s of light at 30 %",
        "The alert clears by itself once the panel warms by at least 1 C during a UV step"
      ],
      "supportUrl": "https://docs.scure.com/errors/9004",
      "videoUrl": ""
    },
    {
      "code": 9005,
      "key": "LED_PANEL_TEMP_DROP",
      "message": "LED Panel Fault - Temperature Dropped During Cure",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9042 (left), 9043 (right), one code per component. Kept so older reports and logs still show a title. A Left or Right LED panel that had warmed up normally cooled down while its light was still commanded on: its thermistor fell by 1.0 C or more below the peak it had reached at this power level (any fall of the chamber temperature over the same time is taken off first) and stayed there for 30 seconds. The panel has stopped receiving current mid-process - a loose connector, a dropped driver output - so it is no longer curing. The alert names the panel with the measured fall. The process keeps running; the alert clears by itself once the panel climbs back to within 0.5 C of its peak while lit. A power-level change is given 120 s to settle before the peak is tracked again; a re-light re-judges the panel from its re-light temperature.",
      "troubleshooting": [
        "Check that the power connector of the LED panel named in the alert (Left or Right) is seated and locked - a connector that works loose under vibration or heat causes exactly this",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay) and its wiring",
        "Watch the Left / Right temperatures on Diagnostics > LED test: a healthy panel holds or climbs while lit",
        "Run the cure again once the connection is fixed - the alert clears when the panel heats normally"
      ],
      "supportUrl": "https://docs.scure.com/errors/9005",
      "videoUrl": ""
    },
    {
      "code": 9006,
      "key": "TEMP_READING_FROZEN",
      "message": "Temperature Reading Frozen - Heater Switched Off",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The heater's temperature reading (chamber NTC TEMP_CHAMBER) did not move by 0.01 C in a minute and a half while the heater was driving at 50 % output or more. A reading that is plausible but frozen - a fixed resistor in place of the sensor, a stuck ADC, a stuck reader - passes every range check and lets the control loop drive the heater at full output for as long as heating is allowed, so it is treated as no reading at all: the heater is switched off at once, the alert names the reading and the number it is stuck at, and every HEAT command is refused until the reading moves again. A chamber holding its setpoint is never judged: near the target the heater output falls below 50 % and the window restarts. The machine restarts itself one minute after the alert (a reading that never moves is also what a stuck sensor reader looks like); the latch is kept on disk, so heating stays refused after the restart until the reading moves. The alert clears by itself once the reading moves by 1 C or more (a real sensor put back) or goes open (then 9001 takes over).",
      "troubleshooting": [
        "Check that the chamber thermistor TEMP_CHAMBER is the real NTC, seated in the chamber, and that its connector on the IO board is the right one",
        "The machine restarts by itself a minute after the alert - wait for it to come back; heating stays refused until the reading moves",
        "Watch the chamber temperature on Diagnostics: a live sensor moves while the heater runs",
        "Measure the thermistor: about 12 kOhm at room temperature and changing with the chamber - a fixed resistance is not a sensor",
        "The alert clears by itself once the reading moves again; heating is refused until then"
      ],
      "supportUrl": "https://docs.scure.com/errors/9006",
      "videoUrl": ""
    },
    {
      "code": 9007,
      "key": "HEATER_NOT_HEATING",
      "message": "Heater Not Heating - Check Voltage Selector / Fuse",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The heater was driven at full output (99 % or more) for ten minutes and the chamber rose less than 0.5 C above its lowest reading of that window: the heater is getting no power. The usual causes are the 110 / 230 V voltage selector parked between its positions, or a blown heater fuse - both leave the controller at full output with nothing heating, and before this rule no alarm was raised (measured 2026-10-01, selector in the middle: 2.5 min at 100 %, chamber 35.0 -> 32.1 C). The heater is switched off at once and the alert names both causes. Normal heating at full output raises the chamber about 8 C in two minutes from cold, and still 2-6 C in ten minutes near 75-80 C, where the two-minute window used to stop working heaters (2026-10-11). The alert clears when the heater is driven again (a new heating start), which judges it afresh. Judged on the ramp up only (2026-11-04): once the chamber has reached its target (within 1.5 C) it is not judged until the next heating start or a new target - at 80 C the UV LED fans at 100 % held the chamber at 72 C with the heater at full output, and the rule stopped a working heater.",
      "troubleshooting": [
        "Check the 110 / 230 V voltage selector is fully in its position (not between the two)",
        "Check the heater fuse; replace it with the rated fuse if it has blown",
        "Start heating again - the alert clears and the chamber must rise within ten minutes"
      ],
      "supportUrl": "https://docs.scure.com/errors/9007",
      "videoUrl": ""
    },
    {
      "code": 9008,
      "key": "N2_PRESSURE_TOO_HIGH",
      "message": "Nitrogen Supply Pressure Too High - Nitrogen Closed",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The nitrogen line pressure measured by the N2 pressure sensor is above the allowed maximum (components.json pressure_sensor.max_bar, 3 bar by default). Nitrogen is never opened above the limit: a request to open the valve (a program's nitrogen step, POST /api/cure/nitrogen) is refused with this code, and if the pressure rises above the limit while the valve is open the valve is closed at once by the 1-second supervision check. The alert names the measured pressure and the limit, e.g. 'N2 supply pressure too high (3.4 bar > 3.0 bar) - nitrogen closed. Lower the regulator below 3 bar.' It clears by itself once the pressure is back at or under the limit; the valve is not reopened by itself - the next nitrogen request opens it. Only a real pressure value counts: with no reading (sensor error, switch mode, saturated input) nothing is blocked.",
      "troubleshooting": [
        "Lower the nitrogen regulator so the line pressure reads below 3 bar on Settings (N2 Pressure)",
        "Check the regulator holds its setting - a creeping regulator lets the pressure rise during a purge",
        "The alert clears by itself once the pressure is under the limit; then start the nitrogen step / program again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9008",
      "videoUrl": ""
    },
    {
      "code": 9009,
      "key": "N2_NO_SUPPLY",
      "message": "No Nitrogen Supply - Line Pressure Too Low",
      "severity": "warning",
      "category": "process",
      "layer": "backend",
      "description": "Nitrogen was requested (a program's nitrogen step, POST /api/cure/nitrogen, or Nitrogen Mode in Settings) while the nitrogen line pressure is below the minimum (components.json pressure_sensor.min_bar, 0.5 bar by default): there is no nitrogen supply to the system, so the valve is not opened and the request is refused with the text 'No nitrogen supply - line pressure X.X bar is below 0.5 bar. Check the nitrogen line and regulator.' The low limit is judged only on a reading taken with the valve CLOSED and settled (3 s after it last closed): while the valve is open the gas flows and the line reads near 0 bar, which is normal and never closes the valve or raises this code. With no reading (sensor error, switch mode, saturated input) nothing is blocked.",
      "troubleshooting": [
        "Check the nitrogen cylinder / generator is on and not empty",
        "Check the nitrogen line is connected to the machine and its valve is open",
        "Set the regulator to at least 0.5 bar (and at most 3 bar) and check N2 Pressure on Settings, then try again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9009",
      "videoUrl": ""
    },
    {
      "code": 9010,
      "key": "CHAMBER_SENSOR_DISCONNECTED",
      "message": "Chamber Temperature Sensor Disconnected",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The chamber temperature sensor (NTC TEMP_CHAMBER) has read open-circuit for at least 60 seconds - the input sits at the 3.3 V pull-up rail, so there is no temperature. It is a required sensor and the heater's own sensor: no process can start while it is open, the heater is never switched on without it, and a heater that is already running is switched off at once - in that case the alert is raised immediately, not after the minute. The check runs at start-up, every second while running, and again right before every process start.",
      "troubleshooting": [
        "Check the chamber thermistor (TEMP_CHAMBER) cable and its connector on the IO board",
        "Check the common ground of the thermistor harness - when it opens, every sensor jumps to 3.3 V together",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The alert clears by itself once the sensor reads again; then start the process again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9010",
      "videoUrl": ""
    },
    {
      "code": 9011,
      "key": "LEFT_LED_SENSOR_DISCONNECTED",
      "message": "Left LED Temperature Sensor Disconnected",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The Left LED panel temperature sensor (NTC TEMP_LEFT, the Left LED panel thermistor) has read open-circuit for at least 60 seconds - the input sits at the 3.3 V pull-up rail, so there is no temperature. It is a required sensor: no process can start while it is open, because the Left panel's temperature could not be watched. The check runs at start-up, every second while running, and again right before every process start.",
      "troubleshooting": [
        "Check the Left LED panel thermistor (TEMP_LEFT) cable and its connector on the IO board",
        "Check the common ground of the thermistor harness - when it opens, every sensor jumps to 3.3 V together",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The alert clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9011",
      "videoUrl": ""
    },
    {
      "code": 9012,
      "key": "RIGHT_LED_SENSOR_DISCONNECTED",
      "message": "Right LED Temperature Sensor Disconnected",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The Right LED panel temperature sensor (NTC TEMP_RIGHT, the Right LED panel thermistor) has read open-circuit for at least 60 seconds - the input sits at the 3.3 V pull-up rail, so there is no temperature. It is a required sensor: no process can start while it is open, because the Right panel's temperature could not be watched. The check runs at start-up, every second while running, and again right before every process start.",
      "troubleshooting": [
        "Check the Right LED panel thermistor (TEMP_RIGHT) cable and its connector on the IO board",
        "Check the common ground of the thermistor harness - when it opens, every sensor jumps to 3.3 V together",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The alert clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9012",
      "videoUrl": ""
    },
    {
      "code": 9013,
      "key": "BACK_LED_SENSOR_DISCONNECTED",
      "message": "Back LED Temperature Sensor Disconnected",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The Back LED panel temperature sensor (NTC TEMP_BACK) has read open-circuit for at least 60 seconds (input at the 3.3 V pull-up rail). This sensor is diagnostic only: processes keep running as usual, but the Back LED temperature is not shown until it is reconnected.",
      "troubleshooting": [
        "Check the Back LED panel thermistor (TEMP_BACK) cable and its connector on the IO board",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The warning clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9013",
      "videoUrl": ""
    },
    {
      "code": 9014,
      "key": "DOOR_LED_SENSOR_DISCONNECTED",
      "message": "Door LED Temperature Sensor Disconnected",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The Door LED panel temperature sensor (NTC TEMP_DOOR) has read open-circuit for at least 60 seconds (input at the 3.3 V pull-up rail). This sensor is diagnostic only: processes keep running as usual, but the Door LED temperature is not shown until it is reconnected.",
      "troubleshooting": [
        "Check the Door LED panel thermistor (TEMP_DOOR) cable and its connector on the IO board",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The warning clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9014",
      "videoUrl": ""
    },
    {
      "code": 9015,
      "key": "N2_FLOW_BLOCKED",
      "message": "Nitrogen Not Flowing Into the Chamber - Nitrogen Closed",
      "severity": "critical",
      "category": "process",
      "layer": "daemon",
      "description": "When the nitrogen valve opens the gas flows into the chamber and the line pressure must drop. The reading taken with the valve closed just before it opened is the baseline; if the line pressure has not fallen by at least components.json pressure_sensor.flow_check_min_drop_bar (0.3 bar by default) within flow_check_window_sec (5 s by default) after the valve opened, nitrogen is not reaching the chamber - the valve is stuck closed, its coil is not driven, or the tube to the chamber is kinked or blocked. The valve is closed at once and the alert names the pressure, e.g. 'Nitrogen is not flowing into the chamber - the line pressure stayed at 2.0 bar after the valve opened. Check the nitrogen valve and the tube to the chamber.' A running program fails with this code (the chamber is not inert, so the cure does not continue). No check is made when there is no real pressure value before or after opening (sensor error, switch mode, saturated input), when the valve was closed again before the window ended, or when it reopens within 3 s of closing (the line has not built up again). The check can be switched off with flow_check_enabled. The alert clears at the next opening of the valve, which judges the flow afresh.",
      "troubleshooting": [
        "Check the nitrogen valve opens: listen for the click and check its cable and connector on the IO board",
        "Check the tube from the valve to the chamber is not kinked, pinched or blocked",
        "Open nitrogen again (start the program again) - the alert clears and the line pressure must drop within 5 seconds"
      ],
      "supportUrl": "https://docs.scure.com/errors/9015",
      "videoUrl": ""
    },
    {
      "code": 9016,
      "key": "N2_SENSOR_NOT_READING",
      "message": "Nitrogen Pressure Sensor Not Reading",
      "severity": "warning",
      "category": "hardware",
      "layer": "daemon",
      "description": "The nitrogen line-pressure sensor gives no valid reading: the reading fails (an ADC / bus error that lasts past the sensor glitch hold), the analog input is saturated, or the sensor's analog output is outside its range (below 90 % of its 1 V / 4 mA start or above 110 % of its 5 V / 20 mA end - an unplugged 1-5 V sensor reads about 0 V). The alert 'N2 pressure sensor not reading - check that the nitrogen pressure sensor is connected.' is raised once there has been no valid reading for components.json pressure_sensor.not_reading_after_sec (20 s by default), and the boot self-test (N2 Pressure Sensor) gives the sensor up to 20 s to read before it fails with the same text. Without a pressure reading the nitrogen protections (9008 over-pressure, 9009 no supply, 9015 flow blocked) cannot work, so opening nitrogen is refused with this code while the alert is active; a valve that is already open is not closed (a reading can glitch mid-purge) - only the alert is raised. A switch-mode sensor has no pressure value by design and is never flagged. The alert clears by itself as soon as the sensor reads again. A machine without the sensor fitted sets pressure_sensor.required to false.",
      "troubleshooting": [
        "Check that the nitrogen pressure sensor is connected: its cable and the Analog_IN connector on the IO board",
        "Check the sensor is powered and its output lead (1-5 V) goes to Analog_IN; a saturated input above about 0.5 MPa needs the 2:1 divider on Analog_IN (pressure_sensor.divider 2.0)",
        "The alert clears by itself once the sensor reads again; then start nitrogen again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9016",
      "videoUrl": ""
    },
    {
      "code": 9017,
      "key": "WATCHDOG_TRIPPED",
      "message": "Firmware Stopped Responding - Watchdog Switched Heater and UV Off",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The machine firmware stopped responding (its heartbeat went silent for 20 s) and the separate output watchdog (scurebox-watchdog.service) switched the heater SSR and the UV LEDs off by itself, then kept them off (re-cut every 5 s). The watchdog records the cut next to the heartbeat (/run/scurebox-heartbeat.trip); when the firmware responds again it reads that record, comes back in a safe state - heater and UV off, a running program ended as failed with this code, nothing resumes by itself - and raises 'Firmware stopped responding - the output watchdog switched the heater and UV off. Restart the process to continue.' The alert stays until the operator acknowledges it (dismiss on the Alerts screen, or POST /api/watchdog/ack). DVT-SAF-010 provokes it on purpose with POST /api/dvt/hang.",
      "troubleshooting": [
        "Acknowledge the alert, check the part and the chamber, then start the process again - nothing restarts by itself",
        "If it happens outside a DVT test, export the logs (Settings > Export Logs) and send them to service: the firmware hung",
        "If the alert says the cut was INCOMPLETE, switch the machine off at the mains and call service"
      ],
      "supportUrl": "https://docs.scure.com/errors/9017",
      "videoUrl": ""
    },
    {
      "code": 9020,
      "key": "HEATER_FAN_FAILURE",
      "message": "Heater Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The heater fan (FAN_HEATER) has been running at least 11.8 % under its nominal speed (the heater fan has its own stop threshold, fan_health.critical_below_pct_by_fan) for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the heater fan (FAN_HEATER) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9020",
      "videoUrl": ""
    },
    {
      "code": 9021,
      "key": "COOLING_FAN_FAILURE",
      "message": "Cooling Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The chamber cooling fan (FAN_COOLING) has been running at least 20 % under its nominal speed for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the chamber cooling fan (FAN_COOLING) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9021",
      "videoUrl": ""
    },
    {
      "code": 9022,
      "key": "LEFT_LED_FAN_FAILURE",
      "message": "Left LED Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The left led fan (FAN_LEFT) has been running at least 20 % under its nominal speed for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the left led fan (FAN_LEFT) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9022",
      "videoUrl": ""
    },
    {
      "code": 9023,
      "key": "RIGHT_LED_FAN_FAILURE",
      "message": "Right LED Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The right led fan (FAN_RIGHT) has been running at least 20 % under its nominal speed for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the right led fan (FAN_RIGHT) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9023",
      "videoUrl": ""
    },
    {
      "code": 9024,
      "key": "BACK_LED_FAN_FAILURE",
      "message": "Back LED Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The back led fan (FAN_BACK) has been running at least 20 % under its nominal speed for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the back led fan (FAN_BACK) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9024",
      "videoUrl": ""
    },
    {
      "code": 9025,
      "key": "DOOR_LED_FAN_FAILURE",
      "message": "Door LED Fan Below Minimum Speed - System Stopped",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The door led fan (FAN_DOOR) has been running at least 20 % under its nominal speed for a full minute, measured by its tachometer against the nominal RPM table for the commanded duty; a fan that is not turning at all (disconnected, seized) trips within 5 seconds. Every output was switched off and no process can start until the fan is fixed. The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Check the door led fan (FAN_DOOR) connector and that its blades turn freely",
        "Replace the fan; the alert clears by itself once it runs at nominal speed for a minute",
        "Do not run a cure until the alert has cleared"
      ],
      "supportUrl": "https://docs.scure.com/errors/9025",
      "videoUrl": ""
    },
    {
      "code": 9030,
      "key": "LEFT_LED_FAN_NOT_SPINNING",
      "message": "Left LED Fan Not Spinning - Job Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Before the UV LEDs are switched on, every LED cooling fan is spun up and its tachometer is read. The Left LED fan (FAN_LEFT) did not turn (disconnected, blocked or dead), so the LEDs were not switched on and the job did not start.",
      "troubleshooting": [
        "Check the Left LED fan (FAN_LEFT) connector on the LED module and that its blades turn freely",
        "Run the LED fan test in Settings - every one of the four fans is reported",
        "Replace the fan; the job can start as soon as all four LED fans spin"
      ],
      "supportUrl": "https://docs.scure.com/errors/9030",
      "videoUrl": ""
    },
    {
      "code": 9031,
      "key": "RIGHT_LED_FAN_NOT_SPINNING",
      "message": "Right LED Fan Not Spinning - Job Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Before the UV LEDs are switched on, every LED cooling fan is spun up and its tachometer is read. The Right LED fan (FAN_RIGHT) did not turn (disconnected, blocked or dead), so the LEDs were not switched on and the job did not start.",
      "troubleshooting": [
        "Check the Right LED fan (FAN_RIGHT) connector on the LED module and that its blades turn freely",
        "Run the LED fan test in Settings - every one of the four fans is reported",
        "Replace the fan; the job can start as soon as all four LED fans spin"
      ],
      "supportUrl": "https://docs.scure.com/errors/9031",
      "videoUrl": ""
    },
    {
      "code": 9032,
      "key": "BACK_LED_FAN_NOT_SPINNING",
      "message": "Back LED Fan Not Spinning - Job Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Before the UV LEDs are switched on, every LED cooling fan is spun up and its tachometer is read. The Back LED fan (FAN_BACK) did not turn (disconnected, blocked or dead), so the LEDs were not switched on and the job did not start.",
      "troubleshooting": [
        "Check the Back LED fan (FAN_BACK) connector on the LED module and that its blades turn freely",
        "Run the LED fan test in Settings - every one of the four fans is reported",
        "Replace the fan; the job can start as soon as all four LED fans spin"
      ],
      "supportUrl": "https://docs.scure.com/errors/9032",
      "videoUrl": ""
    },
    {
      "code": 9033,
      "key": "DOOR_LED_FAN_NOT_SPINNING",
      "message": "Door LED Fan Not Spinning - Job Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Before the UV LEDs are switched on, every LED cooling fan is spun up and its tachometer is read. The Door LED fan (FAN_DOOR) did not turn (disconnected, blocked or dead), so the LEDs were not switched on and the job did not start.",
      "troubleshooting": [
        "Check the Door LED fan (FAN_DOOR) connector on the LED module and that its blades turn freely",
        "Run the LED fan test in Settings - every one of the four fans is reported",
        "Replace the fan; the job can start as soon as all four LED fans spin"
      ],
      "supportUrl": "https://docs.scure.com/errors/9033",
      "videoUrl": ""
    },
    {
      "code": 9034,
      "key": "COOLING_FAN_NOT_SPINNING",
      "message": "Chamber Cooling Fan Not Spinning - Step Not Started",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "Before a drying or cooling step starts - the steps that use it - the chamber cooling fan (FAN_COOLING) is spun up and its tachometer is read. It did not turn (disconnected, blocked or dead), so the step did not start (DVT-SAF-006). Heating and UV steps do not test this fan.",
      "troubleshooting": [
        "Check the chamber cooling fan (FAN_COOLING) connector and that its blades turn freely",
        "Run the chamber intake fan test in Settings",
        "Replace the fan; the step can start as soon as it spins"
      ],
      "supportUrl": "https://docs.scure.com/errors/9034",
      "videoUrl": ""
    },
    {
      "code": 9040,
      "key": "LEFT_LED_PANEL_NOT_HEATING",
      "message": "Left LED Panel Not Heating - Check LED Connection",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The lit Left LED panel has not warmed its thermistor: after 90 seconds of light at 30 % system power or more, its temperature (regular Left thermistor) has risen by less than 1.0 C above its temperature when the light started (a working panel rises by about 1.7 C in that time, LED fans on). The panel is therefore not receiving current - its power connector or driver output is open - and it is not curing. The process keeps running; the panel is re-checked on every UV step and the alert clears by itself as soon as it heats again.",
      "troubleshooting": [
        "Check that the Left LED panel power connector is plugged in and locked (LED_OUT connector on the driver side and the panel side)",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay)",
        "Run Diagnostics > LED test and watch the Left temperature: it must rise within 90 s of light at 30 %",
        "The alert clears by itself once the panel warms by at least 1 C during a UV step"
      ],
      "supportUrl": "https://docs.scure.com/errors/9040",
      "videoUrl": ""
    },
    {
      "code": 9041,
      "key": "RIGHT_LED_PANEL_NOT_HEATING",
      "message": "Right LED Panel Not Heating - Check LED Connection",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The lit Right LED panel has not warmed its thermistor: after 90 seconds of light at 30 % system power or more, its temperature (regular Right thermistor) has risen by less than 1.0 C above its temperature when the light started (a working panel rises by about 1.7 C in that time, LED fans on). The panel is therefore not receiving current - its power connector or driver output is open - and it is not curing. The process keeps running; the panel is re-checked on every UV step and the alert clears by itself as soon as it heats again.",
      "troubleshooting": [
        "Check that the Right LED panel power connector is plugged in and locked (LED_OUT connector on the driver side and the panel side)",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay)",
        "Run Diagnostics > LED test and watch the Right temperature: it must rise within 90 s of light at 30 %",
        "The alert clears by itself once the panel warms by at least 1 C during a UV step"
      ],
      "supportUrl": "https://docs.scure.com/errors/9041",
      "videoUrl": ""
    },
    {
      "code": 9042,
      "key": "LEFT_LED_PANEL_TEMP_DROP",
      "message": "Left LED Panel Temperature Dropped During Cure",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The Left LED panel had warmed up normally but cooled down while its light was still commanded on: its thermistor fell by 1.0 C or more below the peak it had reached at this power level (any fall of the chamber temperature over the same time is taken off first) and stayed there for 30 seconds. The panel stopped receiving current mid-process - a loose connector, a dropped driver output - so it is no longer curing. The process keeps running; the alert clears by itself once the panel climbs back to within 0.5 C of its peak while lit.",
      "troubleshooting": [
        "Check that the Left LED panel power connector is seated and locked - a connector that works loose under vibration or heat causes exactly this",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay) and its wiring",
        "Watch the Left temperature on Diagnostics > LED test: a healthy panel holds or climbs while lit",
        "Run the cure again once the connection is fixed - the alert clears when the panel heats normally"
      ],
      "supportUrl": "https://docs.scure.com/errors/9042",
      "videoUrl": ""
    },
    {
      "code": 9043,
      "key": "RIGHT_LED_PANEL_TEMP_DROP",
      "message": "Right LED Panel Temperature Dropped During Cure",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "The Right LED panel had warmed up normally but cooled down while its light was still commanded on: its thermistor fell by 1.0 C or more below the peak it had reached at this power level (any fall of the chamber temperature over the same time is taken off first) and stayed there for 30 seconds. The panel stopped receiving current mid-process - a loose connector, a dropped driver output - so it is no longer curing. The process keeps running; the alert clears by itself once the panel climbs back to within 0.5 C of its peak while lit.",
      "troubleshooting": [
        "Check that the Right LED panel power connector is seated and locked - a connector that works loose under vibration or heat causes exactly this",
        "Check the driver output / SSR for that panel (405 nm: GPIO20 SSR + LED_SWITCH relay) and its wiring",
        "Watch the Right temperature on Diagnostics > LED test: a healthy panel holds or climbs while lit",
        "Run the cure again once the connection is fixed - the alert clears when the panel heats normally"
      ],
      "supportUrl": "https://docs.scure.com/errors/9043",
      "videoUrl": ""
    },
    {
      "code": 9044,
      "key": "BACK_LED_PANEL_NOT_HEATING",
      "message": "Back LED Panel Not Heating - Check LED Connection",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "During a UV step the lit Back LED panel did not warm its thermistor by the required rise (checked on the Cure screen: max(0.35, 0.8 x intensity/100 x window/15) C over the check window). The panel is therefore not receiving current - its power connector or driver output is open - and it is not curing. The operator is asked whether to continue without it.",
      "troubleshooting": [
        "Check that the Back LED panel power connector is plugged in and locked",
        "Check the driver output / SSR for that panel and its wiring",
        "Run Diagnostics > LED test and watch the Back temperature: it must rise while lit",
        "Run the cure again once the connection is fixed"
      ],
      "supportUrl": "https://docs.scure.com/errors/9044",
      "videoUrl": ""
    },
    {
      "code": 9045,
      "key": "DOOR_LED_PANEL_NOT_HEATING",
      "message": "Door LED Panel Not Heating - Check LED Connection",
      "severity": "critical",
      "category": "safety",
      "layer": "daemon",
      "description": "During a UV step the lit Door LED panel did not warm its thermistor by the required rise (checked on the Cure screen: max(0.35, 0.8 x intensity/100 x window/15) C over the check window). The panel is therefore not receiving current - its power connector or driver output is open - and it is not curing. The operator is asked whether to continue without it.",
      "troubleshooting": [
        "Check that the Door LED panel power connector is plugged in and locked",
        "Check the driver output / SSR for that panel and its wiring",
        "Run Diagnostics > LED test and watch the Door temperature: it must rise while lit",
        "Run the cure again once the connection is fixed"
      ],
      "supportUrl": "https://docs.scure.com/errors/9045",
      "videoUrl": ""
    },
    {
      "code": 9046,
      "key": "LEFT_UV_LIGHT_NOT_DETECTED",
      "message": "Left UV Light Not Detected",
      "severity": "warning",
      "category": "safety",
      "layer": "daemon",
      "description": "The Left UV LED panel has been lit for the confirm time (uv_light_check.confirm_sec, 5 s, at uv_light_check.min_intensity % system power or more) but its UV light sensor - the photoresistor UV_LEFT on the panel - still reads dark: its voltage did not fall to uv_light_check.lit_ratio (0.6) of its dark reading taken while the panel was off. The panel may not be emitting light, or the light sensor is not connected. This is a warning only: the process keeps running. The alert names the panel, the measured volts and the dark baseline, and clears by itself when light is seen or the panel goes off. The photoresistor thresholds are NOT yet calibrated on the unit; they are set in components.json uv_light_check.",
      "troubleshooting": [
        "Check that the Left UV panel is really lit (look through the window with UV-safe glasses, or run Diagnostics > LED test)",
        "Check the Left UV light sensor (photoresistor UV_LEFT) connector J25.9 on the IO board",
        "Check the Left LED panel power connector and its driver output",
        "If the panel is lit and the sensor connected, the thresholds in components.json uv_light_check may need calibrating"
      ],
      "supportUrl": "https://docs.scure.com/errors/9046",
      "videoUrl": ""
    },
    {
      "code": 9047,
      "key": "RIGHT_UV_LIGHT_NOT_DETECTED",
      "message": "Right UV Light Not Detected",
      "severity": "warning",
      "category": "safety",
      "layer": "daemon",
      "description": "The Right UV LED panel has been lit for the confirm time (uv_light_check.confirm_sec, 5 s, at uv_light_check.min_intensity % system power or more) but its UV light sensor - the photoresistor UV_RIGHT on the panel - still reads dark: its voltage did not fall to uv_light_check.lit_ratio (0.6) of its dark reading taken while the panel was off. The panel may not be emitting light, or the light sensor is not connected. This is a warning only: the process keeps running. The alert names the panel, the measured volts and the dark baseline, and clears by itself when light is seen or the panel goes off. The photoresistor thresholds are NOT yet calibrated on the unit; they are set in components.json uv_light_check.",
      "troubleshooting": [
        "Check that the Right UV panel is really lit (look through the window with UV-safe glasses, or run Diagnostics > LED test)",
        "Check the Right UV light sensor (photoresistor UV_RIGHT) connector J25.1 on the IO board",
        "Check the Right LED panel power connector and its driver output",
        "If the panel is lit and the sensor connected, the thresholds in components.json uv_light_check may need calibrating"
      ],
      "supportUrl": "https://docs.scure.com/errors/9047",
      "videoUrl": ""
    },
    {
      "code": 9048,
      "key": "BOFA_NOT_DETECTED",
      "message": "BOFA Unit Not Detected",
      "severity": "warning",
      "category": "hardware",
      "layer": "daemon",
      "description": "Settings says a BOFA fume extractor is connected, but the BOFA connector (J16) reports that nothing is plugged into it: the presence line 4DA_BOFA_PRESENT (GPIO18) does not read the level a connected unit pulls it to. The machine still drives the extraction output whenever the air-intake fan runs, but the chamber gases are probably not being extracted. This is a warning only: nothing is stopped. It clears by itself when the connector reads a unit again, or when the switch in Settings is turned off. The polarity of the presence line is NOT yet measured on a unit - components.json bofa.present_active_low.",
      "troubleshooting": [
        "Check that the extraction fan's cable is plugged into J16 on the IO board and seated fully",
        "Check the cable itself: pin 3 of the 4-pin connector is the presence line, pin 2 is GND",
        "If no BOFA unit is fitted on this machine, turn 'BOFA Connected' off in Settings",
        "Read /api/state bofaDetected with the cable in and out: if it is the wrong way round, flip components.json bofa.present_active_low"
      ],
      "supportUrl": "https://docs.scure.com/errors/9048",
      "videoUrl": ""
    },
    {
      "code": 9050,
      "key": "LED_TEMP_SENSOR_DISCONNECTED",
      "message": "LED Temperature Sensor Disconnected",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9013 (back), 9014 (door), one code per component. Kept so older reports and logs still show a title. An LED panel temperature sensor has read open-circuit for at least 60 seconds (input at the 3.3 V pull-up rail). The line above names the panel. These sensors are diagnostic only: processes keep running as usual, but the LED temperature of that module is not shown until it is reconnected.",
      "troubleshooting": [
        "Check the thermistor cable and IO-board connector of the panel named above",
        "Measure the thermistor: about 12 kOhm at room temperature",
        "The warning clears by itself once the sensor reads again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9050",
      "videoUrl": ""
    },
    {
      "code": 9051,
      "key": "FAN_WEAR_WARNING",
      "message": "Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "Grouped code - no longer raised since firmware 1.0.106: replaced by 9060-9065 (one per fan), one code per component. Kept so older reports and logs still show a title. A fan has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it drops 20 % below nominal (then the system stops, Err 9002). The line above names every fan below nominal, with its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the fan named in the line above",
        "Check for dust on the blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9051",
      "videoUrl": ""
    },
    {
      "code": 9052,
      "key": "NFC_READER_NOT_DETECTED",
      "message": "NFC Reader Not Detected",
      "severity": "warning",
      "category": "io",
      "layer": "backend",
      "description": "NFC cannot be switched on because no NFC reader (Eccel Pepper C2) is connected on USB, or the reader was disconnected while NFC was enabled. The NFC switch in Settings stays off until a reader is detected.",
      "troubleshooting": [
        "Connect the NFC reader to a USB port on the machine",
        "Use a data-capable USB cable (charge-only cables are not detected)",
        "Wait 5 seconds for the reader to be detected, then switch NFC on again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9052",
      "videoUrl": ""
    },
    {
      "code": 9060,
      "key": "HEATER_FAN_WEAR",
      "message": "Heater Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The heater fan (FAN_HEATER) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9020). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the heater fan (FAN_HEATER)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9060",
      "videoUrl": ""
    },
    {
      "code": 9061,
      "key": "COOLING_FAN_WEAR",
      "message": "Cooling Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The chamber cooling fan (FAN_COOLING) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9021). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the chamber cooling fan (FAN_COOLING)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9061",
      "videoUrl": ""
    },
    {
      "code": 9062,
      "key": "LEFT_LED_FAN_WEAR",
      "message": "Left LED Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The left led fan (FAN_LEFT) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9022). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the left led fan (FAN_LEFT)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9062",
      "videoUrl": ""
    },
    {
      "code": 9063,
      "key": "RIGHT_LED_FAN_WEAR",
      "message": "Right LED Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The right led fan (FAN_RIGHT) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9023). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the right led fan (FAN_RIGHT)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9063",
      "videoUrl": ""
    },
    {
      "code": 9064,
      "key": "BACK_LED_FAN_WEAR",
      "message": "Back LED Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The back led fan (FAN_BACK) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9024). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the back led fan (FAN_BACK)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9064",
      "videoUrl": ""
    },
    {
      "code": 9065,
      "key": "DOOR_LED_FAN_WEAR",
      "message": "Door LED Fan Speed Low - Replace Fan",
      "severity": "warning",
      "category": "maintenance",
      "layer": "daemon",
      "description": "The door led fan (FAN_DOOR) has been running at least 10 % below its nominal speed for a full minute. The machine keeps working, but the fan is wearing out and should be replaced before it reaches its stop threshold (then the system stops, Err 9025). The line above gives its measured and expected RPM.",
      "troubleshooting": [
        "Plan a replacement of the door led fan (FAN_DOOR)",
        "Check for dust on its blades and grille",
        "The warning clears by itself once the fan runs at nominal speed again"
      ],
      "supportUrl": "https://docs.scure.com/errors/9065",
      "videoUrl": ""
    },
    {
      "code": 9080,
      "key": "UNKNOWN_DIAGNOSTIC_TOOL",
      "message": "Unknown Network Tool",
      "severity": "warning",
      "category": "validation",
      "layer": "backend",
      "description": "The network diagnostics endpoint was called with an unsupported tool name (expected ping, traceroute or nslookup).",
      "troubleshooting": [
        "Select one of the supported diagnostic tools",
        "Retry the diagnostic from the Network screen"
      ],
      "supportUrl": "https://docs.scure.com/errors/9080",
      "videoUrl": ""
    },
    {
      "code": 9081,
      "key": "USB_NOT_FOUND",
      "message": "No Disk-on-Key Connected",
      "severity": "warning",
      "category": "storage",
      "layer": "backend",
      "description": "An export operation could not find a Disk-on-Key (USB drive) connected to the machine.",
      "troubleshooting": [
        "Connect a Disk-on-Key (USB drive) to the machine",
        "Wait a few seconds for it to mount, then retry",
        "Try a different USB port or Disk-on-Key"
      ],
      "supportUrl": "https://docs.scure.com/errors/9081",
      "videoUrl": ""
    },
    {
      "code": 9082,
      "key": "USB_WRITE_FAILED",
      "message": "Disk-on-Key Write Failed",
      "severity": "warning",
      "category": "storage",
      "layer": "backend",
      "description": "The Disk-on-Key was found but the file could not be written to it (it may be full, read-only, or was removed mid-write).",
      "troubleshooting": [
        "Check that the Disk-on-Key has free space and is not write-protected",
        "Do not remove the Disk-on-Key during export",
        "Reformat the Disk-on-Key (FAT32) and retry"
      ],
      "supportUrl": "https://docs.scure.com/errors/9082",
      "videoUrl": ""
    },
    {
      "code": 9083,
      "key": "LOG_EXPORT_FAILED",
      "message": "Log Export Failed",
      "severity": "warning",
      "category": "storage",
      "layer": "backend",
      "description": "The backend failed to copy the system logs to the USB drive.",
      "troubleshooting": [
        "Insert a writable USB drive and retry",
        "Check available space on the USB drive"
      ],
      "supportUrl": "https://docs.scure.com/errors/9083",
      "videoUrl": ""
    },
    {
      "code": 9084,
      "key": "NETWORK_STATUS_UNAVAILABLE",
      "message": "Network Status Unavailable",
      "severity": "warning",
      "category": "network",
      "layer": "backend",
      "description": "The backend could not read the device network status (IP / MAC / gateway).",
      "troubleshooting": [
        "Check the Ethernet cable and link LEDs",
        "Reboot the system",
        "Verify network settings"
      ],
      "supportUrl": "https://docs.scure.com/errors/9084",
      "videoUrl": ""
    },
    {
      "code": 9085,
      "key": "NETWORK_DIAGNOSTIC_FAILED",
      "message": "Network Diagnostic Failed",
      "severity": "warning",
      "category": "network",
      "layer": "backend",
      "description": "A network diagnostic command (ping / traceroute / nslookup) failed to execute on the device.",
      "troubleshooting": [
        "Verify the target address is reachable",
        "Check the network connection and retry"
      ],
      "supportUrl": "https://docs.scure.com/errors/9085",
      "videoUrl": ""
    },
    {
      "code": 9086,
      "key": "UPDATE_FAILED",
      "message": "Software Update Failed",
      "severity": "critical",
      "category": "update",
      "layer": "backend",
      "description": "The backend update process failed while installing a software package from USB.",
      "troubleshooting": [
        "Re-download the update package and copy it to USB",
        "Verify the package version and integrity",
        "Retry the update from Settings → Update Software"
      ],
      "supportUrl": "https://docs.scure.com/errors/9086",
      "videoUrl": ""
    },
    {
      "code": 9087,
      "key": "UPDATE_PACKAGE_NOT_FOUND",
      "message": "Update Package Not Found",
      "severity": "warning",
      "category": "update",
      "layer": "backend",
      "description": "No update package (or its manifest) could be found on the connected USB drive.",
      "troubleshooting": [
        "Copy the .scu update package and its manifest to the USB root",
        "Insert the USB drive and retry"
      ],
      "supportUrl": "https://docs.scure.com/errors/9087",
      "videoUrl": ""
    },
    {
      "code": 9088,
      "key": "UPDATE_INTEGRITY_FAILED",
      "message": "Update Integrity Check Failed",
      "severity": "critical",
      "category": "security",
      "layer": "ui",
      "description": "The update package failed SHA-256 integrity verification (missing/malformed checksum or a mismatch — a corrupt or tampered-with package). Installation is blocked (EN 18031 secure update).",
      "troubleshooting": [
        "Re-download the update package from the official portal",
        "Verify the checksum/manifest matches the package",
        "Do not install packages from untrusted sources"
      ],
      "supportUrl": "https://docs.scure.com/errors/9088",
      "videoUrl": ""
    },
    {
      "code": 9089,
      "key": "HW_API_UNREACHABLE",
      "message": "Hardware Service Unreachable",
      "severity": "critical",
      "category": "system",
      "layer": "ui",
      "description": "The UI could not reach the local hardware API (Flask backend). Hardware commands cannot be sent.",
      "troubleshooting": [
        "Reboot the system",
        "Verify the sCure service is running",
        "Contact support if the fault persists"
      ],
      "supportUrl": "https://docs.scure.com/errors/9089",
      "videoUrl": ""
    }
  ]
}

```

### config/components.json

```json
{
  "_comment": "CureBox component configuration. Edit THIS FILE ONLY (no source changes) to add LEDs, change fan assignments, fan speeds, default intensity, or wavelength gating. LED and fan names must match the channel names in io_controller (PCA_CHANNELS).",
  "led_power": {
    "ssr_450nm": 16,
    "ssr_405nm": 20,
    "routing": 17,
    "default_mode": "405nm",
    "switch_settle_sec": 0.1,
    "min_intensity": 10,
    "led_max_duty": 60,
    "modes": {
      "450nm": {
        "ssr_450nm": 1,
        "ssr_405nm": 0,
        "routing": 0,
        "led_switch": 0,
        "led_fan_pwm": 30
      },
      "405nm": {
        "ssr_450nm": 1,
        "ssr_405nm": 1,
        "routing": 0,
        "led_switch": 1
      }
    },
    "_comment": "Software-driven LED-driver SSR + wavelength-select GPIOs (OUTPUTS) plus the LED_SWITCH relay: led_switch = TCA6424A P05 -> Q28 -> K4 (selects LED_OUT1/LED_OUT2 at J21), 1 while a Cure / 405nm process runs, 0 for Bleaching / 450nm and whenever the machine is idle, safe or shut down (SystemController._set_led_switch, verified by read-back). Turn-on order on every wavelength change: LED_SWITCH relay first -> wait switch_settle_sec (default 0.1 s, only when the relay actually moved) -> SSR enables + GPIO17 -> DIM PWM. GPIO16 = 450nm SSR, GPIO20 = 405nm SSR, GPIO17 = voltage-routing line. BENCH FINDING 2026-09-07 (testingcm5): GPIO17 HIGH cuts the 12 V rail of the door LED-driver DIM stage in EVERY SSR combination (door DIM measured 0 V), while GPIO17 LOW with only the 450nm SSR on gives the door its full 12 V DIM - so the old assumption HIGH=450nm was inverted and Bleaching never dimmed the door. Both modes therefore keep routing=0; the wavelength is selected by the SSRs alone (450nm: GPIO16 only, 405nm: GPIO16+GPIO20). Do not set routing=1 for 450nm again without re-measuring the door DIM. GPIO17 is still set BEFORE the SSRs and read back to verify before any LED may operate; on a mode change all LEDs turn off first, then GPIO17 changes. (GPIO27 is the door sensor, not here.) Below 'min_intensity' (user-facing brightness %) an LED counts as OFF: its PWM is zeroed, and once no LED remains on the SSRs (GPIO16 + GPIO20) are switched off. 'led_max_duty' is the PWM duty that equals 100% brightness (must match LED_MAX_DUTY in the dashboards); it converts min_intensity into duty for SystemController.set_led."
  },
  "door_sensor": {
    "gpio": 27,
    "open_level": 0,
    "abort_after_sec": 10,
    "_comment": "Door interlock input on GPIO27 (read via pinctrl). 'open_level' is the pin level that means the door is OPEN. Bench-confirmed 2026-07-22: GPIO27 HIGH = door CLOSED, LOW = door OPEN, hence open_level 0. When open: all LEDs + heater are forced OFF and cannot be enabled until the door closes. 'abort_after_sec' (default 10 s) is the grace period of the mid-process door watchdog: if the door STAYS open that long while any output is live, the whole process is aborted (Err 6016) and the status strip turns red; closing the door within the grace lets the process continue."
  },
  "leds": {
    "LED_LEFT": {
      "fan": "FAN_LEFT",
      "fan_speed": 100,
      "intensity": 100,
      "modes": [
        "405nm"
      ]
    },
    "LED_RIGHT": {
      "fan": "FAN_RIGHT",
      "fan_speed": 100,
      "intensity": 100,
      "modes": [
        "405nm"
      ]
    },
    "LED_BACK": {
      "fan": "FAN_BACK",
      "fan_speed": 100,
      "intensity": 100,
      "modes": [
        "405nm"
      ]
    },
    "LED_DOOR": {
      "fan": "FAN_DOOR",
      "fan_speed": 100,
      "intensity": 100,
      "modes": [
        "405nm",
        "450nm"
      ]
    }
  },
  "rgb": {
    "gpio": 12,
    "count": 21,
    "order": "RGB",
    "status": {
      "normal": "green",
      "fault": "red",
      "door_open": "ff7800",
      "busy": "blue",
      "internet_check_sec": 5,
      "busy_style": "solid",
      "busy_direction": "rtl",
      "chase_sec": 0.12,
      "chase_tail": 5,
      "brightness": 100,
      "blink_sec": 0.5,
      "status_sec": 1
    },
    "_comment": "RGB status LEDs (TM1903 driver on GPIO12, WS2811-compatible serial data). 'count' = number of LEDs on the strip (writing more than fitted is harmless), 'order' = color byte order (TM1903 is typically RGB; if red/green come out swapped change back to GRB). Requires: sudo pip3 install adafruit-circuitpython-neopixel. CLI: io_controller.py rgb set <color|RRGGBB> [brightness%] / rgb off. 'status' = automatic machine-status colors driven by the server (io_bridge): solid 'normal' color while everything is OK, BLINKING 'fault' color when any fault is active (highest priority), BLINKING 'door_open' color while the door is open, and while a process runs (heating/cooling/UV) every LED shows the 'busy' color solid (busy = blue, busy_style = solid since 2026-09-16; every color here is re-read LIVE about once a second, so edits apply without a service restart) (busy_style 'comet' instead MOVES the busy color as a comet: 'busy_direction' rtl/ltr, one LED step every 'chase_sec' seconds, tail length 'chase_tail'). Colors are names or RRGGBB hex; 'blink_sec' is the blink half-period; change values here only - no code change needed. 'status_sec' (default 1 s - the HSI sampling-time rule: every reading is sampled at most every 1 s) is how often the machine state is (re)classified - the same watchdog also enforces the door safety: the door opening while ANY output is live aborts the process and forces every output off (heater, UV, cooling, fans, N2, BOFA, damper). The strip has no internet marking (since 1.0.153): while idle it shows 'normal', while a process runs 'busy', whatever the internet state ('internet_check_sec' only paces the background reachability check behind /api/state internetOk). Faults and door-open always take priority."
  },
  "fan_health": {
    "warn_below_pct": 10,
    "critical_below_pct": 20,
    "persist_sec": 60,
    "settle_sec": 5,
    "min_eval_duty": 30,
    "nominal_rpm": {
      "FAN_HEATER": {
        "100": 5925,
        "80": 5227,
        "50": 3669,
        "30": 2363
      },
      "FAN_COOLING": {
        "100": 4790,
        "60": 2690,
        "30": 1235
      },
      "FAN_LEFT": {
        "100": 3560,
        "30": 1135
      },
      "FAN_RIGHT": {
        "100": 3560,
        "30": 1135
      },
      "FAN_BACK": {
        "100": 3560,
        "30": 1135
      },
      "FAN_DOOR": {
        "100": 3560,
        "30": 1135
      }
    },
    "critical_below_pct_by_fan": {
      "FAN_HEATER": 11.8
    },
    "nominal_rpm_damper_open": {
      "FAN_COOLING": {
        "100": 4075,
        "60": 2470
      }
    },
    "_comment": "1.0.68 (user, 2026-10-08): FAN_HEATER nominal re-measured after the heater fan / airflow fix (100 % 5,925 / 80 % 5,227 / 50 % 3,669 / 30 % 2,363 RPM, was 3,530 / 2,925 / 1,870 / 915); critical_below_pct_by_fan: the heater fan stops the machine (9002) at 11.8 % below nominal - the user's limit of 5,227 RPM at 100 % (its 80 %-duty speed); 9051 still warns at 10 % (5,333 RPM). Every other fan keeps critical_below_pct. nominal_rpm_damper_open (sCureBox 1.0.66): used instead of nominal_rpm for the fans listed while the damper is OPEN (cooling / drying) - the open duct slows FAN_COOLING ~14 % (unit 2026-10-01: 60 % ~2,470 / 100 % ~4,075 RPM open vs 2,690 / 4,735 closed), which alone raised the 10 % wear warning 9051 in every fast cooling. Below 60 % the expected RPM is scaled proportionally from the 60 % point. Fan wear supervision (policy 2026-09-09). Every fan with a tachometer is compared, while it is commanded at >= min_eval_duty %, against the nominal RPM measured on the reference machine (testingcm5, 2026-09-09; per duty point, linear interpolation in between). A fan that stays >= warn_below_pct below nominal for persist_sec (one full minute, to ride out tach noise) raises warning 9051 'replace the fan'; >= critical_below_pct below for persist_sec raises critical 9002: every output is stopped, no process may start, and the alert names the exact fan (e.g. FAN_COOLING) with its measured and expected RPM. settle_sec ignores the spin-up after a duty change. Re-read live about once a second - edit here, no restart. LED fans: Right/Back/Door share the Left fan's nominal until measured individually. 1.0.89 (user, 2026-10-14): the LED cooling fans run at 30 % in 450 nm (led_power.modes.450nm.led_fan_pwm); 30 % point measured on the unit 2026-10-14 - all four LED fans 1,113-1,145 RPM, nominal 1,135 (the proportional 1,068 would have under-read)."
  },
  "led_heating": {
    "enabled": false,
    "min_eval_intensity": 30,
    "check_after_sec": 90,
    "min_rise_c": 1.0,
    "rest_sec": 120,
    "panels": {
      "LED_LEFT": "TEMP_LEFT",
      "LED_RIGHT": "TEMP_RIGHT"
    },
    "drop_c": 1.0,
    "drop_persist_sec": 30,
    "drop_settle_sec": 120,
    "_comment": "'enabled' (default false, decision 2026-09-16): at this stage NO LED checks run during a process - no 9004 / 9005 from the server and no LED-panel-not-heating check in the UI; set true to turn them on again (re-read live). LED connection supervision (policy 2026-09-14). 'panels' maps each supervised LED to the thermistor that must warm while it is lit - the REGULAR Left / Right thermistors (TEMP_LEFT = U6 ch3, TEMP_RIGHT = U6 ch1), not the ORIGIN ones, so only the Left and Right panels are checked. Back / Door only carry an ORIGIN thermistor, and the ORIGIN thermistors have a different role in the system - they must NOT be used for this check (user, 2026-10-25). DVT runtime override (DVT-SAF-016): POST /api/dvt/led-checks?on=1 switches these checks on in memory for the panels listed here, until on=0 or a restart; this file is not changed. While a panel is commanded on at >= min_eval_intensity % system power, its temperature is compared with its temperature when the light started (baseline); after check_after_sec of accumulated light the rise must be >= min_rise_c C, otherwise the panel is not receiving current (open connector / driver output) -> Err 9004 critical 'check the LED connection', the alert names the panel. A panel re-lit within rest_sec of its last light keeps the previous baseline (it is still warm). Bench on testingcm5 2026-09-14 at 30 % 405 nm with the LED fans at 100 %: TEMP_LEFT / TEMP_RIGHT rose +1.3 / +1.2 C after 60 s, +1.8 / +1.7 C after 90 s, +2.4 / +2.2 C after 150 s (DVT/bench/data/led_panel_warmup_30pct_405nm_2026-09-14.csv) - 90 s / 1.0 C gives a 1.7x margin. Re-read live about once a second - edit here, no restart. Mid-process drop (Err 9005): once a panel has proved it heats, its peak temperature at the current power level is tracked; a fall of >= drop_c C below that peak - after taking off any fall of the chamber temperature over the same time - that lasts drop_persist_sec s while the panel is still lit means the panel stopped receiving current mid-process -> Err 9005 critical 'panel fault', the alert names the panel. A power-level change waits drop_settle_sec s before the peak is tracked again; a re-light re-judges the panel (rise rule again, peak restarts from the re-light temperature); the latch clears when the panel climbs back to within drop_c/2 of its peak while lit."
  },
  "uv_light_check": {
    "enabled": true,
    "min_intensity": 10,
    "confirm_sec": 5,
    "lit_ratio": 0.6,
    "_comment": "UV-on confirmation (user, 2026-11-01, Err 9046 / 9047 warning). The Left / Right UV panels each carry a photoresistor (UV_LEFT = U6 AIN2, UV_RIGHT = U6 AIN0, connector J25.9 / J25.1) on the 10 kOhm pull-up divider - not a thermistor: about 2.8 V (~55 kOhm) dark on the unit with the LEDs off. While a panel is off its reading is the dark baseline; once it has been lit at >= min_intensity % for confirm_sec s its reading must be <= baseline * lit_ratio, else a warning naming the panel, the volts and the baseline. It clears when light is seen or the panel goes off; nothing is stopped. These thresholds are NOT yet calibrated on a unit. Re-read live."
  },
  "bofa": {
    "max_duty": 60,
    "enable_gpio": 6,
    "present_gpio": 18,
    "present_active_low": true,
    "_comment": "BOFA extraction fan (PCA9685 channel 10 -> 4DA_BOFA_PWM). The channel is NOT a fan drive: the PWM is averaged by two RC stages and amplified x3.3 by U18B (OPA2990, 12 V rail) into 4DA_ANALOG, the fan's 0-10 V speed input on J16.4 (BRD-74205 REV_A). The PCA outputs swing to its own 5 V supply, so 'max_duty' is the channel duty that makes 10 V: 60 % x 5 V x 3.3 = 10 V, the same clamp the identical LED dimming channels use (led_power.led_max_duty). bofaDutyPercent is scaled by this, so 100 % asks for 10 V and never clips against the 12 V rail. 'enable_gpio' (4DA_BOFA_EN, J24 pin 31) opens the fan's own 24 V through a high-side MOSFET - without it the connector is dead, whatever the speed says; it is driven only while extraction runs. 'present_gpio' (4DA_BOFA_PRESENT, J24 pin 12) reads whether a unit is plugged into J16: with 'present_active_low' true a connected unit pulls the line LOW. Settings keeps the manual switch, and a switch that says connected while this line says empty raises warning 9048. NONE of this is measured on a unit yet: check /api/state bofaDetected with the cable in and out and flip present_active_low if it reads the wrong way round."
  },
  "frozen_reading": {
    "enabled": true,
    "window_sec": 90,
    "min_delta_c": 0.01,
    "min_duty_pct": 50,
    "reboot_after_sec": 60,
    "_comment": "Plausible-but-frozen heater reading (DVT-SAF-003, Err 9006). min_delta_c 0.01 C (user 2026-10-11, was 0.1: a chamber held steady at 80 C tripped 9006 at 82 % output). reboot_after_sec (user 2026-10-01): a frozen reading is also what a stuck reader thread looks like, so the machine restarts itself this long after the alert (0 = never); the latch is kept in data/frozen_reading.json and read back at boot, so heating stays refused after the restart until the reading moves. A fixed resistor in place of the chamber NTC, a stuck ADC or a stuck reader thread all give a steady in-range temperature that no range check catches, and the PI loop drives the heater to full output for as long as heating is allowed (2026-10-01 on the test unit: reading 40.9 C flat, PWM 100 %, heater body past 180 C, no alarm). Rule in the user's words: while heating with the heater at >= min_duty_pct % output for window_sec s continuously, the TEMP_CHAMBER reading must move by at least min_delta_c C, otherwise -> Err 9006 critical, the heater is switched off at once, every HEAT command is refused, the alert names the reading and the number it is stuck at. A drop of the output below min_duty_pct (the PI loop near its target) restarts the window, so a chamber holding its setpoint is never judged. The latch clears by itself once the reading moves by >= 1 C (a real sensor put back) or goes open (9001 takes over). Re-read live."
  },
  "no_heat": {
    "enabled": true,
    "window_sec": 600,
    "min_rise_c": 0.5,
    "min_duty_pct": 99,
    "_comment": "Heater not heating (DVT-SAF-017, Err 9007, user 2026-10-01): the heater drives at >= min_duty_pct % output for window_sec s and the chamber rose less than min_rise_c C -> the heater is getting no power: the 110 / 230 V voltage selector is not in its position, or the heater fuse has blown. The heater is switched off and the alert says to check both. Measured 2026-10-01 with the selector in the middle: PWM 100 % for 2.5 min, chamber 35.0 -> 32.1 C, no alarm before this rule; normal heating at full output raises the chamber about 8 C in 2 min. The latch clears when the heater is driven again (a new heating start). 2026-10-08 (user): window 120 -> 300 s - on the unit the displayed chamber (rate-compensated calibration) dipped ~2.5 C while the raw reading kept rising, and the 2-minute window tripped 9007 on a heater that was heating (runs WeatherX, h, 80deg) [reverted in 1.0.67]. Same day: min_duty_pct 50 -> 99 - judged only at full output (the PI saturated far below the target); a hold near the setpoint (integrator capped at 85 %) is never judged, also at 80 C where it could sit above 50 % for minutes [reverted in 1.0.67]. 1.0.67 (user, 2026-10-08): back to 120 s / 50 % - the TC-08 on the heater body showed the trips were real: the heater body reached ~267 C and its self-resetting thermal cutout opened (closing again at ~198 C) while the controller drove 100 %, so the heater really was not heating. 1.0.74 (user, 2026-10-10): min_duty_pct 50 -> 99 - judged only while the controller drives full output (PI saturated); window 120 s and 0.5 C rise from the window minimum unchanged. 1.0.87 (user, 2026-10-12): window_sec 120 -> 600 - on 2026-10-11 the two-minute window raised 9007 three times on a working heater (57.0 -> 57.0 C at a heating start, 76.3 -> 76.6 C and 75.3 -> 75.3 C near the 80 C target, the last one stopping a program after 3232 s) while the TC-08 on the heater body read ~215 C: at full output the chamber climbs ~0.2-0.6 C/min there. A heater with no supply still trips, after ten minutes instead of two. 1.0.152 (user, 2026-11-04): judged on the ramp up only - once the chamber is within heating.at_temp_band of its target the rule is off until the next heating start or a new target (at 80 C the UV LED fans pulled the chamber to 72.2 C at 100 % output and 9007 stopped a working heater). Re-read live."
  },
  "heater": {
    "channel": "PWM_HEATER",
    "fan": "FAN_HEATER",
    "fan_pwm": 100,
    "thermistor": "TEMP_CHAMBER",
    "min_fan_rpm": 100,
    "temp_valid_min": -20,
    "temp_valid_max": 120,
    "health_check_sec": 10,
    "_comment": "Heater safety. Before enabling, the cooling 'fan' is started at 'fan_pwm' (default 100% PWM) and must spin above 'min_fan_rpm', and 'thermistor' must read a valid temperature within [temp_valid_min, temp_valid_max]. While the heater is on, both are re-checked every 'health_check_sec' seconds; any failure turns the heater OFF immediately. Change 'fan_pwm' here only - no source change or recompile needed; each heater activation reads the latest value."
  },
  "heating": {
    "target_temp": 60.0,
    "target_min": 30.0,
    "sample_sec": 0.05,
    "kp": 0.22,
    "ki": 0.00015,
    "kd": 0.0,
    "integ_max": 0.85,
    "integ_min": 0.0,
    "at_temp_band": 1.5,
    "cooldown_sec": 900,
    "cooldown_fan_pwm": 30,
    "_comment": "Heating mode (temperature_control.py, PI(D) + delta-sigma control). Entry runs the 'heater' safety pre-flight (door closed, heater fan spin-up + RPM verified, thermistor valid) and keeps the heater fan on for the whole mode. Every 'sample_sec' (50 ms) the PI computes a 0..1 power command: control = kp*err + integ + kd*(err - prev_err), with integ += ki*err clamped to [integ_min, integ_max]; a first-order delta-sigma modulator streams that power to PWM_HEATER as per-cycle ON/OFF so the element's average ON-time equals the commanded power. |error| <= 'at_temp_band' C reports 'at temperature'. On stop the heater turns off immediately and the fan runs on at 'cooldown_fan_pwm' %% for 'cooldown_sec' s before stopping. 'target_min' is the lowest target temperature that can be entered (default 30 C): starting below it is rejected, and a mid-run setpoint below it is clamped up."
  },
  "servo": {
    "gpio": 8,
    "signal_inverted": true,
    "driver": "auto",
    "settle_sec": 1.5,
    "_comment": "Damper servo (MG90S) on GPIO8. The board buffers the signal through Q16 (transistor driver, J2_MOTOR_DAMPER) which INVERTS it - signal_inverted=true pre-inverts the pulses so the servo sees normal ones. Set false only if the servo is wired directly to the GPIO pin. driver: auto|pio|lgpio - pio = hardware-timed pulses from the RP1 PIO block via server/hardware/pio_servo (build-pio-servo.sh; 1 us exact, no jitter); lgpio = software-timed PWM fallback (jitters -> servo shivers, may stop short). auto picks pio when available. settle_sec: how long to keep pulsing after a move before releasing (must cover the full travel under load; 0 = hold forever)."
  },
  "cooling": {
    "damper_open_angle": 0,
    "damper_closed_angle": 90,
    "heater_fan": "FAN_HEATER",
    "heater_fan_pwm": 100,
    "chamber_fan": "FAN_COOLING",
    "thermistor": "TEMP_CHAMBER",
    "mode_pwms": {
      "fast": 100,
      "medium": 60,
      "slow": 30
    },
    "fast_led_fan_pwm": 100,
    "target_temp": 25.0,
    "sample_sec": 1.0,
    "window_sec": 30.0,
    "pwm_min": 0.0,
    "pwm_max": 100.0,
    "temp_valid_min": -20,
    "temp_valid_max": 120,
    "_comment": "Cooling mode (FIXED chamber-fan duty, no closed-loop rate control). Entry sequence: damper (servo) to 'damper_open_angle', then 'heater_fan' fixed at 'heater_fan_pwm' % for the whole mode, then 'chamber_fan' at a constant duty for the whole mode - the UI modes map to duties via 'mode_pwms' (fast=100, medium=60, slow=30 %). The loop samples 'thermistor' every 'sample_sec' s and estimates dT/dt over a sliding 'window_sec' s window for status/telemetry only. The mode ends automatically at 'target_temp': fans off, damper to 'damper_closed_angle'. Verify damper angles on the bench. 2026-10-01: swapped to open=90 / closed=0 - on the test unit 'Open' physically closed the damper and 'Close' opened it with 0 / 90 (the servo / linkage is mounted the other way round; every software layer was consistent). 2026-10-26 (sCureBox 1.0.119): back to open=0 / closed=90 - with the damper on the PIO helper (now in every Origin package) 90 / 0 was reversed again on the Origin unit (user); the 2026-10-01 swap compensated the software-PWM path."
  },
  "pressure_sensor": {
    "adc": "U7",
    "channel": 3,
    "mode": "analog_voltage",
    "v_min": 1.0,
    "v_max": 5.0,
    "i_min_ma": 4.0,
    "i_max_ma": 20.0,
    "shunt_ohms": 120.0,
    "p_at_v_min_mpa": 0.0,
    "p_at_v_max_mpa": 1.0,
    "divider": 1.0,
    "adc_saturation_volts": 3.2,
    "on_above_volts": 2.0,
    "set_point_mpa": 0.1,
    "max_bar": 3.0,
    "min_bar": 0.5,
    "flow_check_enabled": true,
    "flow_check_window_sec": 5,
    "flow_check_min_drop_bar": 0.3,
    "required": true,
    "not_reading_after_sec": 20,
    "_comment_required": "N2 sensor supervision (user, 2026-10-25): with required true the sensor must give a valid reading - a read error, a saturated input or an analog output outside its range (below 90 % of v_min / i_min, above 110 % of v_max / i_max) for not_reading_after_sec raises Err 9016 and opening nitrogen is refused until it reads again (an open valve is NOT closed). The boot self-test checks it too. Switch mode has no pressure value by design and is never flagged. Set required false on a machine without the sensor.",
    "_comment_flow_check": "N2 flow check (user, 2026-10-25): the reading taken with the valve closed just before it opens must drop by flow_check_min_drop_bar within flow_check_window_sec after it opens, else nitrogen is not reaching the chamber (valve stuck, coil not driven, tube blocked): Err 9015 and the valve closes. No real bar reading before or after = no check.",
    "_comment_limits": "N2 line limits (user, 2026-10-25): above max_bar the nitrogen valve is refused and closed at once (Err 9008, clears below the limit); below min_bar nitrogen is refused - no supply (Err 9009). Only a real bar reading counts: no reading / switch mode / saturated input never blocks.",
    "model": "SMC ISE20A / ISE20B with analog output (CAT.ES100-114); model code -R/-T = 1-5 V voltage output, -S/-V = 4-20 mA current output",
    "rated_range_mpa": [
      -0.1,
      1.0
    ],
    "set_range_mpa": [
      -0.105,
      1.05
    ],
    "resolution_mpa": 0.001,
    "supply": "12-24 VDC +/-10 %",
    "_comment": "N2 line pressure: gray lead (analog output) -> Analog_IN -> R86 (120 R) -> ADS1115 U7 AIN3 (I2C1 0x49). mode analog_voltage: linear through (v_min, p_at_v_min_mpa) and (v_max, p_at_v_max_mpa) - ISE20 positive pressure (datasheet 'Analogue Output', points A/B/C): 1 V = 0 MPa, 5 V = 1.000 MPa, 0.6 V = -0.100 MPa, i.e. 4 V per MPa; so 0.6 MPa (6 bar) = 3.4 V. p_at_v_min_mpa / p_at_v_max_mpa are the conversion points, NOT the rated range (rated_range_mpa below); they were p_min_mpa -0.1 / p_max_mpa 1.0 until sCureBox 1.0.35, which read every value 0.1 MPa too low near zero (1.0 V = -1 bar with no pressure). mode analog_current: I * shunt_ohms then 4 mA = 0 MPa, 20 mA = 1.0 MPa (2.4 mA = -0.1 MPa) (only valid if R86 is a shunt to GND - on the schematic it is in SERIES). mode switch: OUT1/OUT2 lead on the input, on/off only. 'divider' = sensor volts / ADC volts of a divider fitted on Analog_IN (none today). The ADS1115 is supplied from 3.3 V: above adc_saturation_volts the pin is clamped, mpa is reported null and 'saturated' true - with 1-5 V that is every pressure above ~0.55 MPa (3.2 V), i.e. the 6 bar line (3.4 V) ALWAYS saturates until a 2:1 divider is fitted (then set divider 2.0). Exposed as /api/state.n2Pressure and, when readable, n2LinePressure (bar) for the Settings 6 bar guard. BENCH 2026-09-14 (testingcm5): 0.52 V with no pressure (a 1-5 V analog output would give 1.36 V at 0 MPa -> the lead on Analog_IN reads like a switch output or the sensor was unpowered), ADC clamped with pressure. Model code, lead colour on Analog_IN and the display reading still to be confirmed on the unit."
  },
  "sensor_filter": {
    "glitch_hold_sec": 15,
    "_comment": "Glitch tolerance for every analog sensor: the NTC thermistors (chamber, LED panels) and the N2 pressure input. When a sensor reads bad (open / shorted NTC, temperature outside the heater's temp_valid_min..temp_valid_max, I2C error) its last good value is kept for up to 'glitch_hold_sec' seconds, so a short noise burst does not stop the heater, refuse a job or raise 9001/9050. A fault that lasts longer is reported as before (the 60 s open-sensor alert timer starts only then). While holding, the heater loop controls on the held chamber value - keep this well below the time the chamber can overheat at full heater power. 0 disables the hold."
  },
  "_modes_note": "In 450nm mode only LEDs whose 'modes' list contains '450nm' may turn on (the Door LED). In 405nm mode every LED whose 'modes' contains '405nm' may turn on. Each LED's 'fan' starts automatically at 'fan_speed' when the LED is turned on, and stops when the LED is turned off."
}
```

### config/presets.json

```json
[
  {
    "id": "preset-stretch-80-v2",
    "name": "P3 Stretch 80 V2",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 35,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 45,
        "intensity": null,
        "time": 22,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 45
  },
  {
    "id": "preset-ind403",
    "name": "LOCTITE 3D IND403 High Modulus",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 65,
        "intensity": null,
        "time": 12,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 55
  },
  {
    "id": "preset-ST45",
    "name": "Ultracur3D ST45",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-3843",
    "name": "LOCTITE 3D 3843 High Toughness",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-3172",
    "name": "LOCTITE 3D 3172 High Impact",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-ind405",
    "name": "LOCTITE 3D IND405 Clear",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 40,
        "intensity": null,
        "time": 6
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 40,
        "intensity": null,
        "time": 15,
        "uvIntensity": 60,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Bleacher",
        "temperature": 40,
        "intensity": null,
        "time": 10,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 4,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 39
  },
  {
    "id": "preset-ind402",
    "name": "LOCTITE 3D IND402 High Rebound",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 35,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 45,
        "intensity": null,
        "time": 22,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 45
  },
  {
    "id": "preset-silicone-25a",
    "name": "P3 Silicone 25A",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 35,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 45,
        "intensity": null,
        "time": 22,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 45
  },
  {
    "id": "preset-med-silicone-25a",
    "name": "P3 MED Silicone 25A",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 35,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 45,
        "intensity": null,
        "time": 22,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 45
  },
  {
    "id": "preset-ind3380-esd",
    "name": "LOCTITE 3D IND3380 ESD",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 65,
        "intensity": null,
        "time": 12,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 55
  },
  {
    "id": "preset-3955-fst",
    "name": "LOCTITE 3D 3955 FST",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 65,
        "intensity": null,
        "time": 12,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 55
  },
  {
    "id": "preset-stretch-ind475",
    "name": "P3 Stretch IND475",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 35,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 45,
        "intensity": null,
        "time": 22,
        "uvIntensity": 15,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "medium"
      }
    ],
    "totalDuration": 45
  },
  {
    "id": "preset-dura56",
    "name": "Stratasys Dura56",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-med-412",
    "name": "LOCTITE 3D MED 412",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-med-413",
    "name": "LOCTITE 3D MED 413",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-weatherx-100",
    "name": "Somos WeatherX 100",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-rg-3280",
    "name": "Ultracur3D RG 3280",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 65,
        "intensity": null,
        "time": 12,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 55
  },
  {
    "id": "preset-ind3785",
    "name": "LOCTITE 3D IND3785 Low Migration",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 55,
        "intensity": null,
        "time": 15,
        "uvIntensity": 30,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 46
  },
  {
    "id": "preset-deflect-110",
    "name": "P3 Deflect 110",
    "isPreset": true,
    "createdAt": "2026-10-31T00:00:00Z",
    "steps": [
      {
        "step": 1,
        "process": "Drying",
        "temperature": 45,
        "intensity": null,
        "time": 8
      },
      {
        "step": 2,
        "process": "Cure",
        "temperature": 65,
        "intensity": null,
        "time": 12,
        "uvIntensity": 50,
        "timerMode": "on-target",
        "uvStartMode": "at-target"
      },
      {
        "step": 3,
        "process": "Cooling",
        "temperature": 30,
        "coolingMode": "fast"
      }
    ],
    "totalDuration": 55
  }
]

```

### config/system.json

```json
{
  "serialNumber": "",
  "firmware": "0.1.0",
  "lastBoot": "2026-03-29T08:23:00",
  "deviceName": "OR200001",
  "leadOnTimeHours": 10,
  "model": "S-Cure A",
  "hardwareRevision": "CM5-rev1.0",
  "manufacturer": "S-Cure Ltd.",
  "organizationId": "",
  "setupComplete": false
}

```

### config/origin.json

```json
{
  "_comment": "Settings / Setup > Sign in to Origin: a headless browser opens sign_in_url, its picture is shown inside the Sign in dialog (taps and the on-screen keyboard go back to the page), and the app reads only the organizationId from the site's own replies whose URL contains api_host. Nothing about the sign-in is stored.",
  "sign_in_url": "https://app.origin.io/models",
  "api_host": "api.origin.io",
  "browser_path": "",
  "run_as": "scure",
  "language": "en-US",
  "reveal_delay_sec": 10,
  "fade_ms": 900,
  "timeout_sec": 300
}

```
