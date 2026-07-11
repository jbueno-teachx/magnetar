// magnetar particle sprite template
// Placeholders use Python old-style percent-mapping (see render_particles.py).
// Example placeholder: sphere pigment color key "sphere_color".
#version 3.7;
global_settings { assumed_gamma 1.0 }

camera {
  location <0, 0, -4>
  look_at  <0, 0, 0>
}

// White point light
light_source {
  <-2, 4, -2>
  color rgb <1, 1, 1>
}

// Fully transparent background (pair with POV-Ray +UA for PNG alpha)
background {
  color rgbt <0, 0, 0, 1>
}

sphere {
  <0, 0, 0>, 1
  pigment { color %(sphere_color)s }
  finish {
    ambient 0.3
    phong 0.5
  }
}
