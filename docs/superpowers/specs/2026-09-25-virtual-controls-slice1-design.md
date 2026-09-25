# Virtual Controls - Slice 1 Design (rev 2): Eyes Lead, Hands Follow

- Date: 2026-09-25 (rev 2: user review requested comprehensive menu/debug,
  common keyboard+mouse keybinds, touch and 3D-space movement, intuitive
  calibration, unified movement-translation system for gamepad + mouse +
  keyboard, more robust eye/hand tracking)
- Status: pending approval of rev 2
- Scope: first release of the Virtual Controls app, designed so every
  output family and the full control surface ship as one coherent system

## 1. Summary

A Windows-only, Python desktop app that turns an ordinary webcam into a
universal input device: eyes aim (soft magnet), hands steer and click, and a
single translation layer converts captured movement into whichever output
the user chose - real mouse cursor, keyboard keys and shortcuts, virtual
gamepad (ViGEm), virtual touch, or 6-DOF movement for 3D applications.

Everything the user controls lives in one shell: a full settings menu
(8 tabs), a deep debug system, a gesture library with remappable bindings,
and an intuitive guided calibration.

Locked decisions (unchanged): Python, Windows-only, MediaPipe webcam
backend, single-process threaded pipeline, PySide6 overlay shell.
Expanded decisions (rev 2):
- Unified Signal -> Virtual Action -> Backend translation layer (section 2)
- Mouse + keyboard shortcuts first-class from day one (chords, key wheel)
- Gamepad (vgamepad/ViGEm), touch, and 3D transform share the same layer
- Full 8-tab menu and full debug inspector are slice-1 deliverables
- Calibration: guided posture + quick5/precise9/progressive modes
- Tracking: confidence gating, outlier rejection, ROI, per-eye gaze
- Testing stays real-only: real recordings, real MediaPipe, real SendInput

## 2. The translation system (core of the design)

Captured movement is never wired directly to an output. It flows through
three decoupled stages so any input can drive any output:

```text
 SIGNALS                VIRTUAL ACTIONS           OUTPUT BACKENDS
 (tracking)             (semantic, backend-free)  (Windows injection)
 gaze pt + conf   -+                               -> outputs.mouse
 hand landmarks   -+   cursor.move                -> outputs.keyboard
 pinch distance   -+->  button.click/down/up  ----> outputs.gamepad
 gesture events   -+   key.chord / key.tap        -> outputs.touch
 dwell events     -+   wheel.delta                 -> outputs.transform
 hand velocity    -+   axis.set(stick, x, y)
 zone enter/exit  -+   trigger.set(id, v)
                      contact.down/move/up
                      transform.set(pos, rot, zoom)
```

Binding engine: every signal source is described by a Binding record in
config/bindings.json:

    { "source": "gesture:index_pinch", "mode": "desktop",
      "map": "button.left", "params": {"on_frames":3, "tap_ms":250} }
    { "source": "continuous:hand_xy", "mode": "gamepad",
      "map": "axis.left_stick", "params": {"deadzone":0.12,
      "curve":"expo","sensitivity":1.4, "anchor":"neutral_box"} }

Rules:
- Sources: continuous signals (gaze_xy, hand_xy, hand_z, pinch_strength,
  hand_roll, velocity), discrete events (gestures, zone enter/exit, dwell),
  and chords (hold + tap combinations).
- Actions are semantic and output-agnostic; the mapping table decides what
  they mean per MODE (Desktop / Games / Touch / 3D), and profiles select
  modes. Switching profile re-points the whole graph atomically.
- Mapping params per record: curve (linear/expo/log), sensitivity,
  deadzone, invert, axis range, hysteresis, rate limit, easing.
- Gesture detectors are plugins registered in one registry:
  {name, extract(features)->bool/score, params, cooldown_ms}.
  New gestures = new config entries or one small detector function.
  No gesture hard-codes an output; it only emits an action.
- A Mapping Inspector (in the Debug tab) shows, live, which source fired,
  which action was emitted, which backend received it, and its params.

