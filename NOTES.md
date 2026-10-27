# FloorTrack AI — Implementation Notes & Engineering Audit

## 1. Specification Compliance Matrix

This matrix maps every functional requirement (FR1–FR22) and acceptance criterion (AC1–AC9) from the project specification (`MINI PROJECT/Documentation.md`, Canonical TRD/PRD) to its implementation file, test suite, and operational status.

| Requirement / Criterion | Status | Implementation File | Verification Test / Evidence | Description |
|---|---|---|---|---|
| **FR1** | done | `backend/app/routers/events.py` | `backend/tests/test_camera_events.py`<br>`test_validation.py::test_valid_camera_payload` | `POST /api/v1/events/camera` ingests positive camera detections with structured JSON schema (camera_id, event_id, timestamp, detections[]). |
| **FR2** | done | `backend/app/services/identity.py` | `test_validation.py::test_unknown_identifier`<br>`backend/tests/test_camera_events.py` | Camera serial/identifier strings are resolved against asset tags and serials; unregistered identifiers are flagged `unknown_asset` and do not alter state. |
| **FR3** | done | Architecture boundary | Architecture verification<br>Codebase scan | No display, screen error, OCR, or CNN telemetry extraction pipeline exists; visual inputs are simulated positive detections only. |
| **FR4** | done | `backend/app/routers/events.py` | `backend/tests/test_ingestion.py`<br>`test_validation.py::test_duplicate_event_idempotency` | `POST /api/v1/events/ble` accepts batched gateway readings for one tag and timestamp in a single `readings[]` payload. |
| **FR5** | done | `backend/app/routers/events.py` | `backend/tests/test_ingestion.py` | Optional phase and AoA values are checked against gateway declared capabilities; unvalidated values reject with HTTP 422. Position never derives from phase/AoA. |
| **FR6** | done | `backend/app/services/localization.py` | `backend/tests/test_localization.py`<br>`test_validation.py::test_single_gateway_no_position` | Multi-gateway Weighted Centroid Localization (WCL). A single gateway yields NO position (`insufficient_gateways`). Returns gateway count, RSSI spread, and quality factors. |
| **FR7** | done | `backend/app/services/localization.py` | `backend/tests/test_localization.py` | Calibration constants (`tx_power=-59.0`, `path_loss_exponent=2.0`) are recorded with every estimate and explicitly labeled `site-simulated`. |
| **FR8** | done | `backend/app/services/localization.py`<br>`backend/app/routers/events.py` | `backend/tests/test_ingestion.py`<br>`backend/tests/test_localization.py` | Phase/AoA metrics validated against gateway capabilities; strictly zone-level positioning is output without claiming sub-metre accuracy. |
| **FR9** | done | `backend/app/services/fusion.py` | `backend/tests/test_fusion.py`<br>`test_validation.py::test_camera_ble_conflict_high_score` | Cross-modality conflict between camera doorway crossing and BLE zone produces a named review state (`needs_review`), logs `Alert(sensor_disagreement)`, and preserves previous zone. |
| **FR10** | done | `backend/app/services/fusion.py` | `test_validation.py::test_camera_silent_no_state_change`<br>Scenario: `camera_silent` | Sensor silence produces no asset state change; healthy idle cameras update coverage figures only and allow confidence to decay on staleness. |
| **FR11** | done | `frontend/src/pages/MapPage.tsx`<br>`frontend/src/components/FloorMap.tsx` | UI verification<br>`curl http://localhost:5173` | Live, interactive 2D digital floor map rendered in browser with SVG zones and dynamic asset markers. |
| **FR12** | done | `frontend/src/components/AssetDetailDrawer.tsx`<br>`frontend/src/components/AssetSearch.tsx` | UI verification<br>`backend/tests/test_assets.py` | Search returns asset zone, confidence band, freshness, and separate operational availability with its source, actor, and confirmation timestamp. |
| **FR13** | done | `backend/app/routers/assets.py`<br>`frontend/src/components/AssetDetailDrawer.tsx` | `backend/tests/test_assets.py` | `GET /api/v1/assets/{asset_id}/history` provides zone movement timeline and evidence links without personal/staff attribution. |
| **FR14** | done | `backend/app/routers/inventory.py` | `backend/tests/test_inventory.py`<br>`test_validation.py::test_usable_count_exclusion` | Inventory tracks usable, in_use, maintenance, and status_unknown counts per zone; unconfirmed (`status_unknown`) assets are strictly excluded from usable counts. |
| **FR15** | done | `backend/app/routers/inventory.py` | `backend/tests/test_inventory.py` | Reconciles usable inventory against ward PAR thresholds and automatically raises `par_deficit` alerts when usable inventory falls below PAR. |
| **FR16** | done | `backend/app/routers/inventory.py` | `backend/tests/test_inventory.py`<br>Scenario: `excess_inventory` | `GET /api/v1/inventory/recommendations` pairs surplus zones with deficit zones and generates draft redistribution recommendations using neutral wording. |
| **FR17** | done | `backend/app/routers/inventory.py`<br>`backend/app/prohibited_alert_terms.json` | `test_validation.py::test_no_prohibited_terms_in_alerts`<br>`backend/tests/test_inventory.py` | Screen alerts at write time: rejects prohibited words ("hoarding", "theft", "stolen", "neglect") and personal human names. |
| **FR18** | done | `backend/app/routers/assets.py`<br>`backend/app/services/status_sweep.py`<br>`backend/app/database.py` | `backend/tests/test_provenance.py`<br>`backend/tests/test_status_sweep.py`<br>`test_validation.py::test_status_expiry` | Availability is modified ONLY via `POST /api/v1/assets/{asset_id}/operational-status` by named user or adapter; database triggers reject other sources. Unconfirmed statuses decay to `status_unknown`. |
| **FR19** | done | `backend/app/main.py`<br>`docs/openapi.json` | `backend/tests/test_openapi.py` | REST APIs strictly comply with OpenAPI 3.1.0; published `docs/openapi.json` schema is verified against all mounted FastAPI routes. |
| **FR20** | done | `backend/app/routers/integrations.py` | `backend/tests/test_inventory.py` | `POST /api/v1/cmms/work-orders` creates draft maintenance orders requiring supervisor confirmation; no autonomous dispatch occurs. |
| **FR21** | done | `simulators/run_scenario.py`<br>`simulators/ble/`<br>`simulators/camera/` | `simulators/tests/test_scenarios.py`<br>CLI scenario runner | Standalone data generators stream synthetic and reference-adapted events exclusively over public HTTP endpoints without touching the database directly. |
| **FR22** | done | `simulators/scenarios/definitions.json`<br>`simulators/run_scenario.py` | 11/11 scenario passes<br>`simulators/tests/test_scenarios.py` | 11 named test scenarios with recorded expected outputs, including `camera_silent` and `status_never_confirmed`. |
| **AC1** | done | `backend/app/database.py` | Full local execution<br>pytest suite | Zero hardware required; runs entirely locally on SQLite + Python + React/Vite without external services. |
| **AC2** | done | `backend/app/services/fusion.py` | `backend/tests/test_fusion.py`<br>Scenario: `ble_signal_bleeding` | Fusion inspectability: sensor agreement boosts confidence; sensor disagreement creates review alert and preserves previous location. |
| **AC3** | done | `frontend/src/pages/MapPage.tsx` | Browser map UI walkthrough | Searchable map displays zone, confidence band, freshness, and distinct availability provenance. |
| **AC4** | done | `backend/app/routers/alerts.py`<br>`backend/app/routers/integrations.py` | `backend/tests/test_inventory.py` | Neutral surplus/deficit alerts dispatched to mock Slack/Teams webhooks upon human confirmation. |
| **AC5** | done | `docs/openapi.json`<br>`backend/app/main.py` | `backend/tests/test_openapi.py` | OpenAPI 3.1 document generated and validated against all 28 registered API endpoints. |
| **AC6** | done | `backend/app/services/fusion.py` | `test_validation.py::test_camera_silent_no_state_change`<br>Scenario: `camera_silent` | Negative test verified: sensor silence modifies no asset location, band, or availability; coverage figure is updated. |
| **AC7** | done | `backend/app/routers/assets.py`<br>`backend/app/database.py` | `test_provenance.py`<br>`test_status_sweep.py`<br>`test_validation.py` | Availability cannot be set by sensors, simulators, or bulk imports; DB triggers enforce provenance; unconfirmed statuses decay to `status_unknown`. |
| **AC8** | done | `backend/app/services/forecast.py`<br>`backend/app/routers/forecast.py` | `backend/tests/test_forecast.py`<br>`test_deterministic_repeatability` | Deterministic shortage forecast: computes shortfall ratio, prints demand and usable supply, provides uncalibrated indicator, never a percentage-of-likelihood. |
| **AC9** | done | `backend/scripts/seed.py`<br>`SCOPE.md` | Seed verification | Scope strictly held to one floor (Floor 1) and one asset type (Infusion Pumps, 13 units). |

