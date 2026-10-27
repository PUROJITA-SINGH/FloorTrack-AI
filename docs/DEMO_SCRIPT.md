# FloorTrack AI — Demonstration & Viva Script

> **Architecture:** Software-only local prototype (FastAPI + SQLite + React/Vite)  
> **No Docker, PostGIS, MQTT, or external cloud services required.**

---

## 1. Prerequisites & Environment Setup

### 1.1 Python Virtual Environment & Backend Setup
```powershell
# From the repository root:
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r backend/requirements.txt
```
*(On Linux/macOS: use `source .venv/bin/activate && pip install -r backend/requirements.txt`)*

### 1.2 Frontend Setup
```powershell
cd frontend
npm install
cd ..
```

---

## 2. Starting the Application (One-Command Run)

From the repository root, start both the FastAPI backend and Vite frontend with a single command:

```powershell
python run.py
```

This single command automatically:
1. Initializes SQLite schema and seeds clean demo data if not already present.
2. Starts the FastAPI backend at `http://127.0.0.1:8000` (Swagger UI at `/docs`).
3. Starts the Vite React dashboard at `http://localhost:5173`.

---

## 3. Resetting the Demo Database

To restore the demo to its pristine seeded state at any time, **stop the backend first** (press `Ctrl+C` in the terminal running `python run.py`). The database file is locked while the server runs on Windows, so reset only after stopping it. Then:

```powershell
python backend/scripts/reset_demo.py
python run.py
```

> Run this reset before every demo. The `shortage_surge` scenario adds demand events, so the forecast stays at `critical` until the database is reset.

This deletes `backend/data/floortrack.db` (and any associated WAL/journal files) and re-executes `seed_database()`, recreating:
- Floor 1 with 6 zones (Ward A, Ward B, Corridor 1, Storage, Maintenance, Nurse Station)
- 4 BLE gateways and 3 hallway cameras
- 3 PAR level thresholds (Ward A: 10, Ward B: 8, Storage: 5)
- 13 infusion pumps (`P-001` through `P-012`, `P-042`), all initialized to `operational_status = "status_unknown"`
- 10 demand events

---

## 4. Running Simulator Scenarios

All simulator scenarios stream synthetic payloads exclusively via public HTTP POST endpoints (`/api/v1/events/camera`, `/api/v1/events/ble`, `/api/v1/events/demand`). They never access the database directly and never write operational status.

Run any scenario in a separate terminal:
```powershell
python simulators/run_scenario.py --scenario <scenario_name>
```

| Scenario | Command | Key Behavior Demonstrated |
|---|---|---|
| `normal_movement` | `python simulators/run_scenario.py --scenario normal_movement` | Agreeing camera and multi-gateway BLE track asset `P-001` moving from Ward A to Ward B. |
| `agreement` | `python simulators/run_scenario.py --scenario agreement` | Camera and 2+ BLE gateways agree on Ward A for `P-002`, raising confidence to `high` band. |
| `camera_occlusion` | `python simulators/run_scenario.py --scenario camera_occlusion` | Camera view obstructed; BLE fallback localizes `P-003` to Ward B with inspectable quality factors. |
| `ble_signal_bleeding` | `python simulators/run_scenario.py --scenario ble_signal_bleeding` | Camera sees `P-004` in Ward A while BLE wall-reflection suggests Ward B; engine triggers `sensor_disagreement` review alert and preserves prior zone. |
| `ble_tag_failure` | `python simulators/run_scenario.py --scenario ble_tag_failure` | Tag battery failure (0 gateways); camera-only detection locates `P-005` in Ward A with `low` confidence; availability remains untouched. |
| `unknown_asset` | `python simulators/run_scenario.py --scenario unknown_asset` | Unregistered tag detection is safely logged with `unknown_asset=True` without altering system state. |
| `stale_gateway` | `python simulators/run_scenario.py --scenario stale_gateway` | Readings older than 20 minutes are accepted as historical evidence and marked `stale` band. |
| `shortage_surge` | `python simulators/run_scenario.py --scenario shortage_surge` | Simulates surge demand for infusion pumps in Ward A; shortage forecast updates to `critical` band with demand and supply figures printed. |
| `excess_inventory` | `python simulators/run_scenario.py --scenario excess_inventory` | Generates draft redistribution recommendations from surplus to deficit wards using neutral wording. |
| `camera_silent` | `python simulators/run_scenario.py --scenario camera_silent` | Healthy but idle camera produces coverage figures and decaying confidence; modifies NO asset location, band, or availability. |
| `status_never_confirmed` | `python simulators/run_scenario.py --scenario status_never_confirmed` | Camera locates `P-009` in Ward A; because no clinician confirmed availability, status remains `status_unknown` and usable count in Ward A excludes `P-009`. |

