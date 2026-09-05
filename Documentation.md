# 1.Project Overview

## 1. Problem Statement

Hospitals routinely lose track of more than a tenth of their movable medical equipment, such as wheelchairs, beds, and infusion pumps, because there is no reliable way to see where they are left. This forces busy nurses to waste nearly an hour of every shift physically hunting for missing equipment, causing critical care delays, nurse stress, and wasted labor. To cope with these "phantom shortages," hospital departments begin hoarding devices, forcing the facility to purchase or rent up to 30% more medical equipment than they actually need to meet patient demand.

## 2. Solution (4–5 lines)

We are building "Aura-Fusion IPS," a software system that programmatically fuses lightweight edge-based computer vision at hallway chokepoints with Bluetooth beacon tracking. It processes existing hallway security camera feeds using lightweight AI to identify moving medical assets and read their serial IDs in real-time. Simultaneously, it tracks wireless signals from low-cost Bluetooth tags attached to equipment, calculating their locations even when hidden from camera views. The software maps every asset onto a live, searchable web application, predicts inventory shortages, and automatically alerts staff about hoarded equipment.

## 3. My Role (Software Only)

I am responsible for the software development of the Aura-Fusion IPS project, focusing on the core pipelines, fusion algorithms, and integrations. My specific responsibilities include:

- **Implementing the Edge-Vision Pipeline**: Deploying lightweight object detection models (YOLO26) to categorize assets, YOLO-GF to scan character-level asset ID numbers at over 130 FPS, and a CNN display-reader to extract live parameters from device screens.
- **Developing the Wireless Signal Pipeline**: Processing Bluetooth signal inputs from ESP32 proxies using phase-based multilateration algorithms and Weighted Centroid Localization (WCL) smoothed with XGBoost machine learning to calculate high-precision coordinate data.
- **Building the Aura-Fusion Engine**: Designing the data fusion layer that uses XGBoost classification to cross-validate location events, ensuring coordinate updates are verified against visual camera threshold crossings to eliminate room-bleeding errors.
- **Designing Client & Administrative Workflows**: Programming a searchable web-app map interface for floor nurses, automated anti-hoarding alerts triggered by ward-specific PAR-levels, and predictive inventory shortage algorithms.
- **Creating System Integrations**: Exposing documented REST APIs (under OpenAPI 3.1) to feed coordinate-update triggers directly into existing hospital CMMS platforms like Oxmaint.

I am _not_ responsible for physical hardware installation, drilling ceiling tiles to mount ESP32 proxies, running cables, physically tagging medical equipment, or making business procurement decisions.

## 4. High-Level Goal

The goal of this project is to develop and demonstrate a working prototype of "Aura-Fusion IPS," an open-standards, zero-infrastructure hybrid asset tracking software system. By leveraging pre-existing hospital security cameras and cheap Bluetooth beacons, the system aims to slash nurse equipment search times to under two minutes and eliminate capital waste from equipment hoarding. The software must demonstrate how edge-based visual AI and low-cost wireless signal processing can be fused to deliver accurate room-level mapping while remaining 90% cheaper than traditional, proprietary RTLS ceiling reader networks.

## 5. What Success Looks Like

- [ ] **Real-Time Data Fusion Works**: The central Aura-Fusion engine successfully fuses and cross-validates visual event feeds (YOLO26 ID detection) and Bluetooth signal metrics (WCL/phase-based coordinates).
- [ ] **Accurate Indoor Localization**: The system accurately maps asset locations on a live digital floor plan, resolving signal-bleeding and line-of-sight visual blockages.
- [ ] **Passive, Hands-Free Tracking**: The automated tracking operates silently in the background, requiring zero manual scanning, barcodes, or extra photographic tasks from busy clinical staff.
- [ ] **Automated Anti-Hoarding & Predictive Workflows Active**: The system successfully triggers automated redistribution alerts on Slack/Teams when ward PAR-levels drop below safe limits and predicts localized shortages 24 to 48 hours in advance.
- [ ] **Open and Documented APIs**: The software successfully exposes REST APIs under a published OpenAPI 3.1 spec, integrating cleanly with third-party CMMS platforms like Oxmaint to trigger maintenance work orders.
- [ ] **Low-Latency Edge Performance**: Bounding-box detection executes with under 30ms latency on simulated local edge devices, and wireless coordinate triangulation updates process in under 1 second.

---



# 2. Software Scope Document

**Project:** Asset Tracking & Monitoring System (Aura-Fusion IPS) 

---

## Introduction

This document defines the **software boundaries** for the Aura-Fusion IPS mini-project. It explicitly states what the software will do (In Scope) and what it will not do (Out of Scope) to establish clear development boundaries and manage stakeholder expectations.

