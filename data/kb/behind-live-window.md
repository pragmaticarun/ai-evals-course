# BehindLiveWindowException in Media3 / ExoPlayer live streams

A live stream exposes a sliding window of segments. If playback falls further behind than
the window (long pause, slow network, app in the background), the segments it needs are gone
and the player raises a `BehindLiveWindowException`, surfaced as a `PlaybackException` with
error code `ERROR_CODE_BEHIND_LIVE_WINDOW`.

Fix: in `Player.Listener.onPlayerError`, check for that error code, then call
`player.seekToDefaultPosition()` followed by `player.prepare()` to rejoin at the live edge.
Consider a longer live window on the server or a smaller target live offset on the client.
