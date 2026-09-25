# Research: virtual control software landscape

Date: 2026-09-25
Status: draft, extended as findings arrive
Method: web searches run on 2026-09-25 through the session search provider, plus license files already vendored in this workspace.

How to read this document:

- [FACT] a claim with a source linked in section 7.
- [USER] something you told me, mainly the vision captured in README.md.
- [INFERENCE] my reading of the facts, not stated outright by any source.
- [RECOMMENDATION] a concrete suggestion for our app, built on the facts above.

## 1. What we are building ([USER])

From README.md, unchanged:

- Camera-based control with eye-guided input. Markers: a circle for the hand, a dot for the gaze point.
- Gaze acts as a soft magnet that steers the hand cursor instead of replacing it.
- Outputs: a simulated Xbox/PS5 controller, plus mouse and keyboard.
- Simultaneous modes: 3D object control (Blender, Maya), a virtual touchscreen, and a plain mouse fallback.
- Pinch means drag. Look at something, then point a finger to click.
- An always-reachable menu, a debug toggle, tracking configuration, gesture customization, and custom gestures (for example a volume knob).
- Must stay light and usable, not a research prototype.

## 2. Similar software and devices

### 2.1 Virtual gamepads and input remappers

- **vgamepad** [FACT]: Python library that emulates an Xbox 360 or DualShock 4 controller, built on the ViGEm framework on Windows. Linux support exists but is described as experimental. MIT licensed. Source: https://github.com/yannbouteiller/vgamepad, PyPI package `vgamepad`.
- **AntiMicroX** [FACT]: free GPL-3.0 desktop program that maps gamepad buttons, sticks and triggers to keyboard keys, mouse buttons and movement, scripts, and macros. Runs on Windows and Linux. Notable conventions we can borrow: multiple switchable mapping sets, auto-profiles that activate per focused application window, and an SDL2 config generator for odd controllers. About 3,953 stars and 96 contributors on GitHub as of 2026-09-25; current release 3.5.1 (2025-01-27). Source: https://github.com/AntiMicroX/antimicrox.
- **input-remapper** [FACT]: Linux tool to change the behavior of input devices, supports X11 and Wayland, combinations, programmable macros, joysticks and wheels. Source: https://github.com/sezanzeb/input-remapper (license: check the repo before reusing code).
- **JoyToKey** [FACT, secondary source]: closed-source commercial product, roughly $7 one-time with a limited free trial. Described on a fan site, not the vendor page: https://anti-micro.com/. Relevance: it is the paid incumbent AntiMicroX was built to replace.

### 2.2 Open-source eye tracking

- **PyGaze** [FACT]: open-source eye-tracking toolbox written in Python, works with many commercial trackers and includes a webcam-based tracker. GPL-3.0 (COPYING vendored in this workspace). Sources: http://pygaze.org/, https://github.com/esdalmaijer/PyGaze.
- **OpenGazer** [FACT]: open-source gaze tracker for ordinary webcams, from the Microsoft Research lineage. GPL-2.0. Source: https://github.com/opengazer/OpenGazer.
- **WebGazer** [FACT]: open-source webcam eye tracking library that runs in the browser, from the Brown HCI group, usable as a JavaScript dependency. License: verify at the repo before reusing. Source: https://github.com/brownhci/WebGazer.
- **EyeTheia** [FACT]: lightweight eye tracking toolbox for laptops using a regular webcam. A front-facing camera feeds MediaPipe FaceMesh, the output feeds an iTracker-style CNN gaze estimator, followed by user fine-tuning. Ships a 13-point calibration routine; the paper reports that per-user fine-tuning reduces error and names the One Euro filter as future work. Published in Pattern Recognition 2026; preprint at https://arxiv.org/abs/2601.06279.
- **GazeMetrics** [FACT]: open-source tool for measuring HMD eye-tracker data quality (accuracy, precision, drift). Two findings that shape our UI: measurements drift over time, up to 30% decay over about 4 minutes (citing Ehinger et al.), and pre-programmed calibration procedures often never show the user their calibration outcome. Source: https://par.nsf.gov/servlets/purl/10193015.
- **EyeO** [FACT]: gaze typing work with autocalibration, presented at CHI EA 2025, combining gaze input with a gaze-output display plus a filtering and autocalibration algorithm. Source: https://dl.acm.org/doi/10.1145/3706599.3720090.