---

## In Scope (What the Software Will Do)

The software system is responsible for executing the following core data pipelines, processing algorithms, and client-facing workflows:

### 1. Ingest Simulated Camera Detection Data

- The software will provide an ingestion endpoint to accept structured visual data payloads representing asset camera crossings.
- It will parse and normalize real-time JSON detection outputs (such as asset category classifications from **YOLO26** and character-level printed serial ID numbers read by **YOLO-GF**).
- It will accept simulated telemetry values (such as battery status or active alerts) extracted by a coupled display-reading Convolutional Neural Network (CNN).

### 2. Ingest Simulated Wireless Signal Data

- The software will expose endpoints to receive raw Bluetooth Low Energy (BLE) proximity and ranging metrics forwarded from distributed gateway nodes.
- It will ingest Received Signal Strength Indicator (RSSI) measurements as well as **phase-based signal measurements** captured by simulated ESP32 proxy nodes.

### 3. Process Cross-Modal Data Fusion (Aura-Fusion Engine)

- The system will run a **Weighted Centroid Localization (WCL)** algorithm smoothed by an **XGBoost machine learning model** to resolve RSSI fluctuations and mitigate device heterogeneity.
- It will process high-precision analytical multilateration algorithms when phase-based ranging metrics are present.
- It will execute a **bidirectional data fusion loop** that cross-validates wireless coordinates against edge-camera gateway crossings (using XGBoost classification) to eliminate room-bleeding errors.
- It will integrate a **BiFormer attention model** simulation to calculate shelf counts even when target assets are up to 48% physically occluded.

### 4. Searchable Interactive Map Dashboard

- The software will display a live, searchable web-app map representing the facility's floor plan.
- It will allow users to search for specific equipment by category or serial ID (e.g., "IV Pump P-042") and display its real-time, room-level location coordinates on the map.

### 5. Automated Anti-Hoarding & PAR-Level Management

- The system will track and log active inventory counts per ward, corridor, and clinical storage zone.
- It will enforce unit-specific **PAR-level thresholds** and flag whenever a department's active equipment count drops below safe limits or when excess equipment is being hoarded in a single zone.

### 6. Automated Alert Dispatching

- The software will generate real-time alerts for inventory imbalances, equipment hoarding, or unexpected asset boundary crossings (geofencing).
- It will display active alerts in the central web UI dashboard and programmatically dispatch notifications to third-party communication channels (such as **Slack** or **Teams** webhooks).

### 7. OpenAPI Integration Endpoints

- The software will expose documented REST APIs designed under the **OpenAPI 3.1 specification**.
- It will support data outbound pushes to transmit live coordinate-update triggers and automated maintenance requests directly to a simulated CMMS platform (such as **Oxmaint**).

### 8. Simulated Data Playback Runners

- To enable zero-infrastructure validation, the software will include local Python scripts designed to "fake" physical hardware.
- These runners will read and stream historical, physical-layer radio databases (such as **TUJI1** or **UJIIndoorLoc**) and loop through image directories (such as the **Ritsumeikan Medicine Package Dataset**) to mimic active, live edge-camera and proxy networks.

---

## Out of Scope (What the Software Will NOT Do)

To maintain focus on software design and algorithm testing, the following physical, network, and production-level integrations are strictly excluded from this project's scope:

### 1. Hardware Procurement & Physical Installation

- No physical assembly, wiring, or mounting of wall cameras, Raspberry Pi servers, or ESP32 microcontrollers.
- No physical tagging of medical equipment with active BLE beacons or passive RFID labels.

### 2. Physical Camera & Network Configuration

- No camera lens alignment, physical calibration, or video feed troubleshooting.
- No network engineering (VLAN configuration, PoE switch setup, or wireless spectrum adjustments).

### 3. Active Battery & Tag Maintenance

- No physical collection, charging, or replacement of depleted CR2032 or lithium batteries inside the asset tag enclosures.

### 4. Production Hospital Information System (HIS) Integration

- The software will not connect to live, production hospital networks, clinical databases, or active electronic health record (EHR) systems.
- All integrations will run strictly within local, isolated testing sandboxes using simulated or public academic datasets.

### 5. Centimeter-Level Localization

- The software will not calculate sub-centimeter physical coordinates.
- The positioning output is strictly bounded to stable, room-level, or zone-level certainty.

---

## Acceptance Criteria