## 3. Default binding sets (the "common shortcuts" ship list)

### 3.1 Desktop mode (mouse + keyboard)
Continuous:
- gaze_xy (with hand present) -> cursor.move via soft-magnet fusion
- gaze_xy (hand lost) -> cursor.move direct, halo shows uncertainty
- hand_xy (gaze lost) -> cursor.move absolute hand map
- pinch_strength > T_hard -> cursor precision mode (gain 0, filter tight)
Discrete / gestures:
- index pinch -> button.left click / drag (FSM, hysteresis)
- index+middle pinch -> button.right
- open palm + vertical travel -> wheel.delta (speed ~ travel velocity)
- two-finger vertical drag -> wheel.delta (alternate)
- point (index only) + dwell 700ms -> dwell click (toggleable)
- double tap (< tap_ms apart) -> double click
Key chords (gesture -> shortcut, all remappable):
- pinch-hold 600ms then index tap -> KEY WHEEL opens (radial palette)
- fist (closed 300ms) -> Enter            - T-shape -> Escape
- wave left/right -> Alt+Left/Right (browser back/fwd)
- palm facing camera (hold) -> Ctrl hold (modifier latch, release on open)
- two-finger pinch -> Tab
Key wheel (radial, hold to open, aim + pinch to select):
  Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+Z, Ctrl+Y, Ctrl+S, Ctrl+A,
  Alt+Tab, Alt+F4, Space, Enter, Esc, Tab, arrows U/D/L/R,
  Win, Win+D, volume up/down/mute, play/pause
Every chord and wheel slot is editable in Gestures tab; custom chords are
raw key combinations ("Ctrl+Shift+P") parsed by the keyboard backend.

### 3.2 Games mode (virtual gamepad - vgamepad / ViGEm X360 + DS4)
- axis.left_stick  <- hand_xy inside neutral box (deadzone, expo curve)
- axis.right_stick <- gaze offset from screen center (deadzone, expo)
- trigger.left     <- pinch_strength on left-hand pinch (if 2 hands: L/R)
  single-hand default: trigger.left <- slow pinch press, A/B via gestures
- button.A <- index pinch, button.B <- index+middle pinch,
  button.X <- two-finger pinch, button.Y <- T-shape
- button.LB/RB <- palm-tap left/right (quick lateral hand tap)
- start <- fist hold, back <- T-shape hold
- dead zones, curves, inversion, axis swap all per-binding in Gestures tab
- rumble passthrough (if backend supports) -> optional audio tick
- output rate 60 Hz with latest-value sampling (no queue)

### 3.3 Touch mode (Windows touch injection)
- contact.1 down <- index pinch, move <- hand_xy, up <- pinch release
- contact.2 down <- index+middle pinch on second hand, or two-finger spread
- pinch travel = drag; quick pinch = tap; slow pinch hold = long-press
- palm open -> touch cancel; dwell toggle works for tap-to-click
- works in Windows Ink / tablets / any touch app; mouse backend stays
  selectable per-profile so Desktop and Touch can coexist (mouse fallback
  if the target app lacks touch support)

### 3.4 3D mode (Blender / Maya / any DCC)
- transform.set consumes hand pose:
  x,y <- hand_xy (normalized -1..1), z <- hand size change (approach/retreat,
  median-of-5 smoothed), rotation <- hand roll + pitch (wrist orientation),
  grab <- fist hold, zoom <- two-hand distance (pull apart), orbit <- palm
  swipe arcs
- backends (config-selectable):
  a) mouse-look emulation: buttons + relative motion (works everywhere)
  b) companion bridge: tiny TCP/OSC server + add-on scripts for Blender and
     Maya that map transform.set to object translate/rotate/scale, camera
     orbit, and keyframe insert (one-shot "K" via key.chord action)
- 3D gestures are modes, not one-shots: sticky mode chip in overlay shows
  GRAB / ROTATE / ORBIT until changed; leaving 3D profile restores Desktop