### 2.3 Hand tracking already vendored here

The workspace already contains the hand-tracking candidates (barehands, depthai_hand_tracker, minimal-hand, human, and the awesome-hand-pose-estimation list). Each one has an entry in the Credits section of README.md with author and origin link. [USER] No further searching needed beyond noting that all four usable codebases are MIT licensed except the survey list, which has no license file.

### 2.4 Gaze-supported manual pointing

- **Eye&Head** [FACT]: Sidenmark and Gellersen, UIST 2019, "synergetic eye and head gaze pointing for gaze-supported pointing and selection." Describes dynamic coupling between the gaze pointer and the manual pointer, hover behavior, pre-selection exploration, and fast confirmation, comparing head-supported against eyes-only gaze. Evaluated in VR. Source: https://dl.acm.org/doi/abs/10.1145/3332165.3347921 (81 citations reported by search on 2026-09-25).
- **Calibration-free gaze** [FACT]: research on smooth-pursuit and other calibration-free gaze interaction exists, surveyed in https://pmc.ncbi.nlm.nih.gov/articles/PMC7881880/ (35 citations per search result).
- Our "soft magnet" design [INFERENCE]: the closest published pattern is the gaze-supported pointing family above, where gaze biases rather than replaces the hand pointer. Eye&Head is the strongest reference for coupling strength, hover, and confirmation timing.

### 2.5 Dwell-based accessibility control

- **EyeMine** [FACT]: Minecraft pageset for the Eyegaze Edge eye tracker. Quality-of-life features it ships with: dwell-to-build and dwell-to-mine, auto-pillaring, toolbelt and toolbar levels, plus QoL macros for common actions. Source: https://eyegaze.com/eyemine.

## 3. Quality-of-life features worth borrowing

### 3.1 Signal smoothing for gaze and hand cursors

- **1€ filter** [FACT]: Casiez and Vogel, CHI 2012. An adaptive low-pass filter whose cutoff rises with cursor speed, so it kills jitter when the pointer is still but adds almost no lag while it moves. Controlled by two parameters (a minimum cutoff and a speed coefficient), has a public interactive tuner, and implementations are available in several languages. Source: https://github.com/casiez/OneEuroFilter.
- **Tobii's accuracy vs precision framing** [FACT]: noise (imprecision) is filterable at the cost of latency, while accuracy error (a stable offset) is not something filtering fixes. Source: Tobii XR developer documentation, accuracy and precision concepts.
- **Confidence-weighted smoothing** [FACT]: a2026 poster reports that a plain 1€ filter can remove intentional slow gaze/head movement, and shows a combined "adaptive velocity-confidence smoothing" (1€ weighted by per-frame confidence) working better for pose tracking. Source: Bournemouth University SCA 2026 poster PDF from search.
- **Everyday eye-tracking design paper** [FACT]: manufacturer accuracy claims under 0.5 degrees are often exceeded in practice, with remote trackers frequently showing offsets above 1 degree, and task error rates above roughly 5% measurably slow users down. Source: search result "everyday_eyetracking.pdf".

### 3.2 Calibration

- **Point counts in practice** [FACT]: the everyday-eyetracking paper walks through a 7-point calibration; EyeTheia uses 13 points; EyeO works toward autocalibration. [INFERENCE] somewhere in the 9 to 13 point range with a visible quality readout is the practical norm for a first-time wizard.
- **Drift** [FACT]: up to 30% quality decay in 4 minutes has been measured for HMD trackers (GazeMetrics, citing Ehinger et al.). [INFERENCE] a webcam setup will drift more slowly and less severely, but a "recalibrate" affordance and periodic gentle prompts still belong in the menu.
- **Show the outcome** [FACT]: GazeMetrics found that standard calibration procedures often never show the user whether calibration worked. [RECOMMENDATION] our wizard must end with a plain-language score (good / acceptable / poor) and a one-click retry.

### 3.3 Dwell click timing

- **Tradeoff** [FACT]: the everyday-eyetracking paper states that longer dwell times reduce accidental selections but slow the user down. [INFERENCE] dwell needs to be user-configurable rather than hard-coded; a starting range around 400 to 1200 ms with a visible progress ring is a reasonable default to expose in the menu.

### 3.4 Profiles and mapping sets

