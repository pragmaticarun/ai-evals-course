# Audio keeps playing over calls or other apps (audio focus)

Android coordinates audio between apps with audio focus. An app that never requests focus,
or ignores focus loss, keeps playing over navigation prompts, calls, or other media.

Fix:
- With Media3, pass suitable `AudioAttributes` and `handleAudioFocus = true` to
  `ExoPlayer.setAudioAttributes(...)`; the player then requests focus, ducks, and pauses for you.
- Without Media3, request focus with an `AudioFocusRequest` (API 26+) and react to
  `AUDIOFOCUS_LOSS`, `AUDIOFOCUS_LOSS_TRANSIENT`, and `AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK`.
- Also handle `ACTION_AUDIO_BECOMING_NOISY` to pause when headphones are unplugged.
