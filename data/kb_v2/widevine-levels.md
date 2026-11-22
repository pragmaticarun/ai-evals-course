# Widevine security levels and HD playback

## L1 and L3
At L1, decryption and decoding happen inside a hardware trusted environment; at L3 they happen in
software. Content owners commonly allow HD and above only on L1, so an L3 device gets SD.

## Checking the level
Read `MediaDrm(WIDEVINE_UUID).getPropertyString("securityLevel")`. A device can drop to L3 after
its bootloader is unlocked, and the license server then refuses HD keys.