- **AntiMicroX conventions** [FACT]: switchable mapping sets and per-application auto-profiles. [RECOMMENDATION] our gesture customization should support named profiles (Blender, Maya, desktop, games) with one-key switching and optional focus-based auto-switching.

### 3.5 Debug overlay

- [RECOMMENDATION] following Tobii's framing, the debug toggle should show precision and accuracy as separate readouts: a jitter cloud (spread of recent samples) next to a crosshair offset (distance from the true target), plus per-landmark confidence for hand tracking and a dropped-frame counter.

## 4. Free resources status

Downloaded into this workspace (see PROJECTS.md and the Credits section of README.md): barehands, GazePointer, PyGaze, eye-tracking, depthai_hand_tracker, EyeTracker, human, minimal-hand, awesome-hand-pose-estimation. [USER]

Candidates worth downloading next, all free:

- OneEuroFilter (MIT) for real filter code instead of reimplementing it: https://github.com/casiez/OneEuroFilter
- WebGazer (verify license first) if a browser-based fallback is ever wanted: https://github.com/brownhci/WebGazer
- AntiMicroX and input-remapper as reference reading only, not as dependencies: their mapping-set and profile conventions are the parts we want. [INFERENCE]

## 5. Recommendations for the app ([RECOMMENDATION])

1. Use vgamepad with ViGEm for the virtual Xbox/PS5 controller output on Windows rather than writing driver-level injection ourselves. Re-verify ViGEm's maintenance status first (open question 6.1).
2. Implement the 1€ filter for the gaze cursor and the hand cursor, expose its two parameters as a single "smoothing" slider in the menu, and consider confidence weighting later.
3. Build the calibration wizard as 9 to 13 points with live feedback and an end-of-run score plus retry, per sections 3.2.
4. Make dwell click time configurable with a visible progress ring, defaulting around 700 ms. [INFERENCE]
5. Organize gesture customization around named profiles with quick switching, following AntiMicroX conventions.
6. Ship a debug overlay from day one showing jitter, offset, confidence, and frame rate separately.
7. Keep EyeMine's spirit for QoL macros: a small set of one-gesture shortcuts beats a deep settings tree.

## 6. Open questions needing verification

1. ViGEm bus maintenance status and the Windows GameInput direction. Search results suggested the ViGEm project may be in maintenance mode; confirm before committing to it.
2. WebGazer's actual license file.
3. End-to-end latency of a webcam pipeline (capture to rendered cursor) on the target machine; no measured numbers yet. [USER]
4. How to drive Blender and Maya: virtual mouse and keyboard events versus their Python APIs. The vision says simulated input, but native scripting may be smoother for 3D manipulation. [USER]
5. MediaPipe hand landmark confidence semantics: is the per-landmark score usable directly for the confidence weighting in 3.1?

## 7. Sources (all accessed 2026-09-25)

- https://github.com/yannbouteiller/vgamepad
- https://github.com/AntiMicroX/antimicrox and https://anti-micro.com/
- https://github.com/sezanzeb/input-remapper
- http://pygaze.org/ and https://github.com/esdalmaijer/PyGaze
- https://github.com/opengazer/OpenGazer
- https://github.com/brownhci/WebGazer
- https://arxiv.org/abs/2601.06279 (EyeTheia)
- https://par.nsf.gov/servlets/purl/10193015 (GazeMetrics)
- https://dl.acm.org/doi/10.1145/3706599.3720090 (EyeO)
- https://dl.acm.org/doi/abs/10.1145/3332165.3347921 (Eye&Head, UIST '19)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC7881880/ (calibration-free gaze)
- https://eyegaze.com/eyemine (EyeMine)
- https://github.com/casiez/OneEuroFilter (1€ filter, Casiez and Vogel CHI 2012)
- Tobii XR developer documentation on accuracy and precision
- everyday_eyetracking.pdf (accuracy, precision, dwell tradeoffs, 7-point calibration)
- Bournemouth University SCA 2026 poster on confidence-weighted smoothing
- License files vendored in this workspace (PROJECTS.md, README.md Credits)

## 8. Gaps in this research

- No hands-on testing yet; every claim above is from reading, not from running the software.
- Latency and accuracy numbers for our own webcam setup are missing entirely; a small measurement session would answer open questions 6.3 and 6.5.
- No survey of commercial trackers (Tobii, Apple) beyond what the accuracy paper and Tobii docs state; buying recommendations are out of scope for now. [USER]
