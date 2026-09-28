# MoonRay for Blender

*[Leer en español](README.es.md)*

A Blender render engine powered by [MoonRay](https://openmoonray.org/), DreamWorks
Animation's open source production renderer. It works like Cycles: interactive
rendering in the viewport (*Rendered* shading mode) and final renders with F12.

MoonRay doesn't support Windows, so it runs inside **WSL2**. Blender talks to it
through `moonray_bridge`, a small C++ server:

```
 Blender (Windows)                          WSL2 (AlmaLinux 9)
┌───────────────────────┐   TCP localhost  ┌───────────────────────────┐
│ moonray_blender add-on│ ───────────────▶ │ moonray_bridge            │
│  · exports the scene  │  RDLA + meshes   │  one process per session  │
│  · draws the frames   │ ◀─────────────── │  MoonRay RenderContext    │
└───────────────────────┘   RGBA pixels    └───────────────────────────┘
```

> **Status:** early (0.1.0), tested on Windows 11 + Blender 5.1. Expect rough edges.

## Features

- **Interactive viewport** with progressive refinement: orbiting the view, moving
  objects or editing materials updates the render live. Only what changed is sent
  (moving an object sends a matrix, not its mesh).
- **Final render (F12)** with progress in the Image Editor.
- **Geometry:** meshes, curves, surfaces, metaballs and text (evaluated with
  modifiers), with UVs, per-corner normals and one material per slot.
- **Instancing:** collection instances, particles and Geometry Nodes instances via
  `RdlInstancerGeometry`.
- **Lights:** Point → `SphereLight`, Spot → `SpotLight`, Sun → `DistantLight`,
  Area → `RectLight` / `DiskLight`, World → `EnvLight` (color or HDRI). Intensities
  are converted so scenes match Cycles (verified with single-light test scenes).
- **Materials:** Principled BSDF, Diffuse, Glossy, Glass and Emission are converted to
  `DwaBaseMaterial`. Image Texture nodes linked directly to an input become
  `ImageMap`, and the Normal Map node becomes `ImageNormalMap`.
- **Cameras:** perspective and orthographic, with shift, sensor fit and depth of field.

### Known limitations

- Only textures linked *directly* to shader inputs are translated; intermediate
  nodes (Mapping, ColorRamp, Mix...) are ignored. No subsurface or sheen yet.
- HDRI orientation and instancing haven't been validated against Cycles yet.
- **GPU:** the add-on has a *Device* option (CPU / GPU) that selects MoonRay's XPU
  mode, but **NVIDIA doesn't ship OptiX in the WSL2 driver**
  ([NVIDIA forum](https://forums.developer.nvidia.com/t/problem-running-optix-7-6-in-wsl/239355)),
  so under WSL MoonRay falls back to CPU automatically. GPU rendering works on a
  native Linux install (see below).

## Installation

Requirements: Windows 10/11 with WSL2, Blender 4.2 or newer, ~30 GB of free disk
space and a few hours for the first MoonRay build.

### 1. MoonRay in WSL

```powershell
wsl --install -d AlmaLinux-9 --no-launch
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<path-to-repo>/wsl/setup_wsl.sh
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<path-to-repo>/wsl/build_moonray.sh all
```

AlmaLinux 9 is binary compatible with Rocky Linux 9, the platform MoonRay officially
supports. Build logs go to `/opt/MoonRay/logs/`.

### 2. moonray_bridge

```powershell
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<path-to-repo>/wsl/build_bridge.sh
```

It is installed to `/opt/MoonRay/bridge/`.

### 3. The add-on

```powershell
blender --command extension build --source-dir addon/moonray_blender --output-dir dist
blender --command extension install-file -r user_default --enable dist/moonray_blender-0.1.0.zip
```

(or *Edit → Preferences → Get Extensions → Install from Disk*). Then pick
**MoonRay** as the render engine in *Render Properties*.

The add-on starts `moonray_bridge` in WSL automatically the first time you render.
The WSL distribution, user and port can be changed in the add-on preferences.

### Optional: GPU build

```powershell
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<path-to-repo>/wsl/install_cuda.sh
$env:WSLENV="GPU/u"; $env:GPU="1"
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<path-to-repo>/wsl/build_moonray.sh moonray
```

`wsl/patch_moonray_wsl.py` (applied automatically by `build_moonray.sh`) lets MoonRay
detect the NVIDIA driver under WSL, but OptiX itself is still missing from the WSL
driver, as explained above.

## Tests

```powershell
blender --background --factory-startup --python tests/test_export.py   # exporter, no MoonRay needed
blender --background --factory-startup --python tests/test_client.py   # protocol, fake bridge
blender --background --factory-startup --python tests/test_render.py   # real F12 render
blender --factory-startup --python tests/test_viewport.py              # viewport, opens a window
```

## Repository layout

| Folder | Contents |
|---|---|
| `addon/moonray_blender/` | Blender add-on (extension for 4.2+) |
| `bridge/` | `moonray_bridge` (C++, built against MoonRay) |
| `wsl/` | Scripts to set up WSL and build MoonRay and the bridge |
| `tests/` | Tests that run inside Blender |

## Protocol

Messages have a 16-byte header (`magic`, `type`, `size`) followed by the payload.
Message types live in [`bridge/src/Protocol.h`](bridge/src/Protocol.h) and
[`addon/moonray_blender/protocol.py`](addon/moonray_blender/protocol.py). Small scene
changes travel as RDLA text; meshes travel as binary arrays.

## License

- The Blender add-on (`addon/`, `tests/`) is licensed under
  [GPL-3.0-or-later](addon/moonray_blender/LICENSE), as required for Blender add-ons.
- `moonray_bridge` and the build scripts (`bridge/`, `wsl/`) are licensed under
  [Apache-2.0](bridge/LICENSE), the same license as MoonRay.

MoonRay is a trademark of DreamWorks Animation. This project is not affiliated with
or endorsed by DreamWorks Animation.
