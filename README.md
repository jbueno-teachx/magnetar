# magnetar

Electric and magnetic particle simulator in 3D space, with a pygame-ce 2D view
and an interactive terminal prompt.

## Requirements

- Python 3.14+
- A display for the pygame window

## Setup

```bash
# using the project env
source env314/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
python -m magnetar
# or
magnetar
```

Terminal commands while the window is open:

```
magnetar> help
magnetar> add electro 1 0 0
magnetar> add pinned 0 1 0 2
magnetar> list
magnetar> clear
magnetar> quit
```

## Layout

```
python/magnetar/
  __main__.py     # python -m magnetar
  app.py          # view constants + pygame main loop
  world.py        # 3D particle space
  particles.py    # particle types
  prompt.py       # interactive stdin commands
```

Rust (`Cargo.toml`, `src/`) is reserved for a later performance port; the
active path is pure Python.

## OpenGL

This system has Mesa/NVIDIA libGL and pygame can open an `OPENGL` display.
Optional: `pip install -e ".[opengl]"` for PyOpenGL bindings. The default view
uses the software 2D surface path for now.
