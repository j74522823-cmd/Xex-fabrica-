# tools/motion — RE4 (GameCube) skeletal motion export

`tools/motion_export.py` reads every "FCV" motion the game can hand to `MotionSetCore`: the
character archives (`files/em/plNN.drs` players, `emNN.drs` enemies, `wepNN.drs` weapon modules),
the yz2-compressed room archives (`files/St*/rNNN.das`, decompressed by `yz2.py`) with the etc
archives nested in them (`ETM`), the cutscene data (`files/Evd/*.evd`), the sub screen data
(`files/ss/*/*.dat`) and the raw `.fcv` / `.eff` files — on both discs — plays them with the
**game's own code** compiled for the host, and writes glTF 2.0 (and BVH) animations on the model's
parts hierarchy for Blender, with the whole character (body, head, hair, eyes, hands ... as the game
assembles it) skinned and textured from the model `.bin` ("BIN") and texture palette ("TPL")
entries, and the heads' face morphs as shape keys.

    python3 tools/motion_export.py list   files/em/pl00.drs            # or the disc .iso, a rNNN.das, a rNNNsMM.evd, a ss_oc101.dat
    python3 tools/motion_export.py list   orig/G4BE08/re4_debug_disc1.iso orig/G4BE08/re4_debug_disc2.gcm --character leon   # everything Leon plays
    python3 tools/motion_export.py list   orig/G4BE08/re4_debug_disc1.iso orig/G4BE08/re4_debug_disc2.gcm --all-sources      # the inventory
    python3 tools/motion_export.py export files/em/pl00.drs --motion 46 -o leon_046.gltf --bvh leon_046.bvh   # full Leon
    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso --archive em10.drs --motion 46 -o ganado.gltf
    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso --archive em10.drs --motion 665 --character leon -o kick.gltf  # Leon's kick on a stunned Ganado
    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso --archive r100.das --motion 42 --character leon -o r100_042.gltf
    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso --archive r100s03.evd --motion pl0000_s03_000.fcv --character leon -o ev.gltf  # a cutscene motion
    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso --archive r400.das --motion pl00017.fcv --character leon -o ladder.gltf   # a room ETM motion
    python3 tools/motion_export.py export files/em/pl00.drs --all -o out/          # every motion
    python3 tools/motion_export.py export ... --blender-check /tmp/mot/render [--strip]  # headless Blender import + renders
    python3 tools/motion_export.py export ... --blender-check --render-nice /tmp/mot/render   # + lit EEVEE renders
    python3 tools/motion_export.py verify orig/G4BE08/re4_debug_disc1.iso orig/G4BE08/re4_debug_disc2.gcm [--dump dump.bin | --dolphin]

