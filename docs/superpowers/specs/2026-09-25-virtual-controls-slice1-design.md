# Virtual Controls — Slice 1 Design: "Eyes Lead, Hands Follow"

- Date: 2026-09-25
- Status: approved (section-by-section review with user)
- Scope: first vertical slice of the Virtual Controls app

## 1. Summary

A Windows-only, Python desktop app that turns an ordinary webcam into a real
mouse: eye gaze provides coarse aim (a "soft magnet"), hand position provides
precision, pinch gestures click and drag. Ships with a click-through overlay
(gaze dot + uncertainty halo, hand cursor, debug HUD), a real 5-point
calibration wizard, a settings menu, and a kill-switch. All later modes
(virtual gamepad, touch, 3D control, gesture editor) plug into the same
signal path defined here.

Decisions locked with the user:
- Stack: Python (MediaPipe, PySide6, vgamepad-ready outputs)
- Platform: Windows only
- Backend: MediaPipe via plain webcam (DepthAI/OAK blobs = optional later accel)
- Architecture: single process, threaded pipeline (approach 1)
- UI: PySide6 frameless translucent overlay + menu panel
- Slice 1 interactions: cursor move + pinch click/drag (plus the additions in S4+)
- Testing: real trackers, real recordings, real SendInput — no fakes, no mocks

## 2. Architecture and data flow

```text
[camera thread: frame loop @ ~30fps]            [main thread: PySide6]
  Capture -+-> FaceLandmarker -> GazeEstimator -+     Overlay (gaze dot,
            +-> HandLandmarker -> HandEstimator +     hand cursor, HUD)
              |                            |          Calibration wizard
              |                            v                 |
              +-> PinchFSM --------> FusionEngine <----------+
                                    (1e filter, soft magnet)
                                           |
                                           v
                                 MouseOutput (Win32 SendInput)

config/config.json  <- settings, hotkeys, magnet/filter params, camera
config/calibration.json <- affine model + timestamp + resolution
config/gestures.json, config/profiles.json
logs/session.log
```

Modules (one file, one job, typed interface):

| Module | Responsibility |
|---|---|
| capture | webcam frames, resolution/FPS control, device selection |
| gaze | GazeEstimator: face landmarks -> screen point + confidence |
| hand | HandEstimator: 21 landmarks -> cursor point, pinch distance, confidence |
| fusion | 1e filter + soft-magnet merge of gaze and hand -> final cursor |
| gestures | PinchFSM -> click / down / up events; gesture registry |
| outputs.mouse | move cursor, buttons via Win32 SendInput |
| calibration | 5-point dwell wizard + affine model load/save |
| overlay | click-through PySide6 window: markers, HUD, wizard, menu |
| config | pydantic-validated JSON, atomic writes, profiles |

Threading contract: exactly one producer (frame loop) writes an immutable
FrameResult (gaze, hand, cursor, pinch state, confidences, timestamp) into a
single-slot holder; the UI thread reads the latest slot on each paint. No
growing queues, no shared mutable state.

Error handling: camera lost -> status pill + mouse output frozen (never
teleports); tracker confidence low -> fusion degrades to gaze-only or
hand-only; frame-loop exception -> logged with traceback, state reset,
loop continues; 5 crashes in 10 s -> graceful shutdown.

## 3. Gaze estimation and calibration

Estimator: MediaPipe Face Landmarker (478 landmarks, iris centers). Gaze
feature vector = iris center relative to eye corners (head-motion invariant)
plus a small head-pose term from nose/ear geometry. A per-user model maps
features to screen coordinates.

Model: 5-point dwell wizard (4 corners + center), 1.2 s dwell, ~15 samples
per point, least-squares affine fit (feature -> screen). A 2nd-order
polynomial option exists behind a config flag for visible off-axis curvature;
affine is the default (more parameters = more calibration noise without
proven gain at webcam resolution).

Honest accuracy target: webcam gaze lands in a region, not a pixel. Expect
approx. 3-6 degrees (60-150 px on 1080p) after 5-point calibration, worse at
screen edges. Acceptable because (a) gaze is a soft magnet / region
indicator, not the click target, (b) the hand cursor does precision work,
(c) the gaze dot renders an uncertainty halo sized from estimator confidence
so pixel accuracy is never promised.

Recalibration and drift: wizard re-runnable from menu; auto-prompt when
feature drift vs stored baseline exceeds threshold; model saved with
timestamp + screen resolution and invalidated automatically when resolution
changes.

