#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Drive POV-Ray to pre-render magnetar particle sprites.

Run only from a full project checkout (not from an installed wheel).

Why ``"%(key)s" %% mapping`` instead of Jinja2 / str.format?
------------------------------------------------------------
POV-Ray SDL uses curly braces heavily. Old-style ``%%`` mapping only treats
``%(key)s`` as placeholders, so the scene source stays readable.

Animation / light orbit
-----------------------
Light motion is **inside** the ``.pov`` template via ``frame_number`` and
``vaxis_rotate`` (composed with a fixed Z ``vrotate``). Python does not compute
sin/cos for the light path.

One filled ``.pov`` is written per **color**; POV-Ray is invoked once with
``+KFI0 +KFF{N-1}`` so all frames of that color share the same scene file.
Outputs are renamed to ``particle_{color}_f{NNN}.png`` for the image bank.

Work dirs (gitignored; keep ``.gitkeep``)
-----------------------------------------
* ``tmp_pov/``    — one filled scene per color (removed after that color finishes)
* ``tmp_render/`` — intermediate PNGs

Install
-------
* ``--install-assets`` — after render, copy PNGs into package assets
* ``--install-only``  — copy existing ``tmp_render`` PNGs only (no POV-Ray)
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATE_PATH = SCRIPT_DIR / "particle.template.pov"
TMP_POV_DIR = SCRIPT_DIR / "tmp_pov"
TMP_RENDER_DIR = SCRIPT_DIR / "tmp_render"
FONT_TTF = REPO_ROOT / "python" / "magnetar" / "assets" / "fonts" / "IBMPlexSans-Bold.ttf"
PACKAGE_PARTICLES_DIR = REPO_ROOT / "python" / "magnetar" / "assets" / "particles"

WIDTH = 256
HEIGHT = 256
NUM_FRAMES = 8