---

## 2. Architecture Decisions

1. **Storage Layer: SQLite with Native Provenance Triggers**
   - In alignment with user instructions ("Do not add Docker, MQTT, PostGIS or cloud services"), the primary backend persistence layer uses SQLite via SQLAlchemy with custom SQLite triggers (`validate_asset_status_insert`, `validate_asset_status_update`).
   - Ensures strict compliance with Non-Negotiable Rule 2 (operational status provenance) without requiring an external PostgreSQL instance.

2. **Decoupled Location and Availability Models**
   - Sensor events (camera and BLE) stream into the ingestion layer and trigger Weighted Centroid Localization and Multi-Modal Fusion.
   - Fusion writes strictly to `location_estimates`, `fusion_decisions`, and `asset_current_state.zone_id`.
   - `Asset.operational_status` can ONLY be written by `POST /api/v1/assets/{asset_id}/operational-status` through a named user or workflow adapter (`status-expiry-sweep`). The ingestion path has no access to operational status.

3. **Weighted Centroid Localization (WCL) with Zone Bounding**
   - Position estimates require at least 2 distinct gateways hearing the tag. Single-gateway events are recorded as evidence but produce no position (`method="insufficient_gateways"`).
   - Gateway positions are weighted inversely by estimated distance squared ($w = 1 / d^2$). Ray casting assigns coordinates to zone polygons.

