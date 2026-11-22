# Audio output changes: headphones and Bluetooth

## Pausing when headphones are unplugged
When wired or Bluetooth headphones disconnect, output falls back to the speaker. Listen for
`ACTION_AUDIO_BECOMING_NOISY` and pause, or let Media3 do it with
`setHandleAudioBecomingNoisy(true)`.

## Bluetooth output latency
Bluetooth headsets add tens to hundreds of milliseconds of output delay. A player that schedules
video from the timestamps the audio sink reports stays in sync; one that counts written bytes
does not. Test lip sync on a Bluetooth headset, not only on the speaker.
