# BehindLiveWindowException in Media3 live streams

## Why the player falls out of the window
A live stream exposes a sliding window of segments. After a long pause, a slow network, or time in
the background, playback can fall behind the oldest segment still available. The player then
reports `ERROR_CODE_BEHIND_LIVE_WINDOW`.

## Rejoining the live edge
In `Player.Listener.onPlayerError`, check for that error code, call `seekToDefaultPosition()`,
then `prepare()`. A longer window on the server or a smaller target offset on the client makes it
rarer.
