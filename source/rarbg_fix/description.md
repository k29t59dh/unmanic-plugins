
---
#### Description:

This plugin recalculates framerates in RARBG H265 MP4s to correct stuttering playback on Apple devices.

Background:
The miscalculation was due to a bug in the software encoder and affected all RARBG H265s for a period of time.

Details:
ffmpeg won't recalculate framerate when converting, so we use mkvtoolnix.
But mkvtoolnix strips container tags with multiple streams, which we don't want.

So the conversion goes as follows:
1. Use ffmpeg to split the mp4 into audio and video mkvs
2. Use mkvtoolnix to process each single-stream mkv, forcing frame-rate recalculation
3. Recombine the corrected streams back into an mp4

---
###### Note:
This plugin requires mkvtoolnix.

For docker run the following command manually or in your startup script:

    /usr/bin/apt-get update; /usr/bin/apt-get install -y mkvtoolnix
