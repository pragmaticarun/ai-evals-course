# Recording HDR video with the camera

## Camera support
HDR capture depends on the camera: on API 33 and later, `DynamicRangeProfiles` lists the profiles
a camera supports, such as HLG10 or HDR10.

## Encoding the recording
HDR recordings need a 10-bit encoder profile, for example `HEVCProfileMain10HDR10`, and correct
colour metadata in the output file. Playback problems with HDR files are covered separately.