### 3.5 Profiles
Each profile = {mode set, binding table, magnet/filter params, cursor
style, output backend priority}. Ships: Desktop (default), Games, Touch,
3D. Cycled by Ctrl+Alt+P or the menu. Per-app auto-profile (like
AntiMicroX) uses foreground window matching rules stored in profiles.json;
editor for rules lives in Output tab.

## 4. Architecture and data flow

```text
[camera thread: frame loop @ ~30fps]           [main thread: PySide6]
  Capture -+-> FaceLandmarker  -> GazeEstimator -+   Overlay (gaze dot,
            +-> HandLandmarker  -> HandEstimator +   hand cursor, HUD,
                    |                     |          mode chip, wizard)
                    v                     v                 |
              FeatureFrame (landmarks, confidences, ts)     |
                    |                                       |
                    v                                       |
        TrackerCore: gating -> outlier rejection -> EMA/1e  |
                    |                                       |
                    +-> GestureEngine (registry, FSMs)      |
                    +-> FusionEngine (soft magnet)          |
                    |                                       |
                    v                                       v
              ActionBus (virtual actions, mode-aware) <-----+
                    |
                    v
        BindingEngine (bindings.json: source->action+params)
                    |
                    v
        OutputDispatcher -+-> outputs.mouse      (SendInput abs)
                          +-> outputs.keyboard   (SendInput VK)
                          +-> outputs.gamepad    (vgamepad, 60 Hz)
                          +-> outputs.touch      (touch injection)
                          +-> outputs.transform  (mouse-look / TCP bridge)

config/config.json | bindings.json | calibration.json | gestures.json
| profiles.json        logs/session.log        fixtures/real-sessions/*.npz
```

Modules (one file, one job, typed interfaces):

| Module | Responsibility |
|---|---|
| capture | webcam frames, device/res/FPS, mirror, ROI crop |
| gaze | GazeEstimator: face+iris landmarks -> screen point + conf |
| hand | HandEstimator: 21 landmarks -> pose, pinch dist, roll, depth |
| tracker | confidence gating, outlier rejection, EMA/1e filters, ROI |
| fusion | soft-magnet merge of gaze + hand -> cursor position |
| gestures | gesture registry + pinch/dwell/wave FSMs -> events |
| actions | ActionBus: typed virtual actions, mode-scoped |
| bindings | BindingEngine: source -> action mapping, curves, deadzones |
| outputs.* | mouse / keyboard / gamepad / touch / transform backends |
| calibration | quick5 / precise9 / progressive wizard + model persistence |
| overlay | click-through PySide6: markers, HUD, chips, wizard, menu |
| debug | inspector: signals graph, mapping inspector, recorder, logs |
| config | pydantic schemas for all JSON files, atomic writes, profiles |

Threading contract: exactly one producer (frame loop) writes an immutable
FrameResult {signals, gestures, actions fired, confidences, t} into a
single-slot holder; UI thread reads the latest slot each paint. Output
Dispatcher runs on the frame thread for mouse/touch (event-driven) and a
60 Hz sampler thread for gamepad (latest-value). No growing queues, no
shared mutable state; all cross-thread messages via Qt signals.

Error handling: camera lost -> status pill + outputs frozen (never
teleports); low confidence -> degrade per-signal (gaze-only, hand-only,
neither -> freeze + pill); frame-loop exception -> logged, tracker state
reset, loop continues; 5 crashes in 10 s -> graceful shutdown with all
buttons/keys released.

## 5. Tracking robustness (eyes + hands)

All of the following are slice-1 requirements, each individually toggleable
in the Tracking tab with live before/after in the debug overlay:

Gaze:
- Per-eye landmark models (left/right separate), combined by
  confidence-weighted mean; monocular fallback if one eye is occluded
  (glasses glare, side pose) with conf penalty shown in HUD
- Feature vector: iris center relative to eye corners + head-pose term
  (nose-ear geometry) to cancel small head motion
- Per-sample variance gate: a sample beyond k*sigma of the running window
  is dropped (blinks, lookaway) - not fed to fusion
