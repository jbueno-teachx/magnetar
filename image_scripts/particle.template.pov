// magnetar particle sprite template
// Python old-style percent-mapping fills: sphere_color, num_frames
// (see render_particles.py). Light orbit uses POV-Ray frame_number.
#version 3.7;
global_settings { assumed_gamma 1.0 }

camera {
  location <0, 0, -2.7>
  look_at  <0, 0, 0>
  // Default right is ~4:3; without this, square (+W=+H) renders squash spheres into eggs.
  right x * image_width / image_height
}

// --- animated point light ---------------------------------------------------
// Frame 0: Light0 = <-2, 4, -2>
// Frame NumFrames/2: antipode <2, -4, 2> (180 deg about OrbitAxis)
//
// Compose: fixed rotation about +Z, then varying rotation about OrbitAxis
// (perpendicular to the fixed-oriented light vector). POV-Ray vector ops only.
#declare NumFrames = %(num_frames)s;
#declare Light0 = <-2, 4, -2>;
#declare FixedZDeg = 0;
#declare LightBase = vrotate(Light0, <0, 0, FixedZDeg>);
#declare OrbitAxis = vnormalize(vcross(LightBase, y));
#declare LightAngle = frame_number * (360 / NumFrames);
#declare LightPos = vaxis_rotate(LightBase, OrbitAxis, LightAngle);

light_source {
  LightPos
  color rgb <1, 1, 1>
}

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