1. **Zero Hardware Requirement**: The entire software system must compile, run, and execute locally on a single machine utilizing simulated data streams.
2. **Successful Data Fusion**: The Aura-Fusion engine must successfully ingest simulated visual camera events and BLE signals, resolving signal-bleeding or camera occlusion to determine correct room-level locations.
3. **Functional Search & Map UI**: A user must be able to search for an asset ID in the web-app interface and see its simulated real-time coordinate position highlighted on a digital floor plan.
4. **Automated Workflow Triggers**: The system must successfully trigger and dispatch automated Slack/Teams notifications when a ward's active inventory drops below defined PAR-levels.
5. **Exposed API Compliance**: The software must expose documented, RESTful endpoints that comply with the OpenAPI 3.1 specification to push event updates.

---





# 3.Hardware Assumptions Document

**Project:** Asset Tracking & Monitoring System (Aura-Fusion IPS)  
**Document ID:** 03_Hardware_Assumptions  
**Version:** 1.0  
**Date:** August 20, 2026

---

## Introduction

This document outlines the **assumed hardware environment** that the Aura-Fusion IPS software is designed to interface with. While this mini-project focuses **strictly on software** and utilizes **simulated data feeds** for validation, documenting these hardware physical-layer boundaries demonstrates how a real-world clinical deployment operates and highlights the software's structural compatibility with physical infrastructure.

---

## 1. Hardware Components (Assumed to Exist)

### Camera System

- **Existing Optical Infrastructure**: The software assumes the availability of the hospital's pre-installed hallway security camera feeds. It does not require a new proprietary camera network.
- **Edge-Computing Nodes**: Each camera feed is assumed to be processed locally by a wall-mounted, low-power edge-computing processor (such as an **NVIDIA Jetson Nano or Orin**).
- **Edge Vision Pipeline**: The edge-computing nodes run highly optimized, lightweight single-stage object detectors (**YOLO26**) to classify asset types (e.g., "IV Pump"). A coupled character-level text recognizer (**YOLO-GF**) reads printed asset ID stickers/serial numbers on the equipment casing in real-time, while a display-reading CNN extracts telemetry directly from "dumb" medical screens. Bounding-box coordinate vectors and parsed ID strings are then packaged into JSON datasets to be sent to the server.

### BLE Tags

- **Active Tracking Beacons**: High-mobility, high-value assets (such as ventilators, infusion pumps, wheelchairs, and specialized beds) are assumed to carry standard, off-the-shelf **active BLE beacons** (costing $8 to $25 per tag).
- **Motion-Responsive Broadcasting**: To optimize battery life and mitigate the tag-maintenance overhead of dead batteries, tags are assumed to utilize built-in accelerometers. They run a dual-state advertising interval: transmitting at a low-frequency long-sleep interval (every 10–30 seconds) when stationary, and automatically triggering high-frequency 1-second pings when motion is detected.
- **Battery Lifecycle**: The system assumes the use of industrial-grade enclosures such as 5-Year Tags (powered by 2x AAA lithium batteries) or 10-Year Tags (powered by 2x AA batteries) rather than low-end consumer tags.
- **Passive & Paper-Thin Alternatives**: Low-mobility, low-cost assets (such as surgical trays, therapy kits, and linens) are assumed to carry passive **RFID stickers** (costing $0.10 to $2 each) or high-contrast, waterproof **QR codes** instead of battery-powered beacons.

### BLE Receivers / Gateways (Ceiling Nodes)

- **Hybrid Receiver Grid**: The system assumes the presence of a decentralized, low-cost receiver grid. This consists of compact, battery-powered or ceiling-mounted **ESP32 microcontrollers functioning as BLE proxies** (costing ~$4 per node).
- **Enterprise Integration**: These ESP32 proxies are deployed alongside the facility's existing enterprise Wi-Fi Access Points (e.g., Cisco Meraki, Aruba, or Juniper Mist) and utilize **Bermuda BLE integration** to capture signal packets.
- **Central Gateway Coordination**: The distributed proxies scan for beacon packets and forward the signal data to a centralized local **Raspberry Pi server** or a secure local cloud hosting the tracking backend.

---

## 2. Interface Assumptions

- **API Telemetry Transmission**: The software receives all hardware events via standard REST APIs (using Flask or FastAPI) or real-time protocols like MQTT or WebSockets.
- **Normalized Telemetry Payloads**:
    - **Wireless Feed**: The ESP32 proxy gateways transmit standardized JSON payloads containing the asset's Bluetooth MAC address/UUID, the receiving proxy's unique identifier, the Captured Signal Strength (RSSI), and phase-based signal measurements: `{"device_uuid": "Tag_042", "gateway_id": "AP_3", "rssi": -72}`.
    - **Visual Feed**: The Jetson edge camera nodes transmit JSON payloads containing the recognized asset category, the parsed alphanumeric serial ID, bounding-box parameters, and the camera's gateway ID: `{"camera_id": "CAM_West_04", "asset_type": "IV_Pump", "serial_id": "P-042", "timestamp": "2026-08-20T09:25:38Z"}`.