4. **Multi-Modal Uncertainty and Review Workflow**
   - When BLE zone and camera detection conflict, the system never silently guesses a winner. It sets `decision_status="sensor_disagreement"`, records `review_state="needs_review"`, creates an actionable review alert, and retains the asset's prior confirmed zone.

5. **Neutral Alert Vocabulary & Human Confirmation Gating**
   - Alert titles and messages are screened at write time against `prohibited_alert_terms.json` to prevent judgmental language ("hoarding", "theft", "stolen", "neglect") and staff names.
   - Redistribution recommendations and CMMS maintenance work orders are created as drafts (`status="draft"`), requiring human confirmation before dispatch.

---

## 3. Assumptions and Scope Boundaries

- **Software-Only Prototype**: All hardware inputs (Jetson cameras, ESP32 BLE gateways, BLE beacon tags) are simulated via structured JSON payloads.
- **Scope Discipline**: Exactly one hospital floor ("Floor 1") with 6 zones (Ward A, Ward B, Corridor 1, Storage, Maintenance, Nurse Station) and one asset type (Infusion Pumps, 13 units `P-001`–`P-012`, `P-042`).
- **Confidence Calibration**: Confidence scores are explicit, inspectable weighted evidence sums clamped to $[0, 1]$, not probabilities.
- **Shortage Indicator**: The shortage forecast is a normalized shortfall ratio ($\max(0, \text{demand} - \text{usable}) / \text{demand}$), labeled `calibrated=False`.
- **Reference Code Reuse**: Signal replay concepts and WCL math were adapted from `reference/MedTracker` and `reference/Indoor-Positioning-techniques` with proper attribution; ML room classifiers and external UI dependencies were deliberately excluded.


---

## 4. Latest Changes (final polish pass)

- **Demo reset:** `backend/scripts/reset_demo.py` deletes the SQLite file (and WAL/journal files) and re-seeds clean demo data. The backend must be stopped first because the file is locked while the server runs on Windows. Run it before every demo, since the `shortage_surge` scenario adds demand events and leaves the forecast at `critical`.
- **Status history endpoint:** `GET /api/v1/assets/{asset_id}/status-history` returns every availability change with source, actor and reason. The `status_never_confirmed` scenario uses it to prove that no status write happened (`status_write_made` is computed from the real history, not hardcoded).
- **Alert text validation:** `validate_alert_text` now allows legitimate zone and asset-type names (for example "Emergency Department", "Ward Alpha") while still rejecting prohibited words (hoarding, theft, stolen, neglect, lazy, negligent) and individual names (for example "John Smith", "Dr. Rao", "Nurse Priya"). It is applied on every alert write path (inventory, alerts, integrations).
- **Old PostgreSQL design removed:** Docker Compose, the SQL migrations and `run_migrations.py` were removed. The project is SQLite only, and `DEMO_SCRIPT.md` and the README describe the same single run path.
- **Configuration:** `backend/.env.example` was corrupted by a leftover PostgreSQL URL and is fixed. `test_config.py` loads the example values to keep it valid.
- **Availability display:** the drawer shows "Not confirmed" for `status_unknown` assets and shows "Confirmed by <name>" only after a named user or workflow adapter confirmed. After a confirmation the drawer also shows that actor and reason immediately.
- **Map:** zone names sit in the top-left corner of each zone and asset codes are printed under each marker, so labels are never covered.
- **Decision label (deliberate non-change):** a single low-confidence camera detection is still reported with `decision_status = "confirmed"` and confidence band `low`. "Confirmed" means one sensor produced positive evidence and nothing contradicted it. The confidence band, not the decision label, tells how much to trust it. Renaming it to "provisional" was considered and skipped to avoid changing the fusion contract late in the project.
