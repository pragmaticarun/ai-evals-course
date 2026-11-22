# Surfaces and the video pipeline

## Releasing a surface too early
A decoder renders into a `Surface`. If the view that owns it is destroyed while the codec still
renders, decoding fails or the app crashes. Stop or reconfigure the codec, or call
`setOutputSurface`, before the surface goes away.

## SurfaceView or TextureView
`SurfaceView` hands frames to the display compositor directly: lower power, and required for
secure and many HDR paths. `TextureView` behaves like a normal view and supports animation, at the
cost of a GPU copy.