- Velocity clamp: implausible gaze jumps ( > screen diag in 1 frame) are
  rejected instead of teleporting the halo
- Model: least-squares affine default; 2nd-order polynomial behind a
  config flag for visible off-axis curvature
- Honest accuracy: 3-6 deg (60-150 px @1080p) after 5-point calibration,
  rendered as an uncertainty halo (radius = f(1/conf)) - never pixel-precise

Hand:
- Palm-size EMA for normalization (pinch distance, bbox map) so approach
  toward camera does not inflate gestures
- Outlier rejection: median-of-3 on landmark coords; spike filter via
  velocity clamp on cursor source points
- Conf gating: below conf_min -> hand considered lost (fusion switches),
  never a half-detected hand steering the cursor
- ROI tracking: after first acquire, crop to hand ROI (+ margin) for
  MediaPipe - higher FPS and fewer false detections; re-acquire full frame
  every N frames or on loss
- Mirror/flip options in config (webcam natural mirror vs true coords)
- Multi-hand: primary = highest-confidence tracked; second hand only for
  declared two-hand gestures (zoom, two-finger); extras ignored

Fusion + smoothing:
- 1e filter (Casiez/Vogel; min_cutoff 1.0, beta 0.007, d_cutoff 1.0;
  per-signal tunables) on gaze point, hand point, final cursor
- Soft magnet: cursor = hand + gain*(gaze-hand)*falloff(|gaze-hand|)
  falloff = 1 far, decays to 0 inside precision_radius (default gain 0.65,
  radius 120 px); hand lost -> gaze-only (halo grows); gaze lost -> hand
  only; both lost -> freeze + pill
- Frame policy: drop stale frames (process only latest), never queue up

## 6. Calibration (more intuitive)

Guided start (every calibration, not just first run):
- Mirror live preview behind a face oval + distance meter (too close /
  good / too far), head-box guide, "hold still" cue, exposure/skin hint
- Calibrate button always visible; Ctrl+Alt+R anywhere; re-run keeps old
  model until the new one passes (safe fallback)

Three modes (Calibration tab picks the default, wizard offers a switch):
1. quick5 - 4 corners + center, 1.2 s dwell, ~15 samples/point (default)
2. precise9 - 9 points incl. mid-edges, same dwell; recommended when the
   wizard reports high edge residual
3. progressive - calibrate while working: samples natural look-at
   corrections the user makes over ~30 s of normal use, fits incrementally
   (best for re-calibration without the ritual; seeded by a 3-point start)

Quality-first UX:
- Live per-point pass/fail: sample variance gate rejects "you looked
  away" and asks to retry that point; progress ring during dwell
- After fit: leave-one-out residual shown as "expected accuracy ~N px",
  residual bar per screen region, edge-warning if corners are worse than
  2x center; Save / Retry / Save anyway (warned)
- Auto-recalibrate prompt when feature drift vs stored baseline exceeds
  threshold (config); model stored with timestamp + resolution, invalidated
  on resolution change; per-profile calibration offsets supported
- Monocular check: wizard records per-eye residuals and flags a weak eye

## 7. Gesture library (ships with these; all remappable)

| Gesture | Detector | Default binding |
|---|---|---|
| index pinch | thumb-index dist < T_on, 3-frame deb, hysteresis | left click / drag |
| index+middle pinch | thumb touches both tips | right click |
| two-finger pinch | thumb-middle dist | Tab / button.X |
| precision squeeze | pinch < T_hard | precision mode (gain 0) |
| point (index only) | index ext, others curled | contact source / dwell-click |
| open palm | all ext, palm flat | cancel / modifier latch |
| fist | all curled, 300 ms hold | Enter / gamepad start |
| T-shape | index+thumb out, rest curled | Escape / back |
| wave L/R | wrist x oscillation, 2 swings | Alt+Left/Right |
| palm-tap L/R | quick lateral hand tap | LB/RB |
| vertical travel | open palm, dy/dt > thresh | wheel |
| two-hand spread | two hands, dist grows | zoom (3D) |
| hand roll | wrist orientation | rotate (3D) |
| grab hold | fist + move | transform grab (3D) |
| dwell | gaze stationary 700 ms | dwell click (off by default) |
| pinch-hold + tap | chord | open key wheel |