- **Clock Synchronization**: To support temporal data fusion (associating a visual camera crossing with a wireless BLE coordinate shift), all cameras, proxies, and servers are assumed to have synchronized system clocks (via NTP) operating in UTC.

---

## 3. Operational Assumptions

- **Continuous Telemetry Stream**: The hardware operates continuously in the background, passively logging location events and channel metrics without requiring manual intervention, barcodes, or active photo-taking by busy clinical nurses.
- **No Infrastructure Configuration by Software Team**: The software team is not responsible for setting up local servers, calibrating physical proxy positions, mapping floor plan CAD files, or wiring physical cameras.
- **Simulated Data Substitution**: For the prototype validation phase, all hardware network feeds are replaced by a **Simulated Data Generator**. This runner scripts historical, physical-layer radio databases (such as **TUJI1**, **UJIIndoorLoc**, **DSI**, or **SODIndoorLoc**) and loops through medicine-packaging visual datasets (like the **Ritsumeikan University Medicine Package Dataset**) to mimic live physical hardware.

---

## 4. Accuracy & Environment Assumptions

- **RF Signal Instability**: The physical hospital environment is highly complex and dynamic, presenting concrete walls, heavy metal surgical machinery, and elevator shafts that cause **multipath propagation and shadow fading**.
- **Zone and Room-Level Resolution**: Because standard RSSI signals fluctuate wildly, simple signal-strength tracking yields a coarse 5-to-10-meter error range. The software assumes it must use mathematical smoothing (such as **Weighted Centroid Localization (WCL)** combined with **XGBoost machine learning**) to filter noise and deliver stable room-level accuracy (resolving coordinates to 0.5m–0.8m in high-density areas).
- **Phase-Based Precision**: In zones where the COTS ESP32 proxies capture link-layer phase-based wave measurements (bypassing RSSI fluctuations), the positioning engine is assumed to calculate exact coordinates within a **12-centimeter trajectory error**.
- **Visual Occlusion Thresholds**: The software assumes that cameras will experience line-of-sight blockage (staff blocking views, sheets draped over wheelchairs). The vision processing pipeline must be robust enough (using a **BiFormer attention mechanism**) to successfully detect and count assets even when they are **up to 48% physically covered**.
- **Digital Map Degradation**: The software assumes a static physical floor plan during operation. If hospital wings undergo physical renovations or departments swap rooms, the digital coordinates will experience drift. The database must support CAD floor plan re-uploads to redefine coordinates and geofence lines.

---

## 5. Out of Scope (Hardware Responsibilities)

The software project strictly excludes the physical layer, meaning the team is **not responsible** for:

- Mounting, wiring, or supplying PoE power to the ESP32 proxies and edge-computing cameras.
- Configuring camera angles, adjusting focal lengths, or troubleshooting network packet routing.
- Proactively monitoring, swapping, or recycling depleted CR2032 or AAA lithium batteries on physical asset tags.
- Diagnosing component failures (such as a blown proxy microcontroller or a severed camera cable).

---

## 6. Impact on Software Design

Because the physical layer presents these real-world constraints, the software must be architected defensively:

- **Device Heterogeneity Tolerance**: Since different cheap tag brands and receiver chips record signal strengths differently, the localization engine must parse normalized data formats and use machine learning classifiers (like XGBoost) to "smooth out" hardware-induced signal drift.
- **Cross-Modal Verification**: The system must run a bidirectional verification loop. If a camera feed is physically blocked (occluded), the active BLE tag acts as a fallback to maintain room tracking. Conversely, if a BLE signal bounces off a metal elevator shaft and bleeds through a concrete wall, the hallway camera acts as a validation gate (verifying if the asset actually crossed the threshold).
- **Graceful Network Degradation**: If network connectivity drops mid-shift, the local NVIDIA Jetson edge nodes must cache recognized events locally and push them to the central server once the connection is restored, utilizing manual QR code scans as a fallback during active outages.

---

## Summary

This document defines the hardware boundaries for the Aura-Fusion IPS tracking architecture. By explicitly detailing how the edge-computing cameras, active BLE tags, and ESP32 proxy nodes behave physically, we ensure that our software core—including the localization algorithms, database schemas, and data fusion layers—is fully compatible with real-world clinical constraints.

---







#  4. Software Architecture: Aura-Fusion IPS

This document describes the software architecture of the Aura-Fusion IPS, an open-standards, multi-modal asset tracking and inventory management system. This architecture programmatically fuses lightweight, edge-based computer vision at hallway chokepoints with high-density, off-the-shelf wireless coordinate triangulation [107].

---

## 1. HIGH-LEVEL BLOCK DIAGRAM

