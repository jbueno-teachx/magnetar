#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Drive POV-Ray to pre-render magnetar particle sprites.

Run only from a full project checkout (not from an installed wheel). Paths to
package assets (e.g. the HUD font TTF) are resolved relative to this script /
the repo root — no importlib.resources.

Why ``"%(key)s" %% mapping`` instead of Jinja2 / str.format?
------------------------------------------------------------
POV-Ray SDL uses curly braces heavily (``camera { ... }``, vectors, etc.).
Python's ``str.format`` / f-strings / Jinja2 would force escaping every ``{``
and ``}`` in the scene. Old-style ``"%(key)s" % {"key": value}`` only treats
``%(…)s`` as placeholders, so the POV source stays readable and unescaped.

POV-Ray CLI declares (optional alternative)
------------------------------------------
POV-Ray 3.7+ can inject values on the command line, e.g.::

    povray … Declare=SphereColor=rgb\\<1,0,0\\>

That works for simple floats/colors if the ``.pov`` uses matching ``#declare``
names and is already a valid scene. We still fill a template with ``%`` here
so multi-parameter sprites stay easy. CLI Declare remains an option later.

Charge marks / fonts (domain note — next steps)
-----------------------------------------------
POV-Ray can extrude TrueType as **3D ``text`` geometry** inside the scene, so
glyphs pick up the same lighting, reflections, and anti-aliasing as the sphere
("premium" raytraced look). Pasting 2D text onto a finished PNG throws that
away. For charge symbols we should model them *in* the POV scene (or as other
lit geometry), not composite flat labels afterward. This first pass still
renders plain colored spheres only.

Work dirs (gitignored contents; keep ``.gitkeep``)
-------------------------------------------------
* ``tmp_pov/``     — filled ``.pov`` scenes (deleted after each successful render)
* ``tmp_render/``  — intermediate PNGs

Optional install into the package tree: ``python/magnetar/assets/particles/``
only when ``--install-assets`` is passed (not the default).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATE_PATH = SCRIPT_DIR / "particle.template.pov"
TMP_POV_DIR = SCRIPT_DIR / "tmp_pov"
TMP_RENDER_DIR = SCRIPT_DIR / "tmp_render"
# Relative checkout path to the packaged bold font (for future 3D text in-scene).
FONT_TTF = REPO_ROOT / "python" / "magnetar" / "assets" / "fonts" / "IBMPlexSans-Bold.ttf"
PACKAGE_PARTICLES_DIR = REPO_ROOT / "python" / "magnetar" / "assets" / "particles"

WIDTH = 256
HEIGHT = 256

# name → POV pigment expression (rgb or rgbf)
PARTICLE_PRESETS: dict[str, str] = {
    "yellow": "rgb <1.0, 0.9, 0.15>",
    "light_blue": "rgb <0.45, 0.8, 1.0>",
    "red": "rgb <1.0, 0.2, 0.15>",
    "green": "rgb <0.2, 0.85, 0.3>",
}


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def fill_template(template: str, *, sphere_color: str) -> str:
    # Old-style % mapping — see module docstring for why not format()/Jinja2.
    return template % {
        "sphere_color": sphere_color,
    }


def find_povray(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("povray")
    if not found:
        raise SystemExit(
            "povray not found on PATH. Install POV-Ray 3.7+ or pass --povray /path/to/povray"
        )
    return found


def ensure_work_dirs() -> None:
    for d in (TMP_POV_DIR, TMP_RENDER_DIR):
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_bytes(b"")


def render_one(
    *,
    povray: str,
    name: str,
    sphere_color: str,
    template: str,
    quality_extra: list[str],
) -> Path:
    """Fill template → tmp_pov, render → tmp_render, then delete the filled .pov."""
    filled = fill_template(template, sphere_color=sphere_color)
    pov_path = TMP_POV_DIR / f"particle_{name}.pov"
    png_path = TMP_RENDER_DIR / f"particle_{name}.png"
    pov_path.write_text(filled, encoding="utf-8")

    # +FN PNG, +UA output alpha, -D no display, +A antialias
    cmd = [
        povray,
        f"+I{pov_path}",
        f"+O{png_path}",
        f"+W{WIDTH}",
        f"+H{HEIGHT}",
        "+FN",
        "+UA",
        "-D",
        "+A0.3",
        *quality_extra,
    ]
    print(" ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"povray failed for {name!r} (exit {proc.returncode})")
        if not png_path.is_file():
            raise SystemExit(f"povray reported success but missing {png_path}")
        print(f"  wrote {png_path.relative_to(REPO_ROOT)}")
        return png_path
    finally:
        # Filled scenes are throwaways once rendering finishes (success or fail).
        if pov_path.is_file():
            pov_path.unlink()
            print(f"  removed temp scene {pov_path.relative_to(REPO_ROOT)}")


def install_assets(png_paths: list[Path]) -> None:
    PACKAGE_PARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    for src in png_paths:
        dest = PACKAGE_PARTICLES_DIR / src.name
        shutil.copy2(src, dest)
        print(f"  installed {dest.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render magnetar particle sphere sprites with POV-Ray."
    )
    parser.add_argument(
        "--povray",
        default=None,
        help="Path to the povray executable (default: search PATH)",
    )
    parser.add_argument(
        "--install-assets",
        action="store_true",
        help=(
            "Also copy PNGs into python/magnetar/assets/particles/ "
            "(off by default — refine renders before installing)"
        ),
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=sorted(PARTICLE_PRESETS),
        help="Render only these named presets (default: all)",
    )
    args = parser.parse_args(argv)

    if not TEMPLATE_PATH.is_file():
        raise SystemExit(f"missing template: {TEMPLATE_PATH}")
    if not FONT_TTF.is_file():
        print(f"note: font not found at {FONT_TTF} (ok for sphere-only pass)", file=sys.stderr)

    ensure_work_dirs()
    povray = find_povray(args.povray)
    template = load_template()

    names = args.only if args.only else list(PARTICLE_PRESETS)
    pngs: list[Path] = []
    for name in names:
        color = PARTICLE_PRESETS[name]
        pngs.append(
            render_one(
                povray=povray,
                name=name,
                sphere_color=color,
                template=template,
                quality_extra=[],
            )
        )

    if args.install_assets:
        print("Installing into package assets…")
        install_assets(pngs)
    else:
        print("Skipped package install (pass --install-assets to copy into assets/particles/).")

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
