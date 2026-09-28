# MoonRay para Blender

*[Read in English](README.md)*

Motor de render para Blender basado en [MoonRay](https://openmoonray.org/), el
renderer de producción de código abierto de DreamWorks Animation. Funciona como
Cycles: render interactivo en el viewport (modo *Rendered*) y render final con F12.

MoonRay no funciona en Windows, así que corre dentro de **WSL2**. Blender se
comunica con él a través de `moonray_bridge`, un pequeño servidor en C++:

```
 Blender (Windows)                          WSL2 (AlmaLinux 9)
┌───────────────────────┐   TCP localhost  ┌───────────────────────────┐
│ addon moonray_blender │ ───────────────▶ │ moonray_bridge            │
│  · exporta la escena  │  RDLA + mallas   │  un proceso por sesión    │
│  · dibuja los frames  │ ◀─────────────── │  RenderContext de MoonRay │
└───────────────────────┘   píxeles RGBA   └───────────────────────────┘
```

> **Estado:** versión temprana (0.1.0), probada en Windows 11 con Blender 5.1.

## Funciones

- **Viewport interactivo** con refinamiento progresivo. El render se actualiza en
  vivo al orbitar la vista, mover objetos o editar materiales. Solo se envía lo que
  cambia: mover un objeto manda su matriz, no la malla.
- **Render final (F12)**, con progreso en el Image Editor.
- **Geometría:** mallas, curvas, superficies, metaballs y texto (con modificadores
  aplicados). Incluye UVs, normales por esquina y un material por slot.
- **Instancias:** de colección, partículas y Geometry Nodes, mediante
  `RdlInstancerGeometry`.
- **Luces:**
  - Point → `SphereLight`
  - Spot → `SpotLight`
  - Sun → `DistantLight`
  - Area → `RectLight` / `DiskLight`
  - World → `EnvLight`, con color o HDRI

  Las intensidades se convierten para que coincidan con Cycles; está comprobado
  con escenas de una sola luz.
- **Materiales:** Principled BSDF, Diffuse, Glossy, Glass y Emission se convierten a
  `DwaBaseMaterial`. Las texturas conectadas directamente pasan a `ImageMap`, y el
  nodo Normal Map a `ImageNormalMap`.
- **Cámaras:** perspectiva y ortográfica, con shift, sensor fit y profundidad de campo.

### Limitaciones conocidas

- Solo se traducen las texturas conectadas *directamente* a las entradas del
  shader. Los nodos intermedios (Mapping, ColorRamp, Mix...) se ignoran. Todavía no
  hay subsurface ni sheen.
- La orientación del HDRI y las instancias aún no se han comparado con Cycles.
- **GPU:** el addon tiene la opción *Device* (CPU / GPU), que activa el modo XPU de
  MoonRay. Pero **NVIDIA no incluye OptiX en el driver de WSL2**
  ([foro de NVIDIA](https://forums.developer.nvidia.com/t/problem-running-optix-7-6-in-wsl/239355)),
  así que en WSL MoonRay vuelve automáticamente a CPU. El render por GPU sí
  funciona en una instalación nativa de Linux.

## Instalación

Requisitos:
- Windows 10/11 con WSL2
- Blender 4.2 o superior
- Unos 30 GB libres en disco
- Algunas horas para la primera compilación de MoonRay

### 1. MoonRay en WSL

```powershell
wsl --install -d AlmaLinux-9 --no-launch
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<ruta-al-repo>/wsl/setup_wsl.sh
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<ruta-al-repo>/wsl/build_moonray.sh all
```

AlmaLinux 9 es compatible a nivel binario con Rocky Linux 9, la plataforma que
MoonRay soporta oficialmente. Los logs de la compilación quedan en `/opt/MoonRay/logs/`.

### 2. moonray_bridge

```powershell
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<ruta-al-repo>/wsl/build_bridge.sh
```

### 3. El addon

```powershell
blender --command extension build --source-dir addon/moonray_blender --output-dir dist
blender --command extension install-file -r user_default --enable dist/moonray_blender-0.1.0.zip
```

También puedes instalarlo desde *Edit → Preferences → Get Extensions → Install from
Disk*. Después, elige **MoonRay** como motor en *Render Properties*.

El addon arranca `moonray_bridge` automáticamente la primera vez que renderizas.
La distribución de WSL, el usuario y el puerto se cambian en las preferencias del addon.

### Opcional: compilación con GPU

```powershell
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<ruta-al-repo>/wsl/install_cuda.sh
$env:WSLENV="GPU/u"; $env:GPU="1"
wsl -d AlmaLinux-9 -u root -- bash /mnt/c/<ruta-al-repo>/wsl/build_moonray.sh moonray
```

## Pruebas

```powershell
blender --background --factory-startup --python tests/test_export.py   # exportador, sin MoonRay
blender --background --factory-startup --python tests/test_client.py   # protocolo, bridge falso
blender --background --factory-startup --python tests/test_render.py   # render F12 real
blender --factory-startup --python tests/test_viewport.py              # viewport, abre una ventana
```

## Licencia

- El addon de Blender (`addon/`, `tests/`) usa la licencia
  [GPL-3.0-or-later](addon/moonray_blender/LICENSE), como exige Blender para sus addons.
- `moonray_bridge` y los scripts (`bridge/`, `wsl/`) usan la licencia
  [Apache-2.0](bridge/LICENSE), la misma que MoonRay.

MoonRay es una marca de DreamWorks Animation. Este proyecto no está afiliado ni
respaldado por DreamWorks Animation.
