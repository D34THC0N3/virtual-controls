# Virtual Controls — Full Workspace Survey

**Scope:** every subdirectory of `D:\DEV\VIrtual Controls`
**Date:** 2026-09-25
**Method:** one dedicated exploration pass per repository (file reads + structure walk) plus a graphify AST-only knowledge-graph pass over the full corpus (19,223 nodes / 36,036 edges / 904 communities).

---

## 1. Workspace Overview

| Path | Kind | Size / Count | Role |
|---|---|---|---|
| `barehands-main/` | Source (Python + HTML) | 29 files | Webcam bare-hand "glass board" drawing app with AI hooks |
| `eye-tracking-master/` | Source (Java + C++/JNI + Python) | 1,663 files (~350 MB) | 2013 Android eye-tracking student project (Haar + Neuroph MLP) |
| `GazePointer-master/` | Source (C#/WPF) | 280 files (~11 MB) | Microsoft Research hands-free Windows control (Tobii, MIT) |
| `PyGaze-master/` | Source (Python) | 136 files | GPLv3 eye-tracking toolbox / hardware abstraction layer |
| `New folder/` | Archives | 4 ZIPs (189 MB) | ZIP copies of the same four repos |
| `GazePointer 2.9.2.msi` | Binary | 103,788,032 bytes | Compiled GazePointer installer (mention-only, not analyzed) |
| `graphify-out/` | Generated | — | Knowledge graph artifacts (see §8) |

**Corpus totals:** 2,101 files, ~2,227,322 words — 927 code files, 499 docs, 7 papers, 666 images, 2 video.

The common theme: **four independent gaze / gesture input projects** — camera-based hands (barehands), camera-based eyes (eye-tracking-master), commercial eye-tracker hardware (GazePointer, PyGaze). Nothing has been integrated yet; they sit side by side.

---

## 2. `barehands-main/` — Webcam Bare-Hand Glass Board

The smallest and most self-contained project: a local web app that turns a webcam feed into a virtual whiteboard you draw on with your bare hands, plus hooks for wiring in an AI.

### Structure (29 files)

```
barehands-main/
├── server.py               # 392 lines — the whole backend
├── stage.html              # 3,157 lines — single-page frontend (camera, tracking, drawing)
├── barehands.json.example  # config template
├── barehands.md, README.md, CONTRIBUTING.md, TROUBLESHOOTING.md
├── run.bat, update.bat, update.sh
├── bin/board.sh, bin/board-state.sh
├── media/fx/           (fireball.png + READMEs)
├── media/holo/  media/misc/  media/models/   # asset folders + READMEs
├── sample-notes/       # bundled demo notes (Field Guide, Getting Started)
└── state/README.md     # state directory (AI integration surface)
```

### Architecture

- **Backend (`server.py`, 392 L):** Python HTTP server. Core logic in a `Handler` class with `do_GET` / `do_POST`; loads config via `load_config()`; serves `stage.html` and media assets behind a path jail (the media jail and config loader are the graph's `barehands` cluster — community **c355**, 16 members, the project's only community ≥ 8 nodes).
- **Frontend (`stage.html`, 3,157 L):** everything in one file — webcam capture, hand detection/gesture parsing, canvas drawing, note rendering.
- **AI integration via state files:** the app exposes its state under `state/` and accepts localhost POSTs — an external AI agent reads the board state, writes back notes/actions. `sample-notes/Getting Started/Wire In Your AI.md` documents this. `bin/board.sh` / `bin/board-state.sh` are helper scripts for shell-level interaction.
- **Config:** `barehands.json.example` → runtime `barehands.json`.

### Key facts

- No frameworks, no build step: `python server.py` + `run.bat` on Windows.
- Single-file frontend makes it the hardest to modularize but the easiest to run.
- Media assets: `media/fx/fireball.png`, `media/misc/glass-hands.png` (+ README placeholders in `holo/`, `models/`).
- The graph shows **no large internal call structure beyond the HTTP handler** — this project's complexity lives in one file, not across modules.

---

## 3. `GazePointer-master/` — Microsoft Research Hands-Free Windows Control

Microsoft Research *Enabling Technologies* project (2017, MIT license): a Windows WPF application that lets Tobii eye-tracker users control the mouse and click UI elements by dwelling their gaze. Distributed as `GazePointer 2.9.2.msi` (the installer sits in the workspace root).

### Structure (~280 files / 11.1 MB)

```
GazePointer-master/
├── GazePointer.proj            # MSBuild project
├── appveyor.yml                # CI
├── apps/
│   └── GazePointerTest/        # test/demo app
├── lib/                        # 6 class libraries (7 .csproj total)
│   ├── Microsoft.HandsFree.Filters       # gaze signal filtering
│   ├── Microsoft.HandsFree.GazePointer   # core dwell-click engine
│   ├── Microsoft.HandsFree.MVVM           # MVVM plumbing
│   ├── Microsoft.HandsFree.Sensors        # EyeX/Eye tracker access + streams
│   ├── Microsoft.HandsFree.Settings       # settings model, serialization, Nudgers
│   └── Microsoft.HandsFree.Win32          # P/Invoke: window styles, messages
└── external/
    ├── TobiiEyeXSDK-DotNet-1.8.486/       # EyeX .NET SDK
    └── TobiiGazeSdk-DotNetApi-2.1.3.304-Win64/  # Gaze SDK + samples
```

### Architecture

- **Capture:** `lib/Microsoft.HandsFree.Sensors` wraps the Tobii EyeX SDK; exposes gaze as Rx-style async streams (`AsyncData`, `FixationDataStream`, connection-state streams — communities c44/c49).
- **Filtering:** `lib/Microsoft.HandsFree.Filters` smooths raw gaze into fixations (`Settings`, `CancelEventArgs`).
- **Dwell-click engine:** `lib/Microsoft.HandsFree.GazePointer` implements gaze-as-mouse:
  - `GazePointer.cs:108` `Attach()` / `GazePointer.cs:135` `DetachAll()` — wire into / out of the target app.
  - `GazePointer.cs:565-616` `InvokeTarget()` — **the dwell click itself**: performs a UI Automation invoke on whatever the user is staring at.
  - Uses **WPF UI Automation**, not OS-level mouse events, to activate targets.
- **Window targeting:** `lib/Microsoft.HandsFree.Win32` P/Invokes (`ShowWindowFlags`, `WindowStyles`, `WM_*` message constants — community c15, 97 members).
- **Settings:** `lib/Microsoft.HandsFree.Settings` — typed settings with numeric "Nudgers" (c20, 93 members) and `ValueNudgerFactory` serialization.
- **Testing:** `apps/GazePointerTest` exercises the engine.

### Key facts

- C# / WPF, MSBuild + AppVeyor; NuGet-based Tobii SDK dependencies vendored under `external/`.
- The whole product is essentially: **Tobii gaze → filter → dwell timer → UI Automation invoke**.
- Graph hub: `EyeTrackingEngine.cs` (c47, 63 members) and `GazeDataProvider.cs` (c35, 72 members) are the two central classes.

---

## 4. `eye-tracking-master/` — Android Camera Eye Tracking (2013)

A 2013 Wright State University **CEG4210** course project: detect eyes in a front-facing camera with Haar/Viola-Jones cascades, save eye crops as JPEGs, then train offline Neuroph neural nets (eye identity + 7-way gaze direction). **The trained networks are never invoked on the device** — training and inference are separate, offline workflows.

### Structure (1,995 files / ~350 MB — 1,663 tracked entries)

```
eye-tracking-master/
├── android/                 # Eclipse ADT Android app (package edu.wright.ceg4210.eyetracker)
│   └── native/jni/include/  # vendored OpenCV C++ headers (large)
├── neural_network/          # Neuroph-based training (offline)
├── OpenCV_Library_Files/    # vendored OpenCV for Android (second copy)
└── screenshots/             # 647 images
```

### Architecture

- **App (`android/`):** Java, package `edu.wright.ceg4210.eyetracker`. `EyeTrackingController` is the god-class hub (123 edges). Pipeline: camera frame → OpenCV `CascadeClassifier` (eye) → crop → save JPEG. JNI/NDK bindings to vendored OpenCV C++ headers.
- **Offline ML (`neural_network/`):** Java using the **Neuroph** library. Two networks: eye-identity classification and 7-class gaze direction. `Neuron` (151 edges) and `NeuralNetwork` (144 edges) are graph god-nodes. Model weights live in `.nnet` files.
- **Vendored dependencies (dominate the graph):**
  - **OpenCV** — two copies (`android/native/jni/include/` and `OpenCV_Library_Files/`), including a duplicate pair of `opencv2/ts/ts_gtest.h` (the two largest graph communities, c0/c1 @ 350 nodes each).
  - **gtest/FLANN** — `ValueArray43..50` templates (communities c2/c3 @ 299; god-nodes `ValueArray50` @ 104 edges each, duplicated).
  - **Neuroph** — vendored source (communities c6/c7 @ 202/201; hub labels like `Neuroph: Override`).
- **Legacy:** Eclipse `.classpath`/project files, Android JNI `.cpp` files (pre-existing LSP noise).

### Key facts

- The interesting first-party code is a **small fraction** of the repo; the graph is ~90% vendored OpenCV/gtest/Neuroph.
- God nodes `Mat` (510 edges), `Core` (286), `Imgproc` (257), `Moments` (103) are all OpenCV.
- Notable cross-cutting bridge: `Point` (betweenness 0.182) — the most connected community-bridging symbol in the whole graph (mostly a name collision across vendored code, see §8).
- Training is desktop/offline; the Android app only collects data. **No on-device inference path exists.**

---

## 5. `PyGaze-master/` — Eye-Tracking Hardware Abstraction Toolbox

The **PyGaze** toolbox (Dalmaijer & Mathôt, GPLv3) — a Python hardware-abstraction layer so experiments can swap eye trackers without code changes. Published on PyPI as `python-pygaze`.

### Structure (136 files)

```
PyGaze-master/
├── pyproject.toml              # pip packaging (python-pygaze)
├── pygaze/                     # the library
│   ├── eyetracker.py  display.py  mouse.py  keyboard.py
│   ├── screen.py  sound.py  time.py  logfile.py    # public facades
│   ├── defaults.py  settings.py  libgazecon.py  libinput.py  liblog.py
│   ├── py3compat.py
│   ├── _display/  _mouse/  _keyboard/  _screen/  _sound/  _time/  _joystick/
│   ├── _logfile/  _misc/
│   ├── _eyetracker/            # vendor implementations (see below)
│   └── plugins/                # OpenSesame plugin support code
├── examples/                   # usage examples
├── opensesame_plugins/         # OpenSesame experiment-editor plugins
├── additional_libraries/       # extra vendor libs
├── artwork/  resources/
```

### Architecture

- **Pattern:** public facade class (`Eyetracker`, `Display`, `Mouse`, …) with a `_`-prefixed backend directory of implementations; `BaseEyeTracker` (`_eyetracker/baseeyetracker.py`) is the interface contract.
- **Vendor backends in `pygaze/_eyetracker/`:**
  `libeyelink.py` (EyeLink), `libsmi.py` (SMI), `libtobii.py` + `libtobii*.py` (Tobii incl. Pro/Legacy/Glasses), `libeyetribe.py` (EyeTribe), `libopengaze.py`/`opengaze.py` (OpenGaze), `libalea.py` (Tobii Alea), `libdumbdummy.py`, `libdummytracker.py` (dummies), plus APIs `iViewXAPI.py`, `eyelinkgraphics.py`, `pytribe.py`.
  Graph communities for "Not supported for X (yet)" markers show several stubs.
- **Vendored dependency:** `pygaze/_eyetracker/alea/` (Apache-2.0) — Alea tracker helper library.
- **OpenSesame integration:** `opensesame_plugins/pygaze/pygaze_init` etc. (graph community labeled `PyGaze: opensesame_plugins/pygaze/pygaze_init (Item)`).
- **HAL surface:** screen/mouse/keyboard/sound/time/logfile abstractions mirror classic experimental-runtime APIs (`psychopos2pos()`, `pos2psychopos()`, `deg2pix()` appear as graph hubs).

### Key facts

- GPLv3 (with Apache-2.0 vendored Alea code) — **license differs from GazePointer's MIT**; relevant if combining code.
- Pure Python, pip-installable, no build step.
- This is the most reusable piece for a unified "virtual controls" project: it already defines the abstraction for eye trackers, displays, and input devices.

---

## 6. `New folder/` — ZIP Archives

| File | Size |
|---|---|
| `eye-tracking-master.zip` | 176,292,278 B |
| `GazePointer-master.zip` | 5,724,500 B |
| `PyGaze-master.zip` | 4,159,732 B |
| `barehands-main.zip` | 2,685,001 B |

Byte-for-byte archives of the four checked-out repositories (ZIP copies, not additional projects). No unique content.

---

## 7. `GazePointer 2.9.2.msi`

103,788,032-byte Windows installer for GazePointer 2.9.2 — the compiled distribution of `GazePointer-master/` (or its release tag). Binary; not analyzed. Mentioned for completeness.

---

## 8. Knowledge Graph Findings (`graphify-out/`)

AST-only pass (zero LLM/vision cost) over all 927 code files.

### Artifacts

| File | What it is |
|---|---|
| `graph.json` (30.3 MB) | Full graph: 19,223 nodes / 36,036 links / 904 communities (note: key is `links`, not `edges`) |
| `graph.html` (801 KB) | **Aggregated** HTML export — 904 community nodes, 1,460 cross-community edges |
| `GRAPH_REPORT.md` (173 KB) | Labeled report: corpus check, summary, hubs, god nodes, surprising connections, cycles, communities, knowledge gaps, suggested questions |
| `.graphify_labels.json` (54 KB) | 904 community labels (134 hand-written + 770 auto-generated) |
| `manifest.json`, `cost.json` | Run manifest + cost record (0 tokens — AST-only) |

### Health

- **Extraction:** 97% EXTRACTED · 3% INFERRED (1,066 edges, avg confidence 0.83) · 0% AMBIGUOUS.
- ⚠ **2,264 dangling-endpoint edges** (point at nodes that don't exist — mostly unresolved external/stdlib symbols).
- ⚠ **10,106 collapsed edges** — normal for an undirected graph: the same relationship stored in both directions got merged.
- ✅ 0 missing-endpoint, 0 self-loops, 0 exact-duplicate edges.
- ⚠ **6,313 isolated nodes** (`Border`, `VisualStateGroup`, `ContentPresenter`, `Mouse`, `ApplicationVersion`, +6,308) — declared but never referenced in code the extractor saw; typical of WPF/XAML symbol surfaces.
- ⚠ **HTML honesty warning:** `graph.html` shows the **aggregated community view**, not individual nodes — with 19,223 nodes it auto-collapsed (limit 5,000). Node-level detail lives in `graph.json` / `GRAPH_REPORT.md`.

### God Nodes (most connected — core abstractions)

1. `Mat` — 510 edges *(OpenCV, eye-tracking-master)*
2. `Core` — 286 *(OpenCV)*
3. `Imgproc` — 257 *(OpenCV)*
4. `Neuron` — 151 *(Neuroph, eye-tracking-master)*
5. `NeuralNetwork` — 144 *(Neuroph)*
6. `EyeTrackingController` — 123 ← **the only first-party god node** (eye-tracking-master)
7. `ValueArray50` — 104 ×2 *(gtest — duplicated OpenCV trees)*
8. `Moments` — 103 *(OpenCV)*
9. `ValueArray49` — 102 *(gtest)*

### Surprising Connections (all INFERRED)

- `write()` → `w` : `opencv2/core/operations.hpp` ↔ `opencv2/legacy/blobtrack.hpp` (and its mirror copy)
- `read()` → `r` : `operations.hpp` ↔ `opencv2/ml/ml.hpp` (and its mirror copy)
- `CvLevMarq()` → `cvTermCriteria()` : `calib3d.hpp` ↔ `core/types_c.h`

All five are artifacts of **two duplicate OpenCV header trees** plus macro-inferred edges — not real project coupling.

### Suggested Questions (from the graph)

- **Why does `Point` connect OpenCV (Calib3d, imgproc, Subdiv2D, MatOfPoint3, …) to GazePointer (`CancelEventArgs`, `DrawingVisual`, `ButtonState`, Tobii samples, `Settings`)?** — betweenness 0.182, the top cross-community bridge. (Mostly a generic-name collision: `Point` means cv::Point in one repo and System.Windows.Point in the other — the *useful* reading is that these are the two coordinate-system vocabularies any unified project must reconcile.)
- **Why does `Mat` bridge 40+ OpenCV communities plus `EyeTrack/App: activity`?** — betweenness 0.120; `Mat` is the universal currency of the eye-tracking pipeline.
- **Why does `WeightsRandomizer` bridge Neuroph communities?** — betweenness 0.115.
- **What connects `Border`, `VisualStateGroup`, `ContentPresenter`, `Mouse`, `ApplicationVersion` to the rest?** — 6,313 weakly-connected nodes; documentation/edge gaps (WPF/XAML surface).
- **Should the OpenCV `ts` community be split?** — cohesion 0.006–0.016 (very weak); it's vendored test scaffolding, effectively noise.

### Community landscape (real signal beyond vendored noise)

- **Vendored dominates:** c0/c1 OpenCV ts_gtest (350 ×2, duplicate trees), c2/c3 gtest (299 ×2), c4 OpenCV Core (286), c5 Imgproc (252), c6/c7 Neuroph (202/201).
- **barehands:** exactly one meaningful cluster — c355 (16): `server.py` Handler / `do_GET` / `do_POST` / `load_config` / media jail.
- **GazePointer:** 103 communities ≥ 8 — top: c15 Win32 `WM_*` (97), c20 `Settings.Nudgers` (93), c35 `GazeDataProvider.cs` (72), c44 AsyncData/FixationDataStream (66), c47 `EyeTrackingEngine.cs` (63), c49 connection-state streams (61).
- **PyGaze:** many mid-size clusters — `BaseEyeTracker`, per-vendor trackers (TobiiPro, TobiiController, Alea, EyeTribe, OpenGaze, DumbDummy), `_screen` coordinate helpers, OpenSesame plugin `Item`s.
- **eye-tracking-master first-party:** `EyeTrack/App: activity` + `EyeTrack/App: util` clusters (small — most of the repo is vendored).

---

## 9. Cross-Project Comparison

| Dimension | barehands | GazePointer | eye-tracking-master | PyGaze |
|---|---|---|---|---|
| Input modality | Hands (webcam) | Eyes (Tobii hardware) | Eyes (webcam) | Eyes (any vendor) |
| Platform | Local web (Python + HTML) | Windows WPF desktop | Android (Eclipse ADT, 2013) | Cross-platform Python |
| Language | Python, JS/HTML | C# | Java, C++/JNI, Python | Python |
| License | (see LICENSE) | MIT | (student project; vendored OpenCV BSD, Neuroph) | GPLv3 + Apache-2.0 vendored |
| Maturity | Runnable small app | Product-grade (MSR, shipped MSI) | Course prototype, NN not wired up | Actively packaged library |
| Output | Board state (file/POST) | Mouse/dwell clicks | JPEG eye crops → offline training | Experiment-runtime input API |
| Graph size signal | 1 community ≥ 8 | 103 communities ≥ 8 | dominated by vendored code | ~15+ meaningful clusters |

---

## 10. Observations for the Amalgamated "Virtual Controls" Project

1. **No shared code exists today.** Four independent repos, four stacks (Python web, C# WPF, Java/Android, Python HAL), zero cross-references in the graph.
2. **The abstraction layer already exists — PyGaze.** Its facade pattern (`Eyetracker`/`Display`/`Mouse`/`Keyboard`/`Screen`/`Sound`/`Time`/`LogFile` + `Base*` interfaces) is the natural skeleton for a unified "virtual controls" API: add bare-hands and dwell-click as new input backends behind the same interface.
3. **GazePointer contributes the best interaction logic** (dwell-click, gaze filtering, settings, Win32 targeting) but is Windows-only, MIT, and tightly WPF-coupled.
4. **barehands contributes a working realtime camera pipeline** (webcam → gestures → state) with an AI-friendly state-file/POST contract — a good model for how the unified project should expose itself to agents.
5. **eye-tracking-master is mostly disposable vendored weight** (~350 MB OpenCV/gtest/Neuroph, two duplicate copies). Its valuable artifacts are: the Haar eye-detection approach, the Neuroph-trained `.nnet` gaze models, and `EyeTrackingController`'s pipeline design. Its duplicated header trees are the #1 source of graph noise (and 5 of 5 "surprising connections").
6. **Licensing needs a decision:** GPLv3 (PyGaze) vs MIT (GazePointer) vs vendored BSD/Apache — combining directly would force GPL on the whole thing.
7. **The MSI + `New folder` ZIPs are redundant** — safe to ignore for planning (or archive).

---

*Generated from `GRAPH_REPORT.md`, `graph.json` (19,223 nodes / 36,036 links / 904 communities), per-repo exploration passes, and the workspace file inventory.*