The diagram below illustrates how raw telemetry flows from physical and simulated endpoints, through specialized processing pipelines, into the central **Aura-Fusion Engine** for cross-modal validation, and finally reaches client interfaces, alerting channels, and enterprise integration platforms.

```
+---------------------------------------------------------------------------------+
|                                SIMULATION LAYER                                 |
|  [UJIIndoorLoc / TUJI1 / DSI / SODIndoorLoc]   [Ritsumeikan Medicine Package]   |
|               (CSV Signal Player)                      (Image Folder Loop)      |
+------------------------------------+----------------------------+---------------+
                                     |                            |
                                     v                            v
+------------------------------------+---+    +-------------------+---------------+
|       WIRELESS SIGNAL PIPELINE         |    |            EDGE-VISION PIPELINE           |
|                                        |    |                                           |
|   +--------------------------------+   |    |   +-----------------------------------+   |
|   | Active BLE Beacons ($8-$25)    |   |    |   | Hallway Cameras (Existing)        |   |
|   +---------------+----------------+   |    |   +-----------------+-----------------+   |
|                   |                    |    |                     | (Video Feed)        |
|                   v (RF Signals)       |    |                     v                     |
|   +---------------+----------------+   |    |   +-----------------+-----------------+   |
|   | ESP32 Proxies / Bermuda BLE    |   |    |   | NVIDIA Jetson Nano/Orin Edge Node |   |
|   |  - Parses BLE, RSSI, Phase     |    |   |  - YOLO26 (Asset Category, STAL)  |   |
|   +---------------+----------------+   |    |  - YOLO-GF (Serial ID Scan, 130+ FPS) |   |
|                   |                    |    |   |  - CNN Display Reader (State)     |   |
|                   v (JSON: MAC, Proxy, |    |   +-----------------+-----------------+   |
|                      RSSI, Phase)      |    |                     |                     |
+-------------------+--------------------+    +---------------------+---------------------+
                    |                                               |
                    | (MQTT / WebSockets / HTTP POST)               | (HTTP POST / JSON Payload)
                    v                                               v
+-------------------+-----------------------------------------------+---------------------+
|                              AURA-FUSION SOFTWARE ENGINE                                |
|                                                                                         |
|   +---------------------------------------------------------------------------------+   |
|   |                           API DATA INGESTION LAYER                              |   |
|   |    - Ingests wireless telemetry (MAC, RSSI, Phase)                              |   |
|   |    - Ingests visual crossing logs (Camera ID, Serial ID, Class, Telemetry)      |   |
|   +---------------------------------------+-----------------------------------------+   |
|                                           |                                             |
|                                           v                                             |
|   +---------------------------------------+-----------------------------------------+   |
|   |                          AURA-FUSION FUSION CORE                                |   |
|   |    - Runs Weighted Centroid Localization (WCL) & XGBoost noise filtering        |   |
|   |    - Executes Analytical Multilateration on link-layer phase wave metrics       |   |
|   |    - Cross-validates coordinates vs camera crossings (XGBoost Classifier)       |   |
|   |    - Simulates BiFormer self-attention for shelves (resolves 48% occlusion)     |   |
|   +---------------------------------------+-----------------------------------------+   |
|                                           |                                             |
|                                           v                                             |
|   +---------------------------------------+-----------------------------------------+   |
|   |                          CENTRAL SQL DATABASE SCHEMA                            |   |
|   |    - Stores unified real-time room-level location states                        |   |
|   |    - Maintains dynamic PAR-levels and geofence boundaries                        |   |
|   +---------------+-----------------------------------------------+-----------------+   |
|                   |                                               |                     |
+-------------------|-----------------------------------------------|---------------------+
                    |                                               |
                    v (REST APIs / WebSockets)                      v (Trigger Alerts)
+-------------------+--------------------+    +---------------------+---------------------+
|               CLIENT WORKFLOWS         |    |             AUTOMATED ACTION SYSTEM       |
|                                        |    |                                           |
|   +--------------------------------+   |    |   +-----------------------------------+   |
|   | Searchable Mobile Web App Map  |   |    |   | Automated Anti-Hoarding Alerts    |   |
|   |   - Displays asset room level  |   |    |   |   - Restock alerts (PAR < safe)   |   |
|   |   - Nurse search tool (<2 min) |   |    |   - Pushes to Slack / Teams webhooks  |   |
|   +--------------------------------+   |    |   +-----------------+-----------------+   |
|                                        |    |                     |                     |
|                                        |    |                     v (OpenAPI 3.1 REST)  |
|                                        |    |   +-----------------+-----------------+   |
|                                        |    |   | Oxmaint CMMS / EAM Platform       |   |
|                                        |    |   |   - Direct work order generated  |   |
|                                        |    |   +-----------------------------------+   |
+----------------------------------------+    +-------------------------------------------+
```

