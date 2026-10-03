# Third-party code and sources

`patches/howdy-gdm-unlock-only.patch` targets commit
`d3ab99382f88f043d15f15c1450ab69433892a1c` of [boltgolt/howdy](https://github.com/boltgolt/howdy).
The patch context and configuration structure come from that project; its MIT license is at [LICENSES/Howdy-MIT.txt](LICENSES/Howdy-MIT.txt).

Howdy, dlib, OpenCV, NumPy and the dlib pretrained models are each governed by their own licenses. The installation steps in these notes fetch them from upstream; this repository does not distribute their binary build artifacts or model weights.

The handling of GDM caller sessions is based on `gdm-session-worker.c` and `gdm-manager.c` of [GNOME/gdm](https://github.com/GNOME/gdm); the documents link back to the original project.