---

## 5. Short Viva Demonstration Walkthrough

Follow these steps for a live presentation or examination defense:

### Step 1: Open the Searchable Map UI
1. Open <http://localhost:5173> in the browser.
2. Point out the interactive 2D floor plan rendering Floor 1's zones (Ward A, Ward B, Corridor 1, Storage, Maintenance, Nurse Station).
3. Search for **`P-042`** in the search box.
4. Click on `P-042` to open the **Asset Detail Drawer**.
5. **Key Viva Point (Separation of Location and Availability):**
   - Point out that location is displayed as a zone with confidence band and freshness.
   - Point out that **Operational Status** is displayed in a separate card as **Not confirmed** (`status_unknown`). Explain to the examiner: *"A sensor can tell you where a pump is, but it can never verify whether it has been sterilized or is ready for patient use. Therefore, availability is strictly decoupled from tracking."*

### Step 2: Demonstrate Camera Silence (Non-Negotiable Rule 1)
1. Run the camera silent scenario in terminal:
   ```powershell
   python simulators/run_scenario.py --scenario camera_silent
   ```
2. Explain to the examiner: *"Sensor silence produces NO state. An idle or silent hallway camera does not mark any asset as missing, does not alter location, and does not alter availability. It only updates coverage figures and lets confidence decay over time."*

### Step 3: Demonstrate Sensor Conflict & Named Review State (Non-Negotiable Rule 4)
1. Run the signal bleeding conflict scenario in terminal:
   ```powershell
   python simulators/run_scenario.py --scenario ble_signal_bleeding
   ```
2. In the UI, click **Run fusion** or select `P-004`.
3. Point out that the marker displays a dashed outline indicating **Sensor Disagreement**.
4. Open the asset drawer: the decision reason explicitly notes *"Sensor disagreement: camera reports Ward A, BLE reports Ward B"*.
5. Explain to the examiner: *"The fusion engine never silently picks a winner between conflicting sensors. Instead, it logs a named review state and flags a Location Review alert for clinical staff."*

### Step 4: Confirm Availability as a Named User (Non-Negotiable Rule 2)
1. In the asset detail drawer for `P-004` (or `P-042`), click the **Confirm available** button.
2. Note that the status transitions from `status_unknown` to **Available**, displaying the confirming user and confirmation timestamp.
3. Explain to the examiner: *"Only a named clinician or workflow adapter can write availability via `POST /api/v1/assets/{id}/operational-status`. Database triggers reject sensor, simulator, and bulk-import attempts."*

### Step 5: Review PAR Inventory & Neutral Language (Non-Negotiable Rule 6)
1. Navigate to the **Inventory** page (<http://localhost:5173/inventory>).
2. Point out the breakdown: Usable, In-Use, Maintenance, and Unknown.
3. Point out the open PAR deficit alert: *"Usable count (X) is below PAR (10). Y additional units recommended."*
4. Explain to the examiner: *"Alerts use strictly neutral surplus/deficit framing. Words like 'hoarding', 'theft', 'stolen', or individual staff names are rejected at write time."*

### Step 6: Inspect Shortage Forecast
1. Navigate to the **Forecast** page (<http://localhost:5173/forecast>).
2. Point out the transparent shortage indicator: prints upcoming demand, projected usable supply, shortfall units, and band word (`low`, `moderate`, `high`, `critical`).
3. Explain to the examiner: *"The shortage indicator is an explicit, reproducible shortfall ratio, explicitly labeled `calibrated=false`. It does not make probabilistic or opaque claims."*

### Step 7: Clean Up
Stop the backend with `Ctrl+C`, then reset the demo database to its fresh seeded state:
```powershell
python backend/scripts/reset_demo.py
```