---

## 2. MAIN SOFTWARE MODULES

The system is composed of several discrete, highly optimized software modules that interact asynchronously [108, 109, 112].

### A. API Data Ingestion Layer
*   **Wireless Ingestion Sub-Module**: Exposes REST endpoints and WebSocket/MQTT brokers to ingest raw Bluetooth Low Energy packets broadcasted by mobile beacons ($8–$25 each) and relayed via distributed ceiling-mounted ESP32 proxy nodes ($4 each) [108, 110, 112]. The ingested payload contains the asset tag's UUID, the gateway receiver ID, the signal strength (RSSI), and phase-based link-layer metrics [110].
*   **Optical Ingestion Sub-Module**: Receives real-time visual events pushed from local NVIDIA Jetson edge nodes mounted throughout the hallways [108, 109]. It parses JSON event payloads containing identified asset categories, character-level serial IDs, and timestamp coordinates [109].

### B. Localization & Positioning Module
*   **Weighted Centroid Localization (WCL) Engine**: Resolves raw RSSI values using a weighted center-of-mass formula based on receiver geometry to establish zone-level position coordinate estimates [53, 110].
*   **Phase-Based Analytical Multilateration Engine**: Captures link-layer radio wave phase shifts on off-the-shelf receivers to calculate high-precision, sub-meter positioning coordinate metrics within a proven 12-centimeter trajectory error range [37, 110].
*   **XGBoost Signal Smoothing Filter**: Utilizes a pre-trained XGBoost machine learning model to filter out multi-path reflections and severe signal variations caused by thick concrete hospital walls, elevators, metal equipment, and hardware device heterogeneity [110, 66].

### C. Aura-Fusion Core (Cross-Modal Fusion Engine)
*   **Cross-Modal Verification Loop**: Implements a bidirectional validation matrix using an XGBoost classification model [110, 111]. It compares coordinate updates from the BLE positioning module against optical hallway camera crossings [115]. For example, if a signal-bleeding event shows an asset in Room B but the camera did not detect a doorway crossing from Room A, the fusion engine rejects the BLE update, suppressing room-bleeding errors [115].
*   **BiFormer Occlusion Estimator**: Implements a simulated BiFormer bi-level routing self-attention block that filters out surrounding visual noise on shelves and in storage rooms, successfully recognizing and counting medical inventory items even when they are up to 48% physically covered or obscured [52, 111].

### D. Interactive Mapping & User Dashboard
*   **Searchable Web-App Map**: Renders an interactive 2D layout of the hospital floor plan [112]. It supports live search queries (e.g., "wheelchair" or "ventilator") and highlights room-level asset locations in real-time [112].
*   **Asset Trajectory Playback Module**: Logs history vectors, allowing administrators to audit historical asset routes and monitor movement patterns across hospital departments [3].

### E. Inventory Control & Automated Workflows Engine
*   **PAR-Level Inventory Manager**: Continually tallies room-specific and ward-specific assets, cross-referencing counts against dynamic ward-specific PAR thresholds [112].
*   **Predictive Shortage Modeler**: Processes upcoming patient admission forecasts and active operating room schedules, calculating local equipment demand to forecast localized inventory shortages 24 to 48 hours in advance [112].
*   **Anti-Hoarding Alert Dispatcher**: Triggered when equipment levels violate PAR-levels or if excess devices are hoarded in a single closet [112]. It formats and dispatches immediate notification webhooks directly to Slack or Microsoft Teams channels, highlighting the exact coordinates of the hoarded equipment [112].

### F. OpenAPI Integration Layer
*   **Oxmaint CMMS Connector**: Formats outbound coordinate updates and triggers automated preventive maintenance work orders directed to the Oxmaint platform when equipment exceeds operational usage limits [112, 151]. All interfaces comply with the OpenAPI 3.1 specification [142, 151].

### G. Hardware Simulation & Playback Module
*   **CSV Signal Player**: A simulated database loop that reads rows of radio fingerprints sequentially from open positioning datasets (TUJI1, UJIIndoorLoc, DSI, or SODIndoorLoc) and posts them to the API Ingestion Layer [172].
*   **Visual Frame Emulator**: Iterates through image folders (e.g., the Ritsumeikan Medicine Package dataset) to mimic live, edge-processed camera streams [173].

---

## 3. DATA FLOW

Data moves sequentially through the system to ensure that raw physical-layer inputs are translated into reliable clinical actions:

1.  **Tag Advertising & Video Capture (Physical/Simulation Layer)**:
    *   *BLE Route*: Active tags on mobile assets broadcast BLE advertising frames at motion-responsive intervals (every 1 second when moving via accelerometer triggers, sleeping to 10–30 seconds when stationary) [111, 116]. Off-the-shelf ESP32 proxies capture these packets [108].
    *   *Vision Route*: Hallway cameras capture standard 1080p security video feeds [108, 154].
2.  **Edge Processing**:
    *   *BLE Route*: ESP32 microcontrollers run Bermuda BLE firmware to extract RSSI and phase-based link-layer wave metrics, packaging them into JSON frames [108, 110].
    *   *Vision Route*: Local wall-mounted NVIDIA Jetson edge processors execute a single-stage YOLO26 object detection network to classify asset types (e.g., "IV Pump") [108, 109]. A coupled YOLO-GF module instantly processes the image to read printed alphanumeric serial IDs at 130+ FPS [109]. Raw video is immediately discarded to preserve patient and clinician privacy, transmitting only the parsed text metadata and bounding-box coordinates [138, 173].
3.  **Data Transport**:
    *   Both pipelines transmit telemetry to the centralized local Raspberry Pi server via MQTT, WebSocket, or HTTP POST protocols [108, 112, 172].
4.  **Signal Conditioning & Raw Positioning**:
    *   The Localization Module processes BLE payloads [110]. If phase metrics exist, it runs analytical multilateration [110]. If RSSI is used, it runs Weighted Centroid Localization [110, 53]. Raw coordinates are smoothed using XGBoost models to filter out multipath reflections and resolve hardware heterogeneity [110, 66].
5.  **Multi-Modal Fusion Validation (Aura-Fusion Engine)**:
    *   The central engine runs the bidirectional cross-modal verification loop [111]. The coordinate estimate is compared with recent visual chokepoint crossings [115]. If they align, the position update is validated. If they conflict (e.g., showing a device inside a concrete-walled OR with no matching doorway crossing), the fusion engine resolves the room-bleeding error and logs the correct ward-level state [115].
6.  **Database Recording & State Evaluation**:
    *   The validated location coordinate, category, serial ID, and active status are logged into the central database.
    *   The Inventory Control Engine runs PAR-level comparisons [112].
7.  **Client Presentation & Alert Triggering**:
    *   The Web App UI pulls database records, updating the interactive mapping floor plan with live room-level markers [112].
    *   If a ward-level count falls below the PAR threshold, or if a device is flagged as hoarded, the Anti-Hoarding module triggers a web-request alert [112]. This pushes a notification to Slack/Teams with the exact room-level coordinate, and forwards an OpenAPI 3.1 work-order to Oxmaint to dispatch a transport technician [112, 151].

---

## 4. TECHNOLOGY STACK

The Aura-Fusion IPS technology stack leverages highly efficient, open-source libraries, lightweight neural networks, and standard networking protocols detailed across the project's source materials [108, 109, 110, 112].

### A. Edge-Vision Stack (Hardware & Models)
*   **NVIDIA Jetson Nano / Orin / AGX Orin**: High-efficiency, embedded hardware platforms for processing local hallway camera video streams [4, 108, 52].
*   **YOLO26 (YOLOv26)**: Single-stage object detection model utilizing Small-Target-Aware Label Assignment (STAL) and end-to-end NMS-free inference for edge-vision tasks [4, 109].
*   **YOLO-GF**: High-speed, lightweight OCR model used to read character-level asset ID stickers at over 130 FPS [109, 114].
*   **EfficientDet-BiFormer-ResNet-18**: Scale-adjusting network with bi-level routing self-attention and triplet-loss embedding space for classifying medical assets under up to 48% occlusion [52, 111].
*   **YOLOv8 & YOLOv12**: Lightweight computer vision architectures utilized for retrofitting displays and real-time medical item parsing [2, 23, 109].

### B. Wireless Signal Stack (Hardware & Firmware)
*   **ESP32 Microcontrollers**: Cheap ($4 each) microchips deployed as distributed ceiling-mounted Bluetooth proxies [108, 53].
*   **Bermuda BLE**: Open-source integration firmware used by the ESP32 proxies to scan, filter, and report BLE signal packets [108, 53].
*   **Home Assistant**: Open-source automation platform running on the Raspberry Pi server to coordinate raw receiver feeds [108, 53].
*   **Raspberry Pi Server**: Decentralized local server hosting the open-source Bermuda BLE positioning backend [108, 53].

