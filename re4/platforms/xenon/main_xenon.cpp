// Xbox 360 entry point for the RE4 port: initialises Aurora (window, GX, DVD, PAD, CARD) and then hands over to the
// game's own main (src/game/main.cpp), which boots the SDK itself on the GameCube.
//
// TODO (see docs/360-port.md, "Next steps"):
//   1. aurora_initialize(...) with the config the Dusklight port uses (platforms/xenon in dusklight-xenon).
//   2. Point Aurora's DVD at the debug disc image(s) (disc 1 + disc 2 as a single FST; disc swap not needed).
//   3. Call the game's entry and run its scheduler each frame between GX frames.
int main(int, char**) { return 0; }
