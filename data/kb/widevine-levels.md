# Widevine security levels and HD playback

Widevine has security levels: L1 (decryption and decoding inside a hardware trusted
environment) and L3 (software only). Content owners commonly restrict HD and higher
renditions to L1, so the same app may get only SD on an L3 device.

Checks:
- Read `MediaDrm(WIDEVINE_UUID).getPropertyString("securityLevel")`.
- A device can drop from L1 to L3 after an unlocked bootloader or a failed keybox
  provisioning; the license server then refuses HD keys.
- Log the license request and response status to tell a policy refusal apart from a
  network or provisioning error.
