# SPDX-License-Identifier: GPL-3.0-or-later
#
# Helpers to write RDLA (MoonRay's Lua-based scene format).
#
# Matrix convention: RDL2 uses row vectors (translation in the last row) and
# Blender uses column vectors, so the transpose is written.

import re


def s(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def f(x):
    return format(float(x), ".9g")


def b(x):
    return "true" if x else "false"


def i(x):
    return str(int(x))


def vec2(v):
    return f"Vec2({f(v[0])}, {f(v[1])})"


def vec3(v):
    return f"Vec3({f(v[0])}, {f(v[1])}, {f(v[2])})"


def rgb(c):
    return f"Rgb({f(c[0])}, {f(c[1])}, {f(c[2])})"


def mat4(m):
    return "Mat4(" + ", ".join(f(m[r][c]) for c in range(4) for r in range(4)) + ")"


def ref(cls, name):
    return f"{cls}({s(name)})"


def bind(obj_ref, default=None):
    if default is None:
        return f"bind({obj_ref})"
    return f"bind({obj_ref}, {default})"


def block(cls, name, attrs):
    """Creates or updates an object: Class("name") { ["attr"] = value, ... }"""
    body = "".join(f"    [{s(k)}] = {v},\n" for k, v in attrs.items())
    return f"{ref(cls, name)} {{\n{body}}}\n"


_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-/]")


def safe_name(name):
    """Stable RDL object name without unusual characters."""
    return _UNSAFE.sub("_", name)