### C. Backend & API Stack *(suggested, not explicitly in sources)*
*   **Python 3.12**: The primary system programming language, implied by the use of PyTorch, pandas, and XGBoost machine learning libraries [110, 172].
*   **FastAPI**: A high-performance, asynchronous Python web framework used to expose API endpoints under the OpenAPI 3.1 specification to handle concurrent HTTP POST data streams from Jetson and ESP32 nodes [142, 151, 172].
*   **PostgreSQL with PostGIS**: A robust SQL database system with geographical spatial extensions, highly suited for indexing real-time 2D physical floor coordinates and defining geofence polygonal boundaries.

### D. Frontend & Map Stack *(suggested, not explicitly in sources)*
*   **React.js**: A component-based JavaScript UI library used to build the responsive client mapping dashboard and administrative portal.
*   **Leaflet.js / Mapbox GL JS**: A lightweight interactive mapping library configured to render custom 2D SVG or raster CAD floor plans as geographic-like coordinate spaces for plotting room-level asset overlays.

### E. Communication Protocols & Webhooks
*   **MQTT (Eclipse Mosquitto)**: A lightweight, pub/sub messaging protocol optimized for streaming raw, high-frequency RSSI and phase-based packets from ESP32 nodes to the backend ingestion queue *(suggested, not explicitly in sources - implied by low-power IoT constraints)*.
*   **WebSockets**: Utilized for real-time, bi-directional coordinate pushes to active client web-app maps [112].
*   **Slack & Microsoft Teams Incoming Webhooks**: Used to instantly dispatch automated PAR-level restocking alerts and anti-hoarding notices to unit teams [112].
*   **OpenAPI 3.1**: The REST API specification standard used to document and secure communication gateways between Aura-Fusion and third-party systems like Oxmaint [142, 151].

### F. Datasets (Simulation & Validation)
*   **TUJI1 Multi-Device Dataset** (Zenodo, DOI: 10.1016/j.dib.2024.110356): High-density multi-device BLE signal database used to simulate radio fingerprints [170].
*   **UJIIndoorLoc / DSI / SODIndoorLoc**: Multi-floor Wi-Fi and Bluetooth databases used to simulate signal propagation across complex layouts [170].
*   **Ritsumeikan Medicine Package Dataset**: Optical dataset used to simulate image packages for verifying character recognition pipelines [171].



# 5. Functional Requirements

FR1: The system shall ingest real-time JSON payloads containing categorized asset detection events from edge-vision camera nodes [109].
FR2: The system shall ingest character-level asset serial ID strings parsed by the edge OCR pipeline [109].
FR3: The system shall ingest device telemetry and active screen errors extracted from simulated medical screen reader CNNs [109].
FR4: The system shall ingest Received Signal Strength Indicator (RSSI) measurements forwarded by BLE receiver proxies [110].
FR5: The system shall ingest physical phase-based signal measurements captured by COTS BLE gateway nodes [110].
FR6: The system shall calculate asset coordinate estimates using a Weighted Centroid Localization (WCL) algorithm [110].
FR7: The system shall apply an XGBoost machine learning model to smooth RSSI fluctuations and mitigate hardware device heterogeneity [110].
FR8: The system shall calculate physical tag coordinates using analytical multilateration when phase-based ranging metrics are available [110].
FR9: The system shall cross-validate calculated BLE coordinates against optical camera crossing events to filter out signal-bleeding room errors [111, 115].
FR10: The system shall run a BiFormer attention mechanism to identify and count assets on storage shelves that are physically occluded up to 48% [111].
FR11: The system shall display a live, searchable digital map of the facility floor plan in a web application interface [112].
FR12: The system shall highlight the real-time room-level location of an asset on the map when a user searches by its unique serial ID [112].
FR13: The system shall render trajectory location history playback for any selected asset [3, 45].
FR14: The system shall continuously track active asset inventory counts per ward, corridor, and clinical storage zone [112].
FR15: The system shall trigger an automated redistribution alert when a ward's active equipment count drops below its defined PAR-level threshold [112].
FR16: The system shall trigger a hoarding alert when an asset overstays in an unassigned storage zone or falls below utilization thresholds [112, 45].
FR17: The system shall dispatch generated alerts to external platforms using Slack or Microsoft Teams webhooks [112].
FR18: The system shall generate low-battery dashboard alerts when an active BLE tag's voltage falls below a critical threshold [116].
FR19: The system shall expose REST API endpoints that comply with the OpenAPI 3.1 specification to support external data integrations [112, 142].
FR20: The system shall automatically transmit maintenance work orders to a third-party CMMS platform (such as Oxmaint) when a PM interval is reached [112, 151].
FR21: The system shall provide a local data generator that streams simulated signal events from CSV datasets (e.g., TUJI1 or UJIIndoorLoc) to test the localization engine without physical hardware [172].
FR22: The system shall provide a local camera simulator that loops through image folders (e.g., Ritsumeikan Medicine Package Dataset) to test the edge-vision OCR pipeline [173].
