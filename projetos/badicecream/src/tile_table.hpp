// GERADO por tools/gen_tiles.py -- não editar.
#pragma once
namespace bic {
struct TileInfo { bool free; int fw, fh; };  // pegada em células (a partir do canto sup. esq.)
inline const TileInfo kTileInfo[] = {
    {false, 1, 1},  // BlockTile
    {true, 1, 1},  // LandTile
    {false, 2, 2},  // BigTree
    {false, 2, 2},  // BigWell
    {false, 1, 1},  // BrickBlockBlue
    {false, 1, 1},  // BrickBlockRed
    {false, 1, 1},  // BrickBlockYellow
    {false, 1, 1},  // CubedLog
    {false, 2, 2},  // FourBlue
    {false, 2, 2},  // FourRed
    {false, 2, 2},  // FourYellow
    {false, 1, 1},  // OneBlue
    {false, 1, 1},  // OneBlueHole
    {false, 1, 1},  // OneRed
    {false, 1, 1},  // OneRedHole
    {false, 1, 1},  // OneYellow
    {false, 1, 1},  // OneYellowHole
    {false, 1, 1},  // StripedBlock1
    {false, 1, 1},  // StripedBlock2
    {false, 1, 1},  // StripedBlock3
    {false, 2, 1},  // TwoBlue
    {false, 2, 1},  // TwoRed
    {false, 1, 2},  // TwoTallBlue
    {false, 1, 2},  // TwoTallRed
    {false, 1, 2},  // TwoTallYellow
    {false, 2, 1},  // TwoYellow
    {false, 6, 3},  // Hut1
    {false, 5, 3},  // Hut2
    {false, 4, 4},  // Igloo
    {true, 4, 3},  // LargeGroundHole
    {true, 4, 2},  // LargeSnowMound
    {false, 1, 1},  // LittleTree
    {false, 1, 1},  // Log
    {false, 1, 1},  // LogsLeft
    {false, 1, 1},  // LogsMiddle
    {false, 1, 1},  // LogsRight
    {false, 1, 1},  // LogsSingle
    {true, 2, 2},  // MedGroundHole
    {true, 1, 1},  // MeltedSnow1
    {true, 1, 1},  // MeltedSnow2
    {true, 1, 1},  // MeltedSnow3
    {true, 1, 1},  // MeltedSnow4
    {true, 1, 1},  // MeltedSnow5
    {true, 1, 1},  // MeltedSnow6
    {true, 1, 1},  // MeltedSnow7
    {true, 1, 1},  // MeltedSnow8
    {true, 1, 1},  // MeltedSnow9
    {true, 1, 1},  // MeltedSnow10
    {true, 1, 1},  // MeltedSnow11
    {true, 1, 1},  // MeltedSnow12
    {true, 1, 1},  // SideSnowLeft
    {true, 1, 1},  // SideSnowRight
    {true, 1, 1},  // SmallGroundHole
    {true, 1, 1},  // SmallSnowMound
    {true, 1, 1},  // SnowSprig
    {true, 1, 1},  // SnowySideLeft
    {true, 1, 1},  // SnowySideRight
    {true, 1, 1},  // Stones1
    {true, 1, 1},  // Stones2
    {true, 1, 1},  // Stones3
    {false, 1, 1},  // PoleTree
    {false, 2, 1},  // SmokeStackBlue
    {false, 2, 1},  // SmokeStackYellow
    {false, 3, 1},  // Snowman
    {false, 1, 1},  // Campfire
};
}  // namespace bic