Detector contract: extract(features, history) -> score in [0,1]; engine
emits event when score > on_th for on_frames, clears at off_th < on_th
(hysteresis), plus per-gesture cooldown_ms. Thresholds and debounce live in
gestures.json. The Gestures tab has a live tester: perform a gesture, see
its score, and bind it without touching JSON. Custom gestures beyond the
library = optional one-file detectors (Python) discovered from a
user-detectors/ folder; the volume-knob twist is the first example
(wrist roll rate over threshold).

## 8. Menu (8 tabs, complete control surface)

Shell: settings window (open from overlay button or Ctrl+Alt+Comma),
separate from the click-through overlay; persists across profile switches.

1. Output - backend priority per profile; mouse (speed, accel off,
   button swap); keyboard (key wheel slots editor, chord list, key
   repeat); gamepad (device type X360/DS4, deadzones, curves, invert,
   axis swap, rumble toggle); touch (sensitivity, long-press time);
   3D backend picker (mouse-look vs Blender/Maya bridge + bridge status);
   per-app auto-profile rules editor (match by process name/title regex)
2. Gestures - full library table (enable, score threshold, params),
   live gesture tester with score bar, binding editor per gesture
   (source -> action dropdown + params), add/remove custom bindings,
   import/export gesture sets
3. Eye - model type (affine/poly), per-eye enable, halo style + scale,
   dwell-click on/off + duration, accuracy readout, re-run calibration,
   drift prompt threshold
4. Calibration - mode picker (quick5/precise9/progressive), posture
   guide toggle, live quality meter, residual report history, per-profile
   offset trim (nudge gaze up/down/left/right without full recalibration)
5. Tracking - camera device/res/FPS/mirror, ROI toggle, conf gates
   (gaze/hand min), smoothing (1e params per signal, magnet gain,
   precision radius), feature switches (velocity clamp, outlier filter,
   blink gate) with live before/after overlay
6. Debug - see section 9
7. Profiles - create/duplicate/rename/delete, bind hotkey to cycle,
   active profile indicator, export/import all config, open config
   folder, open logs folder, reset-to-defaults (typed confirmation)
8. Help - first-run walkthrough, gesture cheat-sheet overlay (Ctrl+Alt+H),
   version info, links (ViGEm runtime install if gamepad missing, camera
   permission help, sources page), diagnostics bundle export (zip: configs
   + logs + last recording)

Hotkeys (global, remappable in Output tab):
Ctrl+Alt+X kill-switch, D debug, R recalibrate, M markers toggle,
P profile cycle, Space pause tracking (camera released), Comma menu,
H cheat-sheet.

## 9. Debug system (deep, always available)

Overlay debug layer (Ctrl+Alt+D):
- gaze dot + uncertainty halo; hand skeleton; pinch distance arc with
  T_on/T_off lines; neutral box + stick deadzone visual (Games mode);
  zones/latches highlighted; cursor trail (fading last ~20 points);
  edge glow near screen bounds; DRAG / GRAB / precision chips; pinch
  ripple feedback; status pill: FPS sparkline (60 samples), pipeline
  latency (capture -> injection, ms), gaze/hand conf bars, active mode

Inspector window (Debug tab):
- Live signal charts: gaze xy, hand xy, pinch dist, confidences, filtered
  vs raw (toggle per channel), 10 s window
- Mapping inspector: event stream "source -> action -> backend -> params"
  (click an entry to jump to its binding)
- Gesture scores: all enabled detectors with bars, firing history
- Output monitor: last mouse pos sent, key chord sent, gamepad state
  (buttons/triggers/sticks grid), touch contacts, transform values
