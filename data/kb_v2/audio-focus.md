# Audio keeps playing over calls or other apps (audio focus)

## Why it happens
Android shares the speaker between apps through audio focus. A player that never asks for focus,
or ignores losing it, keeps playing over phone calls, navigation prompts, and other media.

## Letting Media3 manage focus
Pass suitable `AudioAttributes` with `handleAudioFocus = true` to `ExoPlayer.setAudioAttributes`.
The player then requests focus when playback starts, lowers its volume when it may duck, and
pauses when another app takes over.

## Managing focus yourself
Build an `AudioFocusRequest` (API 26 and later) and call `AudioManager.requestAudioFocus`. In the
listener, pause on `AUDIOFOCUS_LOSS_TRANSIENT`, stop on `AUDIOFOCUS_LOSS`, and duck on
`AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK`.