PARTICLE_PRESETS: dict[str, str] = {
    "yellow": "rgb <1.0, 0.9, 0.15>",
    "light_blue": "rgb <0, 0.5, 1.0>",
    "red": "rgb <1.0, 0.2, 0.15>",
    "green": "rgb <0.2, 0.85, 0.3>",
}


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def fill_template(template: str, *, sphere_color: str, num_frames: int) -> str:
    return template % {
        "sphere_color": sphere_color,
        "num_frames": str(int(num_frames)),
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


def _normalize_frame_outputs(color: str, num_frames: int) -> list[Path]:
    """Map POV-Ray's frame-numbered outputs to particle_{color}_f{NNN}.png."""
    final_paths: list[Path] = []
    # POV-Ray inserts the frame number before the extension; padding varies.
    # Common patterns: name0.png, name00.png, name000.png, name1.png, …
    candidates_by_frame: dict[int, Path] = {}
    prefix = f"particle_{color}_f"
    for path in TMP_RENDER_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        name = path.name
        if not name.startswith(prefix):
            continue
        # particle_yellow_f000.png (already good) or particle_yellow_f0.png / f00.png
        m = re.match(rf"^particle_{re.escape(color)}_f(\d+)\.png$", name, re.I)
        if not m:
            continue
        frame = int(m.group(1))
        if 0 <= frame < num_frames:
            candidates_by_frame[frame] = path

    if len(candidates_by_frame) < num_frames:
        # Some POV builds use a bare stem + digits without our zero pad.
        # Also match particle_yellow_f7.png after +Oparticle_yellow_f.png
        pass

    for frame in range(num_frames):
        src = candidates_by_frame.get(frame)
        if src is None:
            raise SystemExit(
                f"missing rendered frame {frame} for {color!r} in {TMP_RENDER_DIR} "
                f"(found: {sorted(p.name for p in TMP_RENDER_DIR.glob(f'particle_{color}_f*.png'))})"
            )
        dest = TMP_RENDER_DIR / f"particle_{color}_f{frame:03d}.png"
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            src.rename(dest)
        final_paths.append(dest)
    return final_paths


def render_color(
    *,
    povray: str,
    name: str,
    sphere_color: str,
    template: str,
    num_frames: int,
    display: bool = False,
) -> list[Path]:
    """One .pov per color; POV-Ray animation emits all frames."""
    filled = fill_template(template, sphere_color=sphere_color, num_frames=num_frames)
    pov_path = TMP_POV_DIR / f"particle_{name}.pov"
    pov_path.write_text(filled, encoding="utf-8")

    # Output stem: POV-Ray inserts frame numbers before the extension.
    out_stem = TMP_RENDER_DIR / f"particle_{name}_f.png"
    last_frame = num_frames - 1
    cmd = [
        povray,
        f"+I{pov_path}",
        f"+O{out_stem}",
        f"+W{WIDTH}",
        f"+H{HEIGHT}",
        "+FN",
        "+UA",
        "+D" if display else "-D",
        "+A0.3",
        f"+KFI{0}",
        f"+KFF{last_frame}",
    ]
    print(" ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"povray failed for {name!r} (exit {proc.returncode})")
        return _normalize_frame_outputs(name, num_frames)
    finally:
        if pov_path.is_file():
            pov_path.unlink()
            print(f"  removed temp scene {pov_path.relative_to(REPO_ROOT)}")


def collect_render_pngs() -> list[Path]:
    """All particle frame PNGs currently in tmp_render (normalized names)."""
    paths = sorted(TMP_RENDER_DIR.glob("particle_*_f*.png"))
    # Prefer zero-padded fNNN; still include any fN.png if present
    return [p for p in paths if p.is_file()]


def install_assets(png_paths: list[Path] | None = None) -> int:
    """Copy rendered PNGs into python/magnetar/assets/particles/."""
    PACKAGE_PARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    if png_paths is None:
        png_paths = collect_render_pngs()
    if not png_paths:
        raise SystemExit(
            f"no PNGs to install under {TMP_RENDER_DIR} "
            f"(render first, or check particle_*_f*.png names)"
        )
    n = 0
    for src in png_paths:
        dest = PACKAGE_PARTICLES_DIR / src.name
        shutil.copy2(src, dest)
        print(f"  installed {dest.relative_to(REPO_ROOT)}")
        n += 1
    return n


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
        help="After rendering, copy PNGs into python/magnetar/assets/particles/",
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help=(
            "Only copy existing tmp_render/particle_*_f*.png into package assets; "
            "do not run POV-Ray"
        ),
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=sorted(PARTICLE_PRESETS),
        help="Render only these named presets (default: all)",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show POV-Ray's render window (+D); default is off (-D)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=NUM_FRAMES,
        help=f"Animation frame count (default {NUM_FRAMES})",
    )
    args = parser.parse_args(argv)

    ensure_work_dirs()

    if args.install_only:
        print("Install-only: copying tmp_render → package assets (no render)…")
        n = install_assets()
        print(f"done ({n} files).")
        return 0

    if not TEMPLATE_PATH.is_file():
        raise SystemExit(f"missing template: {TEMPLATE_PATH}")
    if not FONT_TTF.is_file():
        print(f"note: font not found at {FONT_TTF} (ok for sphere-only pass)", file=sys.stderr)

    num_frames = max(1, int(args.frames))
    povray = find_povray(args.povray)
    template = load_template()
    names = args.only if args.only else list(PARTICLE_PRESETS)

    pngs: list[Path] = []
    for name in names:
        color = PARTICLE_PRESETS[name]
        print(f"=== {name}: {num_frames} frames (one scene file) ===")
        pngs.extend(
            render_color(
                povray=povray,
                name=name,
                sphere_color=color,
                template=template,
                num_frames=num_frames,
                display=args.display,
            )
        )

    if args.install_assets:
        print("Installing into package assets…")
        install_assets(pngs)
    else:
        print("Skipped package install (pass --install-assets or --install-only).")

    print(f"done ({len(names)} colors × {num_frames} frames = {len(pngs)} images).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
