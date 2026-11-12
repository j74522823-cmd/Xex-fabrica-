// IDs e constantes do Bad Ice-Cream, tirados do bytecode AS3 (TileGrid, Level.addItems, Walker).
#pragma once
namespace bic {
constexpr int TILE_SIZE = 36;        // Level.TILE_SIZE
constexpr int FIRST_TILE_TYPE = 32;  // id do XML - 32 = índice em kTileNames
constexpr int WALKER_SPEED = 3;      // Walker.moveSpeed (px por quadro, 12 quadros por tile)

enum Direction { DIR_NONE = 0, DIR_LEFT = 1, DIR_RIGHT = 2, DIR_UP = 3, DIR_DOWN = 4 };  // Walker.LEFT/RIGHT/UP/DOWN

// Tipos de item do <i> (Level.addItems).
enum ItemType {
    ITEM_PLAYER1 = 1, ITEM_PLAYER2 = 2,
    ITEM_BANANAS = 3, ITEM_LEMON, ITEM_ORANGE, ITEM_GRAPES, ITEM_WATERMELON, ITEM_KIWI, ITEM_STRAWBERRY, ITEM_PEAR,
    ITEM_PINEAPPLE, ITEM_CHERRIES,                                                   // 3..12 frutas
    ITEM_SIMPLE1 = 13, ITEM_SIMPLE2, ITEM_SIMPLE3, ITEM_SIMPLE4,                      // 13..16
    ITEM_BREAKER_BLUE = 17, ITEM_BREAKER_GREEN, ITEM_BREAKER_YELLOW,                  // 17..19
    ITEM_FLYING = 20, ITEM_LOG_ENEMY = 21, ITEM_TOWER = 22, ITEM_CHASER = 23,         // 20..23
    ITEM_ARROW_LEFT = 24, ITEM_ARROW_RIGHT, ITEM_ARROW_UP, ITEM_ARROW_DOWN,           // 24..27
    ITEM_CAMPFIRE = 28, ITEM_FLAMEPAD = 29, ITEM_INVISIBLE_TILE = 30, ITEM_ICE = 31   // 28..31
};

// Nome do sprite de cada tile (índice = id - FIRST_TILE_TYPE). 0 = BlockTile (sólido), 1 = LandTile (chão).
// Tile id 32 = BlockTile, 33 = chão; ids 0 = célula coberta por um objeto grande vizinho.
inline const char* const kTileNames[] = {
    "BlockTile", "LandTile", "BigTree", "BigWell", "BrickBlockBlue", "BrickBlockRed", "BrickBlockYellow", "CubedLog",
    "FourBlue", "FourRed", "FourYellow", "OneBlue", "OneBlueHole", "OneRed", "OneRedHole", "OneYellow", "OneYellowHole",
    "StripedBlock1", "StripedBlock2", "StripedBlock3", "TwoBlue", "TwoRed", "TwoTallBlue", "TwoTallRed", "TwoTallYellow",
    "TwoYellow", "Hut1", "Hut2", "Igloo", "LargeGroundHole", "LargeSnowMound", "LittleTree", "Log", "LogsLeft",
    "LogsMiddle", "LogsRight", "LogsSingle", "MedGroundHole", "MeltedSnow1", "MeltedSnow2", "MeltedSnow3", "MeltedSnow4",
    "MeltedSnow5", "MeltedSnow6", "MeltedSnow7", "MeltedSnow8", "MeltedSnow9", "MeltedSnow10", "MeltedSnow11",
    "MeltedSnow12", "SideSnowLeft", "SideSnowRight", "SmallGroundHole", "SmallSnowMound", "SnowSprig", "SnowySideLeft",
    "SnowySideRight", "Stones1", "Stones2", "Stones3", "PoleTree", "SmokeStackBlue", "SmokeStackYellow", "Snowman",
    "Campfire"};
constexpr int kTileNameCount = sizeof(kTileNames) / sizeof(kTileNames[0]);
}  // namespace bic
