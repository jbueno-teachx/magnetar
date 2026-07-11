// magnetar particle sprite template
// Placeholders use Python old-style percent-mapping (see render_particles.py).
// Example placeholder: sphere pigment color key "sphere_color".
#version 3.7;
global_settings { assumed_gamma 1.0 }

camera {
  location <0, 0, -2.7>
  look_at  <0, 0, 0>
  // Default right is ~4:3; without this, square (+W=+H) renders squash spheres into eggs.
  // image_width / image_height come from the POV-Ray CLI (+W / +H).
  right x * image_width / image_height
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
