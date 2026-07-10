# magnetar — TODO

## Simulation core

- [ ] Implement **Coulomb** and **Maxwell** acceleration laws properly for particles  
  (the simulation core itself — fields → force → acceleration → motion).

## Rendering / assets

- [ ] Pre-render **3D-ish particle sprites** with **POV-Ray**  
  - Output lives under the package `assets/` folder once ready.

## Interactive prompt

- [ ] Migrate the prompt **in-game** via a custom **text-entry widget** (no separate stdin TTY required for normal use).
- [ ] Improve the **DSL** accepted by the prompt (richer commands, clearer syntax, better errors).