`--motion N` is the archive entry index (the game's `PL_ARC` index is `N + 4`: the container body
starts with four header words); a named entry (an event bin, a room ETM file) is given by its file
name. One command exports the whole character: the body `.bin` with its
palette and the attachment models the game's set-up code hangs on the same parts (the table in
`character.py`, below). `--body-only` leaves the attachments out; `--mesh [stem:]BIN[:[stem:]TPL]`
adds a model (or replaces the palette of a table entry; `stem:` names another archive of the
source: the disc, or a `.drs` / `.das` next to the given one). An archive that is not in the table
exports the body only and says so. `--no-mesh` writes the skeleton with the old stick-figure
placeholder. `--character leon` (`ada`, `hunk`, `krauser`, `wesker`, or a `plNN` stem) plays the
motion on that player's body with its attachments whatever archive the motion is in (`--model
pl00:0` is the same thing by hand); an archive without a default body (a room) needs one of the
two. Units: game millimetres × `--scale` (default 0.001 → metres), Y up, 30 fps.

## Where the motions come from

`MotionSetCore(model, work, data, seq, ...)` (`src/game/motion.cpp`) is the only way a motion is
played; `cModel::motionSet`, `cPlayer::motionSet`, `cEmWrap::motionSet`, `cMot3::set`, the
`*BlendMotSet` / `MotSetObj*` wrappers, `PlRegistMotion` (fills `m_MotTbl2`), the `cEm10::set*Motion`
setters and the weapon modules' `PSet(pl->m_MotTbl[n], WEP_ARC_PTR(m))` fills all end in it;
`CameraControl::MotionSet` plays the same format on the camera. `gen_refs.py` scans every call in
`src/` (2371 call sites, 3015 constant references resolved, 192 left with a run-time pointer:
object work fields filled by a room's table walk, the debug tools) and writes `refs.py`; the
`data` pointer of every call resolves to one of these archive classes:

| class (how `data` is obtained) | disc files | exported |
|---|---|---|
| `PL_ARC_PTR(pG->pPlayer, n)`, `PL_ARC(n)`, `m_MotTbl` (weapon modules fill it), `m_MotTbl2` (rooms) | `em/plNN.drs` (`ReadPlayerData`: pl00/08/09/10 Leon, pl01/05 Ashley, pl0b/0c Ada, pl06 HUNK, pl0a Krauser, pl0d Wesker) | yes |
| `PL_ARC_PTR(em->subArc, n)`, `ARC(n)`, `pl->subArc = em->subArc` in the grab / ride / door routines (the melee, the boat and jet ski pl0e/pl0f, the partner pl11/pl14) | `em/emNN.drs`, `em/plNN.drs` (`EmFileTbl*`) | yes, attributed per player (`list --character`) |
| `WEP_ARC_PTR(n)` = `pG->pWep` | `em/wepNN.drs` (`ReadWepData`, `wep_data_<player>` tables) | yes, per weapon and player |
| `ROOM_ARC_PTR(pG->pRoom, n)`, `PlRegistMotion`, `cEm10::setEvtMotion`, the objects' motion tables | `St1/St2/St4/rNNN.das` (disc 1), `St3/rNNN.das` (disc 2 only) | yes |
| `GetEtcAddr(arc, "pl00017.fcv")` (EtcModel.cpp: ladders, doors, windows) | the rooms' `ETM` entry: a named-file archive nested in the .das | yes (`ETM/` entries) |
| `EvtMgr.GetBin(name)` -> `Event::ExePacket_Mot` / `ExePacket_Cam` / `ShapeSet` | `Evd/rNNNsMM.evd` (87 disc 1, 61 disc 2): named bins `<room>/<cut>/<model>/*.fcv`, `cam/*.fcv` (camera), `<model>/face/*.fcv` (ShapeData) | yes |
| `SS_ARC_PTR(arc, n)` (Sscrn: codec screen, inventory models, weapon display) | `ss/cmn/ss_ocNNN.dat`, `ss_wepNN.dat`, `ss/<lang>/ss_cmmn.dat`, `ss_term.dat` (bare container bodies) | yes |
| `EspGetEfmMotAddr` (esp_efm.cpp: effect models) | the `EFF` data's effect-model motion tables (core.das, rooms, ETM `.eff`, event `.eff`, `etc/<lang>/*.eff`) | read; the only 3 entries (`r10b.das` EFF efm 124) are not MotionData |
| `cSmd::getMotPtr` (scroll.cpp: scroll models) | the `SMD` entries' motion tables (rooms, `St1/r100_NN.dat`) | read; every SMD motion table on both discs is empty |
| `ARC_PTR(pG->pCore)` (`etc/core.das`) | `etc/core.das` | no FCV in it (models, TPLs, camera / light data) |
| `op/opNN.das` (ss_term.cpp `OP_ARC_PTR`) | 13 `MDT` + 13 "SEQ" per file: the codec conversation blocks, not `MotionSeqKey` tables | listed, excluded from the SEQ round-trip |
| `ss/<lang>/tel*.fcv` (4 raw MotionData files) | not referenced by any code on the disc | yes |
| debug tools (`db_mod.cpp` motion viewer, `t_motseq`, `db_port`) | `HDReadDebugAlloc("Room/Em/mot_tbl.txt")`, `x:/soft/room/`: the developers' host disk, not on the disc | — |

Every other file on both discs was checked: the ハカセ containers, bare bodies, events, yz2 streams
and the nested `ETM` / `EFF` / `SMD` are parsed, and every remaining blob (`Rel/*.rel`, `etc/*.esl`,
`ss/Item/*`, `font/`, the `CAM` / `LIT` / `MDT` / `ITM` ... room entries) was brute-force scanned for
MotionData headers at 32-byte alignment: none. `Movie/*.sfd` and `bgm/` are video and audio.

Disc 2 (`re4_debug_disc2.gcm`): the 42 `St3` rooms and 59 events are its own, `em/`, `ss/`, `etc/`,
`op/` and `St4/` are byte-identical to disc 1 (847 identical files, only `opening.bnr` differs).
Totals: disc 1 15128 FCV entries (em 9273, rooms 358 + 205 in ETM + 3 in EFF, events 5111, sub screen
178), disc 2 13468 (rooms 325 + 75 in ETM, events 3617); both discs deduplicated 18961 FCV entries:
1775 event camera motions (1038 + 752, two events are on both discs), 1502 event face shape tables
(878 + 634) and 15684 skeletal motions (5389 of them cutscene motions in 146 events),
18946 byte-identical round-trips (`verify`). The 15 that do not round-trip: the 12 malformed rifle /
pl14 archive entries below and the 3 EFF entries of r10b. All 6574 `SEQ` tables round-trip (the
ETM `.seq` files included).

Format variants met on the way (all byte-exact in `fcv.py` / `meshbin.py`): the event bins and ETM
files pad motions, sequences and models with 0x00 instead of 0xCD (`fill`); the event camera
motions carry a zero size word (`size_word`; `MotionSetCore` steps over it) and flag bits 14-15 of
`maxFrame` (`frame_flags`, masked by the game); their type-15 key blocks (f32 values without
tangents) start 4-aligned; the four raw `tel*.fcv` files end at the last key without the padding
their size word counts; 27 event TPL bins are 32-byte 0x20-filled placeholders; the ETM textures
include 2x2 ones (one tile, round-tripped uncropped).

`list --character leon` prints, per archive, every motion Leon can play with the function that
plays it: the player archive, the melee table, the enemy / vehicle archives the grab and ride
routines play on him, the weapon modules (with the `m_MotTbl` slot each fill goes through), the
rooms' `ROOM_ARC_PTR` motions on the player, the rooms' `ETM/pl00NNN.fcv` ladder motions, the
event bins under `pl00NN/`, and the sub screen's codec motions. `list --all-sources` prints the
inventory per file and per tag.

## The melee motions: two archives

The routines that play the player's melee moves (`plem10Kick`, `plem10Kick2`, `plem10FS`,
`plem10KneeKick`, `plem10NeckBreak`, `plem10Showtay` in `em10/em10.cpp`) set
`pl->subArc = em->subArc` and play `PL_ARC_PTR(pl->subArc, N)`: the motion is an entry of the caught
Ganado's archive, `em10.drs` (for Ada too), not of the player's. The exception is the kick on a
kneeling Ganado: `em10KneeDownAction` sets `r_no_3 = 1` and `plem10Kick` plays
`PL_ARC_PTR(pG->pPlayer, 0x25)` from the player's own archive. On a stunned standing Ganado
`em10KickAction` enters through `SetPlDamage`, which clears `r_no_3`, and the kick is em10's 0x29D,
the same motion for every player. Entry indices (`--motion`), with the prompt the game shows:

| player | kneeling Ganado | standing Ganado | other |
|---|---|---|---|
| Leon pl00 | own 33 (`ACT_KICK`) | em10:665 (`ACT_KICK`) | em10:210 suplex |
| Ada pl0b / pl0c | own 33 (`ACT_BACKKICK`) | em10:665 (`ACT_SENPUU`) | em10:210 suplex |
| HUNK pl06 | own 33 (`ACT_KICK`) | em10:693 neck break (`ACT_EXECUTE`) | em10:210 suplex |
| Krauser pl0a | — | em10:665 + SEQ em10:666 (`plem10Kick2`) | em10:688 knee kick |
| Wesker pl0d | own 33 (`ACT_NERICHAGI`) | em10:688 palm strike (`ACT_PALM_SHOCK`) | em10:210 suplex |

`character.MELEE` holds the table; `list --character` prints it with the other motions. On the PS2
disc Ada's Ganados load archives of their own (`EmFileTbl_Ada`: `ema0.dat` for em10), so her
standing kick there is `0672_ema0:665` (below).

## The PS2 disc

`list`, `export` and `verify` also read the PS2 disc (the one whose `SLPS_000.00` is the ELF
`tools/ps2sym.py` reads). Its files are packed in `DATA/BIO4DAT.AFS`; the `.dat` archives there are
the GameCube's container bodies little-endian and uncompressed, and the motions, sequence tables and
room ETM files are the GameCube layouts byte-swapped. The game addresses a file by its AFS index
(`EMD_READ_SET::Dat`) and names repeat across the language sets, so an archive is named after its
index: `0672_ema0.dat`. Models, textures, EFF and SMD data have other layouts and are not read, so a
PS2 motion plays on a GameCube body, without the joints of parts the body lacks (the PS2 Ada
skeleton adds parts 90-97):

    python3 tools/motion_export.py export orig/G4BE08/re4_debug_disc1.iso ps2.iso --archive 0672_ema0.dat --motion 665 --character ada -o ada_kick.gltf

`verify`: 18683 of 18684 FCV entries and all 12867 sequence tables round-trip; the one left,
`2433_r229:27`, is the GameCube's big-endian motion copied unconverted.

## The `.das` archives (yz2)

`St1/St2/St4/rNNN.das` (85 rooms on disc 1), `St3/rNNN.das` (42 rooms on disc 2), `etc/*.das` and
`op/*.das` are the same ﾊｶｾ container as the
`.drs` files; a room's type-0 body is a **yz2** stream: a text header `"<packed hex>\t<unpacked
hex>\n"` (`Yz2DecodeSet`, `strtoul` twice), the coded bytes from the next 32-byte boundary after
the second number, the body record `packed + 0x24` bytes long. `etc/core.das` and `memcard.das`
store the body raw. `archive.py` decompresses the body (`yz2.py`) and re-assembles the container
so `.das` entries read like `.drs` ones; a room decompresses in about 2 s in pure Python.

`yz2.py` is a port of `src/game/yz2code.cpp` (set-up) and the instructions of
`src/game/yz2asm.cpp` (the decode loop; label names cited in the module docstring), an adaptive
range coder over an LZ dictionary:

- Coder (`FrequencyDecode_Decode`, `.L_801D4058`): state `R` (primed 0x80) and `C` (the first
  byte); renormalise by 1 / 2 / 3 bytes when `R` ≤ 0x800000 / 0x8000 / 0x80; `step = R >> 14`,
  `value = C / step`, symbol = the cumulative slot holding `value` (the asm's 0x8000-entry lookup
  table = a bisect on the cumulative starts), `C -= step * start`, `R = (step * freq) >> 1`. The
  cumulative table always totals 0x8000.
- Models (`Yz2Freq`): `freq[i]++` per symbol; at `total == 1 << bits` (bits ≤ 14) the cumulative
  table is rebuilt as `freq << (15 - bits)` and `bits++` (`.L_801D415C`); at bits 15 and
  `total > 0x7FFF` the table takes the unhalved counts, then `freq >>= 1` where > 1
  (`.L_801D41BC`). Initial cumulative table: 0x8000 counts dealt round-robin (`MODEL_SETUP`);
  `freq` reset to 1 (`FREQ_RESET`).
- Symbols (`yz2Decode_loop`): main model of 0x500. `s ≥ 0x400`: literal `s & 0xFF`.
  `s < 0x400`: a run from the dictionary of the byte before the run (`ctx = *r21`), slot
  `(s + cnt) & 0x1FF` of its 512-entry ring (`cnt` = next write slot, so `s & 0x1FF = 0x1FF` is
  the newest); `0x200 ≤ s ≤ 0x3FF` (`yz2Decode_L02`) takes pointer and length from the slot,
  `s ≤ 0x1FF` (`yz2Decode_L01`) the pointer only, the length from the 0x100-symbol side model:
  `t > 2` → `t - 1`; `t = 2 / 1 / 0` → a 16 / 24 / 32-bit big-endian value from further side
  symbols, minus 1.
- Dictionary (`yz2Decode_dic_set`): after every literal or run, if the scan pointer is behind the
  last byte written, `dic[*scan].ptr[cnt] = scan + 1`, `.len[cnt] = length`, `cnt = (cnt + 1) &
  0x1FF`, `scan = last`. So every run (and every literal, length 1) is entered under the byte that
  preceded it. `Yz2DicEnt` is `{u32 cnt; u32 ptr[0x200]; u32 len[0x200]}` (0x1004 bytes).

How it is verified (the asm cannot run on the host; the oracles are structural and external):

1. Every `.das` on both discs (132: 127 rooms + core + memcard + 3 op, 127 yz2-compressed) decompresses to exactly the header's
   unpacked size with the coder 1–3 bytes short of the packed size (the encoder's flush), and
   parses as a container whose entry table is consistent (`drs.Drs`: offsets ascending, 0x20-aligned,
   within the body; tags 3 upper-case letters) — `verify` counts this.
2. The entries pass the same byte round-trips as the `.drs` ones: rooms hold 358 FCV, 154 SEQ,
   88 BIN, 87 TPL; 358 / 154 / 88 / 87 re-serialise byte-identically (the two room models with a
   `WeightExt` table, r10c:27 = r22a:27, made `meshbin.py` learn that 12-byte weight record). A
   single wrong output byte breaks a motion's key offsets or a model's section layout.
3. External oracle: 74 room entries (1.19 MB: NPC models r100:32–37 = pl07:0–4, motions r104:41 =
   pl00:74, em2b models ...) are byte-identical to entries of the uncompressed `em/*.drs`, and 449
   entries occur byte-identically in two or more rooms, i.e. independent yz2 streams decode to the
   same bytes.
   `core.das` fails 3 entries and `memcard.das` 1 for format reasons (model version 0x2c020202,
   CLUT / format 5 / 6 textures), not decompression: their bodies are raw.

## The character table (`character.py`)

Read off the players' `setModel` / `setRightHand` / `setLeftHand` (the state before the weapon
module runs) and the Ganado's `em10ModelInit`; `verify` checks that every entry loads from the disc.
`bin:tpl` are archive entry indices (PL_ARC − 4).

| archive | character | models (role bin:tpl) | source |
|---|---|---|---|
| pl00 | Leon | body 0:1, costume 6:1, face 9:1, head 4:3, hair 2:3, eyes 5:3, right hand 14:13, left hand 17:13 | `cPlLeon::setModel` (PL_ARC 4/5, 0xA/5, 0xD/5, 8/7, 6/7, 9/7), `setRightHand(0)` 0x12/0x11, `setLeftHand(1)` 0x15/0x11 |
| pl01 | Ashley | body 0:1, head 3:5, hair 2:7, skirt 4:1, accessory 6:1, right hand 13:1, left hand 16:1 | `cPlAshley::setModel` (4/5, 7/9, 6/0xB, 8/5, 0xA/5), `setRightHand(0)` 0x11/5, `setLeftHand(0)` 0x14/5 |
| pl0c | Ada (playable) | body 0:1, hair 2:3, head 4:3, eyes 5:6, right hand 13:1, left hand 14:1 | `cPlAda::setModel` (4/5, 6/7, 8/7, 9/0xA), `setRightHand(0)` 0x11/5, `setLeftHand(0)` 0x12/5 |
| pl02 | Ada (event, red dress) | body 0:1, hair 2:3, eyes/face 5:6 | same code; entry 13 is empty, 14 wants texture 6 of the 5-texture palette, and the "head" entry 4 is a 29-vertex stub without a shape table rigged to a 67-part skeleton whose parts 7 is the body's upper arm (it floats beside the shoulder in the game's own skinning) - left out; the body has the hands modelled in |
| pl0d | Wesker | body 0:1, costume 6:1, head 4:3, hair 2:3, right hand 14:13, left hand 16:13 | `cPlWesker::setModel`, `setRightHand(0)` 0x12/0x11, `setLeftHand(0)` 0x14/0x11 |
| pl06 | HUNK | body 0:1, mask 2:3, right hand 14:13, left hand 17:13 | `cPlHunk::setModel`, `setRightHand(0)`, `setLeftHand(1)` 0x15/0x11 |
| pl0a | Krauser | body 0:1, hair 2:3, head 4:5, face 10:5, accessory 11:12, right hand 14:13, left hand 16:13 | `cPlKlauser::setModel` (the be_flag &= ~8 models 0xA/0xB and the 0x18/0x19 glow are hidden: not exported) |
| em10 | Ganado (village, type 0) | body 440:441, head 442:441, right hand 444:441, left hand 449:441 | `em10ModelInit` + `Em10Set` type 0 (mot[1]/mot[0] = ARC 0x1BC/0x1BD), `em10HeadSet(0)` mot[2]/mot[5], `em10HandSet(0)` mot[6], mot[11] with mot[0] |

Hands and the weapon module: the default handgun modules (wep01 FN57, wep02 Mauser) do not touch the
hands (`Wep01_init` creates the weapon object only), so the bare hands of the player archive are the
default state. The other modules replace the right hand with their grip hand:
`cPlBody::initWepHand(WEP_ARC_PTR(0xA))` + `setRightHand(1)` draws `wepNN.drs` entry 6 with the
player's hand palette (`PL_ARC_PTR(pG->pPlayer, 0x11)` = pl00:13) — a cross-archive pair, e.g.
`--mesh wep04:6:13 --mesh 20:13` for Leon holding the shotgun (`wep04.cpp`: `setLeftHand(4)` =
0x18). The eye / eyelid parts (0x1C, 0x20, 0x21) are skeleton parts the game turns by code
(`cPlayer::moveEyeNormal`), not by the motion, so the eye models are bound through the skin like
everything else and stay at rest here.

## The mesh export

`meshbin.py` parses the model `.bin` (`include/model.h` ModelData, the section offsets that
`calcModelAddr` in `game/model.cpp` relocates) and `gxtex.py` the TPL; `gltf.py` writes one glTF
mesh per `.bin`, one primitive per `ModelPart` (its GX display list), skinned to the armature.
What each array means comes from the game's draw path, `game/trans.cpp`:

- `commonModelTrans` sets the vertex descriptor: position / normal / texcoord (and colour when
  flags bit31) all `GX_INDEX16`; positions `GX_S16` with `frac = shift` (value / 2^shift mm,
  `dbmodule.cpp DrawObjWireframe` uses the same `1 / (1 << shift)`), normals `GX_S8` (flags bit29)
  or `GX_S16`, texcoords `GX_S16` frac 8, colours `GX_RGBA8`. A display-list vertex is therefore
  four u16 indices (position, normal, colour, texcoord); opcodes on the disc: 0x80 quads, 0x90
  triangles, 0x98 strips (vertex format 0 only), 0x00 NOPs pad the list to 32 bytes. Every model on
  the disc has the colour array; the game's lighting ignores it (`trans_lit.cpp`: material source
  = register unless flags bit30, never set), it is exported as `COLOR_0` anyway.
- Skinning (`commonScreenMatSub`): `calcWeightMat` builds `mtx[k]` = parts k world matrix × bind
  matrix (`cParts::lt_inv_mat`, the inverse of the rest-pose world translation) relative to parts 0;
  `MakeWeightPalette` blends them per `Weight {u8 id[3], num, wht[4] %}` entry (the last weight
  takes `1 - sum`); `CalcSk1_x` multiplies each vertex (`s16 x, y, z, s16 matrix index`, 8 bytes)
  by `palette[matrix index]`, the normals (`s8 x, y, z, u8 index`) likewise. So the vertices are
  rest-pose model-space positions and the export is plain glTF linear-blend skinning:
  `JOINTS_0 / WEIGHTS_0` = the Weight entry's (parts, weight) pairs (≤ 3), inverse bind matrices
  from the rest pose (the same skin the bones already used). Rigid attachment models
  (`weight_palette_num <= 1 && nParts == 1`, drawn from the original arrays on
  `getPartsPtr(pHead->partsNo)`) fall out as single-joint weights. `WeightExt` (`{u16 idx[3],
  u16 num, u8 weight[4]}` × `weight_ext_num` when that is > 0xFF, `MakeWeightPaletteExt`) occurs
  in one room model (r10c:27 = r22a:27, 275 entries) and is read the same way.
- Materials: `materialSetup` binds `ModelPart.texId` on TEX0 (`GXSetTexCoordGen2(..., GX_TG_TEX0)`,
  identity matrix, `GX_REPEAT` from the TPL headers); `alphaSetup` (part flags bit2) multiplies the
  alpha of `alphaTex` in and alpha-compares `alpha > alphaRef` → glTF `MASK` with cutoff
  `(alphaRef + 1) / 255`, the alpha texture's alpha composed into the base PNG. Bump (flags bit0,
  `bumpTex`, indirect stage), specular / environment stages and texture blend tables are not
  exported (recorded in the primitive's `extras.re4`). Triangle winding: the GX order is
  counter-clockwise towards the vertex normals on every disc model checked (0 to 9 disagreeing
  faces per model), so it is kept as the glTF front face.
- Textures (`gxtex.py`): TPL descriptors → `GXInitTexObj` fields. Formats on the disc: CMPR (2159
  textures in em/*.drs + 161 in the rooms), IA8 (373 + 17), I4 (244 + 25); decoded to RGBA8 PNGs in `textures/` next to the output
  (`<archive>_<tpl entry>_<tex id>[_a<alpha id>].png`, shared by the motions of an archive). CMPR
  follows Dolphin's decoder (8×8 tiles of four DXT1 blocks, indices MSB first, 5/8-3/8 blend,
  transparent black fourth colour); only the base mip level is decoded (9 textures have mips).
- Morph targets (`ModelData::shapeOfs`, `game/shape.cpp`): the head models carry a shape table,
  `u32 count` then `count × ShapeEntry {u32 ofs, s32 num}` (offsets from `shapeOfs + 4`, the lists
  back to back) and per shape `num × {s16 vertex index, s16 dx, dy, dz}` in the vertex units
  (`1 / (1 << shift)` mm). Every frame `commonScreenMatSub` copies `vtxOrig` into the vertex buffer
  (`ResetShape`) and `CalculateShape_new` adds `weight × delta` for each of the five shape slots
  (`weight` = the ShapeData channel's Hermite key in percent / 100, ×1.37 for `shapeFlags` bit 3),
  before the skinning; the normals are not touched. Each shape becomes a glTF POSITION morph
  target on every primitive of the head mesh (named `shape_NN` in `extras.targetNames`: the game has
  no names; Blender shows them as shape keys), so shape key 1.0 = the game's 100 %. Which key is
  which: `cPlLeon::setFace(1)` plays PL_ARC 0x62 (channel on shape 0, the pain face), `setFace(2)`
  0x63 (shape 1); Ada (pl0c) has one shape; Ashley's two are played by the events. On the disc 12
  of 1830 em models have a shape table (22 keys: pl00/08/09/10 and em32 Leon heads, pl01/05/11/15/21
  Ashley, pl0b/0c Ada), deltas at most 19.7 mm (Ashley's open mouth); one room model (r206:50) has 26 keys.

Verified by:

1. **Byte round-trip** (`verify`): every `BIN` on both discs (5117 of 5118: 1830 players, enemies and
   weapons, the rooms', the ETM files', the sub screen's and the events' models; the one left is
   core.das's version-0x2c020202 model) parses into vertices, normals, colours, texcoords, weights, parts headers, display-list
   primitives, shape table, blend and flip tables and re-serialises to identical bytes, with the
   zero / 0xCD padding and the shape entries' offsets regenerated (not copied), the colour and
   texcoord counts taken from the display lists (the padding after them must be zero), and every
   vertex index (display lists and shape deltas) range-checked. Every TPL parses (3506 palettes,
   9647 textures decoded, both discs); the lossless formats re-encode byte-identically (2530 of 2530 I4 / IA8). The raw-bodied `etc/core.das` / `memcard.das`
   hold one model of another version (0x2c020202) and CLUT / format 5 / 6 textures, which are not read.
   CMPR is lossy: checked by eye on Leon's jacket / face textures. Every entry of the character
   table loads from the disc (45 of 45).
2. **Blender** (`--blender-check`): asserts the mesh objects are exactly the exporter's models
   (names) with its vertex and triangle counts, are skinned to the armature, have UVs, colours and
   node materials with the images; that the shape keys are exactly the head's morph targets, each
   moving some vertices and none by more than 60 mm; that the deformed mesh stays inside the
   bones' bounding box + 25 % at the sampled frames (an exploded vertex or a stretched limb fails
   it); renders textured (workbench, `color_type='TEXTURE'`); `--strip` renders every frame at the
   motion's fps into `<name>_strip.png` and `<name>.mp4` (ffmpeg). `--render-nice DIR` adds EEVEE
   renders with three area lights (key / fill / rim scaled to the character's height) and the
   camera framed on the skinned mesh's bounding box over the motion (`<name>_nice_fNNN.png`, first
   and middle frame), plus a head close-up per shape key at 1.0 and the neutral head
   (`<name>_nice_<mesh>_shape_NN.png`).

Known gaps: TEV materials (bump / specular / texture-blend stages, the indirect stage) and mip
levels are not exported, only the base texture with the alpha test; of the room archives only the
BIN / TPL / FCV / SEQ entries are understood (CAM, SAT, LIT, SMD, ... are listed with their size);
12 motions do not round-trip (below); the enemy table covers the
village Ganado (em10 type 0) only: the other Ganado types / enemies pair their heads and hands in
their `emNN_set.cpp` (`--mesh` for those); the game turns the eye parts by code, so exported eyes
look straight ahead; one duplicated face in pl00:4 is dropped (Blender removes it on import). The
host helper is built with `make` in `host/`; on Windows that needs a C++ toolchain (MSYS2 / MSVC).

## What is verified, and how

1. **Byte round-trip of the parse** (`verify`): every FCV and SEQ entry is parsed into keys
   (`fcv.py`) and re-serialised; the bytes must be identical, including the size word, the
   exporter's joint block order and the padding. Both discs: 18946 of 18961 FCV entries (9273 in em/*.drs, 615 in the
   rooms + 226 in their ETM files + 3 in an EFF, 8666 in the events, 178 in the sub screen; see "Where the motions come from")
   and all 6574 sequence tables. The 12 archive failures are named: 11 weapon motions (wep09/10/21/24/31/32/47) whose
   last attach-camera joints (channel 6) have key blocks in the padding, at the end, or on a
   duplicated offset, and pl14:8 (a 1-joint stub whose key block is padding); the game only
   evaluates channel-6 joints with an attach camera set. See "Malformed motions" below.
2. **The evaluation is the game's code** (`host/`): `src/game/motion.cpp` (MotionSetCore,
   MotionMove, MotionMoveCore, HermiteInterpolation, Fcc_get_data_*), `src/game/ik.cpp`
   (IKInit, InverseKinematics), `cModel::partsMatCalc/partsWorldCalc/getPartsPtr/matBlend` from
   `model.cpp`, `hermite/RotMatrix/TransMatrix/ScaleMatrix/VecRadLimit/SetOrientation*/VecAngle`
   from `math_sub.cpp`, `GetDistance3` from `sub2.cpp`, the SDK's C `MTX/VEC/QUAT` routines
   (`src/lib`) under the `PS*` names, and the game's libm `sinf/cosf/acosf` (`src/lib` fdlibm).
   `host/prepare.py` writes host copies into `host/build/` (register pins `asm("rN")` stripped,
   `(u32)` pointer casts widened to `uintptr_t`, the `MOT_HIST` byte-offset macro turned into the
   member access; functions extracted verbatim by name). The game tree is not edited. Stub headers
   (`host/stub/`) supply the 32-bit types and a `cModel` with the members the code uses; offsets
   differ from the GameCube layout, so the offset macros of `motion.h` (`MOTION_PARTS`, `IK_PARTS`,
   `PARTS_BIND_MAT`) are redirected to members. Hand-written: the driver (`motion_host.cpp`), the
   log / camera / floor stubs, and C versions of the paired-single-only `SQRTF` (frsqrte + Newton
   in the game; correctly rounded sqrt here) and `LIMIT_ANGLE`.
   The motion image is handed to the helper little-endian (same layout, fields byte-swapped, from
   `fcv.serialise(m, '<')`) so the game's byte-wise readers produce the GameCube values; it lives in
   memory below 4 GB (`MAP_32BIT`) because MotionSetCore relocates the key offsets as 32-bit
   pointers. Python (`evalhost.py`) builds the cModel from the `.bin` parts records exactly like
   `cModel::initJoint` (rest positions, parent links, bind matrices, blend table), calls
   MotionSetCore(flags 0) and, per frame, MotionMove with the sequence frame forced (Mot_attr
   0x8000). So the poses include the IK (effector position keys: the feet/hands, no floor on the
   host) and the double-joint quaternion blends, as in the game.

   **For anyone writing their own importer:** the position keys on the IK end effectors (ankles,
   hands; chain roots have kind bit 0x10/0x20) are targets in model space for `ik.cpp`'s solver,
   not the joint's own translation. Reading them as bone translations gives stretched or folded
   limbs — the usual failure of RE4 animation importers. Either run the IK (this tool does) or
   drop those keys and accept approximate limbs. Details in `fcv.py`'s header.
   `make fma` builds a variant with `-mfma -ffp-contract=fast` (fused multiply-adds like the PowerPC
   `fmadds`); `--fma` selects it.
3. **Check against the real game** (`dolphin.py`): `verify --dolphin` boots the debug disc in
   headless `dolphin-emu-nogui` (one instance under `timeout`, no window, no audio), drives the pad
   through Dolphin's Pipe input until the player model plays a motion, and dumps the player's
   `MotionWork` and parts (`pPL` = `*0x803159F4`, `cModel::Motion` at +0x1D8, parts chain at +0xF4)
   from the emulated MEM1 (read through `/proc/<pid>/mem`, the 32 MiB shared mapping). The motion
   playing is identified from `MotionWork::pMot - PL_DATA_ADDR (0x807EC000)` = the body offset of
   the FCV entry. `verify --dump file.bin` compares an existing dump (layout in `dolphin.py`
   `DUMP_LAYOUT`) with the helper's pose at the same frame and prints the max abs error of
   `ang/pos/scale`, `l_mat`, `mat` per parts class (motion keys only / IK chains + blend-table
   joints / parts no motion joint drives). Result on the opening event motion (pl00 entry 117,
   frames 12..70, `--fma-too`): key-driven angles differ by <= 6e-8 rad (0 with the FMA build),
   positions by <= 6.1e-5 mm (1 ULP at 1000 mm), world matrices by 1-2 ULP of the world
   coordinates (~1e5 mm); IK / blend parts by <= 2.3e-2 mm (frsqrte-based normalisation in the
   game); the head's eye/face parts differ because pl_leon poses them outside the motion.
4. **Blender** (`export --blender-check [dir]`): `blender -b --python blender_check.py` imports the
   glTF, asserts the bone count and the action frame range, compares bone world positions with the
   helper's parts world positions at four frames, checks the mesh (above), and renders four frames
   (workbench, textured).

## Malformed motions on the disc (the rifle modules)

The only motion data on disc 1 that does not round-trip is in the two rifle modules and their
byte copies: `wep09:28` (bolt-action rifle), `wep10:16` and `wep10:28` (semi-auto rifle), and the
same entries in `wep21`/`wep24` (= wep09) and `wep31`/`wep32`/`wep47` (= wep10); plus `pl14:8`, a
one-joint stub. `wep10:16` is the semi-auto's draw animation (`pl_rifle.cpp` `WEP_ARC_PTR(0x14)`);
`:28` is archive slot 0x20 (not referenced by `pl_rifle.cpp`). In each, the last joints are tagged
for attach-camera channel 6 (`kind` word bits 8-11 = 6, e.g. `0xa602`) and their key blocks are
broken: a key count of 16401 that runs past the end of the blob, an offset at or past the end, or a
duplicate of another joint's offset.

The GameCube never touches them. `MotionMoveCore` (`src/game/motion.cpp`, the `ch == 6 || ch == 7`
branch) skips channel-6/7 joints unless the MotionWork has an attach camera (`pAttachCam`, set by
event cameras attached to a motion), and the player has none while handling a rifle. So the data is
inert on GC; an evaluator that walks every joint of the blob (a re-implementation, or a port that
dropped the channel test) would read garbage there. `verify` prints the 12 entries with the reason
each fails.

## Files

    motion_export.py   CLI (tools/)
    fcv.py             MotionData / sequence table parse + byte-exact serialise (format notes in the docstring)
    modelbin.py        model .bin parts hierarchy, rest pose, blend table
    meshbin.py         model .bin mesh data: arrays, weights, display lists, shape table; byte-exact serialise (format notes in the docstring)
    character.py       archive -> attachment models (bin, tpl, role) read off the game's setModel code; MELEE: the
                       player's melee motions per archive (em10.drs / own) from the em10 routines; PLAYER_TYPE /
                       SS_MOTIONS and the per-player queries over refs.py (list --character)
    gen_refs.py        scans src/ for every motion-setting call and writes refs.py: archive class + entry per call,
                       function, model; the read.cpp file tables; the weapon module unit lists (run after editing src/)
    refs.py            generated by gen_refs.py
    gxtex.py           TPL parse, CMPR / IA8 / I4 decode, I4 / IA8 encode, PNG writer
    archive.py         every container kind: .drs / .das (tools/drs.py, a .das body decompressed first), bare bodies (ss/*.dat),
                       events (.evd), raw .fcv / .eff; the nested ETM / EFF / SMD entries; disc extraction via dtk (both discs);
                       the PS2 disc (ISO9660 -> BIO4DAT.AFS -> little-endian .dat bodies)
    yz2.py             Capcom's yz2 decompressor (adaptive range coder + 256 x 512 run dictionary), from yz2code/yz2asm
    evalhost.py        ctypes front end: Player (hosted cModel), Pose
    gltf.py, bvh.py    writers (gltf: skin, meshes, morph targets, materials, animation)
    dolphin.py         Dolphin harness, memory dump format, comparison
    blender_check.py   headless Blender import / compare / render
    host/              Makefile, prepare.py, motion_host.cpp, stub/ -> build/libmotion_host*.so
