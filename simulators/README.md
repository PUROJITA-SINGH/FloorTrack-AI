# Demo simulators

The scenario definitions in `scenarios/definitions.json` are the single source
for scenario inputs and expected outputs. Each run resolves current demo IDs
with `GET /api/v1/simulator/topology`, posts positive sensor/demand events only
to public API endpoints, and checks its result against the recorded expectation.
No simulator opens the database or calls the operational-status endpoint.

Start the API first, then run a scenario:

```powershell
python simulators\run_scenario.py --scenario agreement
```

Run any of the eleven recorded scenarios by using its name:

```text
normal_movement
agreement
camera_occlusion
ble_signal_bleeding
ble_tag_failure
unknown_asset
stale_gateway
shortage_surge
excess_inventory
camera_silent
status_never_confirmed
```

Use `--delay 1` to pause between events in a multi-event scenario, or
`--base-url http://localhost:8001` to target a different local API address.
Each run prints both the expected and actual JSON output and exits non-zero
when they differ.

Scenarios do not fabricate negative sensor events. `camera_occlusion`,
`ble_tag_failure`, and `camera_silent` model missing sensor inputs by sending no
event for that source. `status_never_confirmed` deliberately sends no status
write. `shortage_surge` uses the public forecast endpoint to determine the
remaining demand needed to reach the JSON-defined target, so it is repeatable.

`camera/simulator.py`, `ble/simulator.py`, and `heartbeat/simulator.py` are
independent API clients. The orchestrator runs only the components enabled for
the selected scenario and performs fusion/forecast/recommendation checks over
HTTP.