Quality gates: a point is rejected if sample variance is too high ("you
looked away"), pass/fail shown live, leave-one-out residual displayed as
"expected accuracy: ~N px". Bad calibration is the top failure mode in eye
trackers; the UI must never silently accept it.

## 4. Fusion (soft magnet) and pinch gestures

1e filter (Casiez and Vogel, min_cutoff=1.0, beta=0.007, d_cutoff=1.0,
config-tunable) on gaze point, hand point, and final cursor.

Soft magnet fusion: hand pointing position comes from a hand-bbox-to-screen
homography (rough in slice 1; gaze carries aiming intent), then:

    cursor = hand_pos + magnet_gain * (gaze_pos - hand_pos) * falloff(dist)

falloff = 1 far from hand (gaze pulls hard, covers coarse travel), decays to
0 within precision_radius (near target the hand alone controls - no
fighting). Defaults: magnet_gain 0.65, precision_radius 120 px. Hand lost ->
cursor follows filtered gaze (halo grows). Gaze lost -> hand-only absolute
mode. Both visible in the debug HUD.

Pinch FSM (thumb tip vs index tip distance, normalized by hand size):

    IDLE --(dist < T_on for 3 frames)--> PRESSED -> SendInput left DOWN
    PRESSED --(dist > T_off for 3 frames)--> IDLE -> SendInput left UP

T_on < T_off (hysteresis) plus 3-frame debounce = no flicker. While PRESSED,
cursor motion drags. Tap (< 250 ms) = click, hold = drag. Watchdog forces
LEFTUP if state unknown > 500 ms or tracking lost - a button is never left
stuck.

Gesture registry: gestures are data, not code - {name, detector, params,
binding} entries in config/gestures.json. Slice 1 ships pinch -> left click
and index+middle pinch -> right click; later custom detectors (volume-knob
twist) are added through the editor without touching the engine.

## 5. Mouse output and overlay UI

Mouse output: Win32 SendInput, absolute coordinates (MOUSEEVENTF_MOVE |
ABSOLUTE | VIRTUALDESK, normalized 0-65535 over the virtual desktop so
multi-monitor works), buttons via LEFTDOWN/LEFTUP/RIGHTDOWN/RIGHTUP. Event-
driven: move only when the fused cursor moved > 0.5 px since last send;
button events immediate. Global kill-switch Ctrl+Alt+X (config) freezes all
injection instantly - checked before every SendInput.

Overlay: frameless, translucent, always-on-top PySide6 window over the
primary screen with WindowTransparentForInput | WindowDoesNotAcceptFocus
(click-through, never steals focus). Renders at UI rate from the latest
FrameResult slot:
- gaze dot + uncertainty halo (radius = 1/confidence)
- hand cursor ring; ring solidifies while PRESSED (visible dragging)
- status pill (debug): FPS, gaze conf, hand conf, active mode
- menu button (top-right hit area) opening the settings panel

Calibration wizard UI lives in the same overlay: dim full screen, bright
dwell dot, progress ring during dwell, per-point pass/fail, final accuracy
estimate, Save/Retry. Esc cancels, Space skips a point.

### 4+ Added functionality (approved)

Interactions:
- Right-click gesture: index+middle pinch (T-shape alternative in config)
- Scroll mode: open palm facing camera + vertical hand travel -> wheel
  events, speed proportional to travel; two-finger vertical drag alternate
- Precision squeeze: pinch tighter than T_hard -> magnet gain 0, filter
  tightens (micro-movements stable)
- Dwell-click toggle (default off): gaze resting > 700 ms clicks
- Double-tap = double click; tap timing configurable

Feedback:
- Pinch ripple on release, ring contraction on press, tick flash
- Cursor trail (debug): fading polyline of last ~20 fused positions
- Edge glow pulse near screen edges
- Optional soft tick sound (feedback.sound, default off)
- DRAG chip beside the cursor while dragging

Hotkeys (global, configurable): Ctrl+Alt+X kill-switch, Ctrl+Alt+D debug,
Ctrl+Alt+R recalibrate, Ctrl+Alt+M toggle markers, Ctrl+Alt+Space pause
tracking (camera released).

Menu panel: camera device picker + resolution/FPS, magnet gain, precision
radius, filter beta, dwell-click toggle, feedback sound, profile selector
(Desktop / Games / 3D - each stores output bindings + magnet params, cycled
by hotkey), FPS + latency readout, export/import config, open logs.

Status HUD (debug): 60-sample FPS sparkline, pipeline latency
(capture -> SendInput, ms), active profile, output mode.

## 6. Config, reliability, testing

Config: config/config.json, schema-versioned, pydantic-validated (unknown
keys warn, missing keys fill defaults - never crash on a hand-edited file).
Siblings: calibration.json, gestures.json, profiles.json. Menu writes are
atomic (temp file + rename). Every hotkey, threshold, filter param and
camera choice lives here; nothing hard-coded.

Reliability:
- Camera watchdog: no frame > 1.5 s -> release and auto-reopen (3 tries),
  status pill "camera lost", mouse injection frozen (never stale coords)
- Stuck-button guard: forced LEFTUP/RIGHTUP on tracking loss, pause,
  kill-switch, and app exit (atexit hook)
- Kill-switch precedence: checked before every SendInput
- Frame-loop exceptions: catch, log traceback to logs/session.log, reset
  tracker state, continue; 5 crashes within 10 s -> graceful shutdown
- Cleanup: MediaPipe graphs and camera released on quit; overlay close exits

### Testing - real trackers, real recordings, real SendInput (no fakes, no mocks)

Test corpus = real recordings: --record captures real webcam sessions to
.npz (frames, landmarks exactly as MediaPipe produced them, fusion outputs,
timestamps, screen geometry). Checked into fixtures/real-sessions/ covering:
clean run, hand lost, gaze lost, rapid pinch, head turned, low light. Every
new bug gets a recorded session added first, then the fix.

Tier 1 - unit (pure logic, real parameters): 1e filter, affine fit + LOO
residual, soft-magnet falloff, pinch FSM hysteresis, config validation,
multi-monitor normalization. Inputs are numeric values taken from recorded
sessions; expected outputs captured from a known-good run. No camera needed,
runs on every commit.

Tier 2 - replay (real MediaPipe, real pipeline): --replay runs the actual
Face/Hand Landmarkers over recorded frames through the actual fusion,
gesture and output pipeline; assertions compare against what the recording
shows should happen (click at frame N, cursor path within tolerance),
verified via real Win32 state.

Tier 3 - live integration (real webcam, real mouse): opt-in pytest -m live.
Opens the real camera; scripted real actions (calibrate on the real wizard,
real pinch); verifies through real OS queries - GetCursorPos matches the
fused cursor within tolerance, GetAsyncKeyState shows the left button
genuinely down during a real drag, kill-switch genuinely stops injection,
camera unplug genuinely freezes output. Run before every milestone.

Manual checklist (docs/manual-test.md): calibration accuracy gate, drag a
real window, unplug camera mid-drag, multi-monitor, 10-minute soak for FPS
and memory.

### Packaging and DX

Dev: python -m vctrl. Ship: pyinstaller --windowed single exe (no relative
path assumptions; resources via importlib.resources). requirements.txt
pinned, ruff lint/format. Perf target: frame loop >= 25 fps at 640x480 on
integrated GPU; per-frame MediaPipe latency shown in HUD.

## 7. Out of scope for slice 1

Virtual gamepad (vgamepad/ViGEm), virtual touch mode, 3D object control
(Blender/Maya), full gesture editor UI, OAK/DepthAI backend, dwell-click
accessibility profiles beyond the toggle, packaging/signing, tray icon,
multi-language. These are enabled by the interfaces defined here (OutputSink,
Gesture registry, Tracker) but are separate specs.

## 8. Acceptance criteria

1. Fresh install -> menu -> 5-point wizard completes and reports expected
   accuracy; config files created.
2. With one hand visible, cursor follows fused position on the real desktop;
   gaze dot + halo and hand ring render in the overlay.
3. Real pinch clicks (verified by GetAsyncKeyState), pinch-hold drags a real
   window, release drops it; right-pinch right-clicks.
4. Kill-switch mid-drag instantly stops injection and releases buttons.
5. Hand leaves frame -> gaze-only mode with grown halo; returns -> fusion.
6. Camera unplugged -> output frozen, pill shows camera lost, no teleport.
7. Tier 1 + Tier 2 pass; Tier 3 run and documented.
8. Frame loop >= 25 fps at 640x480 on integrated GPU.

## 9. Open questions (deferred, non-blocking)

- ViGEm bus maintenance status for the future gamepad slice (research TODO).
- Exact WebGazer license if web-based fallback is ever considered.
- Whether the second-order polynomial calibration is worth exposing per
  profile (decide after real accuracy numbers from Tier 3).