- Recorder: start/stop capture to fixtures/real-sessions/*.npz, replay
  controls (play/pause/step) with --replay engine, jump-to-timestamp
- Calibration analyzer: load a recording, show fit residuals + map
- Log console: tail logs/session.log with level filter (INFO/DEBUG), one
  click "export diagnostics bundle"
- Kill-test panel: buttons to trigger each safety path manually (freeze
  outputs, force-release, camera restart) to verify guards work

## 10. Output backends (implementation notes)

outputs.mouse: SendInput MOUSEEVENTF_MOVE|ABSOLUTE|VIRTUALDESK; normalize
screen coords to 0-65535 across the virtual desktop (multi-monitor);
skip sub-0.5px deltas; buttons via LEFTDOWN/UP etc.; wheel via WHEEL with
round(120 * delta) units; force-release helper called from watchdog.
outputs.keyboard: VK codes + SHIFT/CTRL/ALT/WIN modifiers; SendInput
keydown/keyup sequences; chord parser "Ctrl+Shift+P" -> modifier set;
key wheel = same engine; OS-level rate limit respected (no 100% spam).
outputs.gamepad: vgamepad (ViGEm runtime required - Help tab detects and
links installer); X360 default, DS4 optional; 60 Hz sampler writes latest
axis/trigger/button state; deadzone+curve math shared util with mouse
gain; graceful no-op + warning if ViGEm bus missing.
outputs.touch: Windows touch injection (SendInput touch events or the
touch API wrapper); pointerId 1 and 2 for multi-touch; fallback to mouse
click-and-drag when target rejects touch (per-profile flag).
outputs.transform: abstract set(pos,rot,grab,zoom) -> backend
(a) relative mouse-look emulation: mode chip GRAB/ROTATE maps buttons+delta
(b) TCP bridge (localhost, JSON lines) + companion add-ons:
    Blender: python socket add-on -> translate/rotate/scale/orbit/zoom,
    Maya: python command plug-in equivalent; both on GitHub releases page
    later, bridge protocol documented in docs/bridge.md

## 11. Config and profiles

All JSON, pydantic-validated, schema_version field, atomic write
(temp+rename), corrupt file -> defaults + rename .bak + log warning:
- config/config.json - app settings (all Tracking/Output/Debug knobs,
  hotkeys, calibration mode, defaults)
- config/bindings.json - full source->action tables per mode
- config/gestures.json - detector thresholds, cooldowns, enables
- config/calibration.json - model coeffs, per-point residuals, timestamp,
  resolution, per-profile offsets (invalidated on resolution change)
- config/profiles.json - profiles (mode sets + overrides) + auto-profile
  window rules
Export/import = single zip of all five (Help tab); reset = typed confirm.

## 12. Reliability

- Camera watchdog: no frame 1.5 s -> close, reopen, cycle device if
  configured; max 3 attempts then camera-lost pill
- Stuck-input guard: force button/key/touch release on (a) tracking loss
  > 0.5 s while PRESSED, (b) pause/kill/profile switch, (c) app exit
  (atexit), (d) crash path (wrap dispatcher, release before re-raise)
- Crash isolation: frame-loop and dispatcher exceptions logged + state
  reset; 5 crashes / 10 s -> release all outputs, exit cleanly
- Kill-switch Ctrl+Alt+X processed on a dedicated low-level keyboard
  hook thread (works even if UI thread is busy), releases everything
- Disk: logs/session.log rotated (1 MB x 3); recorder enforces free-space
  check before writing .npz

## 13. Testing (real data only - no fakes, no mocks, anywhere)

Corpus: fixtures/real-sessions/*.npz recorded by the app's own recorder
(real camera frames + real MediaPipe landmarks + fusion outputs +
timestamps + screen geometry). Scenarios: clean session, hand lost,
gaze lost, rapid pinch, head turned, low light, two-hand. Recorded once
by us on real hardware, then replayed everywhere.

- Tier 1 unit (pure math): affine fit, 1e filter, magnet falloff, pinch
  FSM hysteresis/debounce, outlier rejection, key chord parser, deadzone/
  curves - inputs sampled from corpus .npz recordings
- Tier 2 replay (integration, CI-able): replay engine feeds recorded
  frames through REAL MediaPipe + full pipeline; assert golden outputs
  (cursor path within tolerance, click events, action stream) and verify
  REAL Win32 state via GetCursorPos/GetAsyncKeyState probes
- Tier 3 live (pytest -m live, opt-in): real webcam, real gestures,
  real SendInput; assertions via GetCursorPos / GetAsyncKeyState /
  vgamepad state readback; runs on dev machine only
- Manual checklist docs/manual-test.md: calibration gate (expected-px vs
  measured crosshair), drag a real window end-to-end, unplug camera
  mid-drag (forces release, no stuck buttons), multi-monitor absolute
  coords, profile switch under load, 10-minute soak with 0 stuck inputs,
  key wheel against a real editor (Ctrl+C/V in Notepad), gamepad in a
  real game/Windows Game Controller panel, touch against a real app
- Gates: Tier 1+2 green required before every push to main; Tier 3 +
  manual before tagging a release; target >= 25 fps @640x480 sustained,
  capture->output latency < 50 ms p95 (measured by debug latency meter)

## 14. Packaging

Dev: python -m vctrl (uses repo env; uv/pip with pinned pyproject).
Ship (post-slice-1, designed now): pyinstaller one-file, tray icon,
first-run wizard + Help links (ViGEm runtime), ruff clean, Python 3.12.

## 15. Out of scope (slice 1)

- macOS/Linux (Windows only, per decision), mobile/web
- OAK-D / depthai acceleration (blobs vendored; feature-flag later)
- PS5/DualSense beyond DS4 emulation; Xbox adapter hardware
- Training-data collection / user-data telemetry (diagnostics bundle is
  local zip, user-initiated only)
- Full Maya/Blender add-on polish (bridge ships as minimal working
  version), Unreal/Unity integrations
- ML gesture training pipeline (library detectors only; custom detectors
  are hand-written)
- Auto-profile learned over time (rules are explicit; learning later)
- Installers/store signing (pyinstaller manual for now)

## 16. Acceptance criteria

1. Fresh install -> walkthrough -> quick5 calibration passes with
   reported accuracy <= 150 px on a normal 1080p screen; halo matches.
2. Desktop profile: eyes+hand cursor moves with magnet feel; pinch = click
   and drag of a real window; two-finger pinch = Tab; key wheel performs
   Ctrl+C/Ctrl+V in Notepad; dwell-click and precision squeeze work when
   enabled in menu.
3. Games profile: virtual X360 visible in Windows "Game Controllers" and
   steers stick from hand movement, gaze steers right stick, pinch maps
   to A, with deadzone/curve edits applied live from Gestures tab.
4. Touch profile: pinch taps and drags a real touch-enabled app.
5. 3D profile: transform chip GRAB moves/rotates an object in Blender via
   the bridge (or mouse-look fallback with no add-on).
6. Menu: all 8 tabs reachable; every value change takes effect without
   restart; profiles cycle via hotkey; config survives restart (atomic,
   schema-validated).
7. Debug: Ctrl+Alt+D shows HUD (FPS>=25, latency, confs), inspector charts
   fire, mapping inspector shows real source->action->backend lines, a
   recorded .npz replays through Tier 2 harness and matches goldens.
8. Robustness: unplug camera mid-drag -> no stuck button/key anywhere
   (verifiable by kill-test panel + manual check); kill-switch works with
   UI frozen; 10-min soak -> 0 stuck inputs; Tier 1+2 green in CI-like
   run, Tier 3 + manual checklist green on dev machine.

## 17. Open questions (deferred, non-blocking)

- ViGEm bus install state on target machines -> Help tab detection + link
- Polynomial gaze model: worth it beyond affine? -> config flag, measure
  on real sessions before deciding default
- Touch injection API choice (SendInput touch vs Windows Touch API):
  prototype both in Tier 3, pick by reliability on real apps
- Second-hand two-hand gestures: which are worth the ambiguity? ->
  ship zoom + two-finger pinch only, revisit after dogfooding
- Progressive calibration sample weighting: tune from real recordings
