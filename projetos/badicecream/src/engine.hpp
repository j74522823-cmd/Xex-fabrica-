// Núcleo de simulação do Bad Ice-Cream (portável: sem I/O, sem STL pesada, estilo C++11 compatível com C++17).
// Regras derivadas do bytecode AS3 (ver docs/RULES.md). O núcleo NÃO sabe desenhar nem tocar som:
// a plataforma (Xbox 360 / host) lê o estado público e esvazia a fila de sons.
#pragma once
#include <cstdint>
#include <vector>
#include "game_ids.hpp"
#include "level_loader.hpp"
#include "tile_table.hpp"

namespace bic {

constexpr int FPS = 25;          // inferido da fórmula do bônus de tempo (25 * 121); confirmar no cabeçalho do SWF
constexpr int SCREEN = 550;      // palco 550x550
constexpr int INF = 1000000000;

// Estado de um controle, preenchido pela plataforma a cada quadro.
struct PadState {
    bool connected = false;
    bool left = false, right = false, up = false, down = false, shoot = false;
    bool start = false, back = false;   // menus (não usados pelo núcleo)
};

struct Rng {
    uint32_t s;
    explicit Rng(uint32_t seed = 12345) : s(seed ? seed : 1) {}
    uint32_t next() { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }
    float f() { return (next() & 0xFFFFFF) / 16777216.0f; }
    int range(int n) { return n <= 0 ? 0 : (int)(next() % (uint32_t)n); }
};

enum Phase { PHASE_PLAYING, PHASE_WON, PHASE_LOST };
enum IceState { ICE_ADD, ICE_STATIC, ICE_BREAK, ICE_QUICKBREAK, ICE_MELT, ICE_GONE };

struct Walker {
    int tx = 0, ty = 0;           // tile de destino (a ocupação muda assim que o passo começa, como no original)
    float x = 0, y = 0;           // canto superior esquerdo da célula, em pixels (desenhar em x - ox, y - oy)
    int moveDir = 0, lastDir = DIR_DOWN;
    float speed = 3;
};

struct Ice { int x = 0, y = 0, state = ICE_ADD, timer = 0; };
struct Ray { int owner = 0, dx = 0, dy = 0, cx = 0, cy = 0, dir = 0, range = 0, timer = 0; bool adding = false, checkAdding = true, dead = false; };

struct Player : Walker {
    int num = 1;                   // slot do jogador: 1 ou 2
    int characterId = 0;           // 0..7: baunilha, morango, chocolate, sorbet, menta, chiclete, alcaçuz, bacon
    bool present = false, dead = false;
    int deadFrames = 0, turnTimer = 0, shootTimer = 0, score = 0;
    bool shootFrame = false, shootBreak = false, shootChecked = false, spaceKey = false;
    int animFrame = 0;             // contador para a camada de desenho
    Player() { speed = 6; }
};

enum EnemyKind { EK_SIMPLE, EK_BREAKER, EK_FLYING, EK_LOG, EK_TOWER, EK_CHASER };
struct Enemy : Walker {
    int itemType = 0, kind = EK_SIMPLE;
    bool randomWalk = true, rightTurn = false, chase = false;
    int randomTurnTimer = 0, animFrame = 0;
    // Breaker
    bool breaking = false; int breakDir = 0, breakFrame = 0;
    // Flying (pato)
    bool flying = false; int jumpFrame = 0, jumpDir = 0, hesitate = 0; float fx0 = 0, fy0 = 0, fx1 = 0, fy1 = 0;
    // Log
    bool rolling = false; int trans = 0; bool transStart = false;
    // Tower
    int moves = 0, tpState = 0, tpTimer = 0;   // tpState: 0 normal, 1 saindo, 2 entrando
    // Chaser
    int chaseTimer = 0, chasing = -1, chState = 0, chTimer = 0; bool followP2Next = false;
};

struct Fruit : Walker {
    int itemType = 0;
    bool visible = false, collected = false, appearing = false;
    int appearTimer = 0, collectTimer = 0, tpTimer = 0, tpState = 0, animFrame = 0;
    bool jumping = false; int jumpFrame = 0; float jx0 = 0, jy0 = 0, jx1 = 0, jy1 = 0;
    int randomTurnTimer = 0;
};

struct Obj { int type = 0, x = 0, y = 0, state = 0, timer = 0; };  // seta, fogueira, flamepad, tile invisível
enum CampState { CAMP_LIT, CAMP_UNLIT, CAMP_LIGHTING };

class World {
public:
    // Inicia uma fase. coop = true cria o jogador 2 (a plataforma decide: segundo controle conectado).
    bool load(const LevelData& lvl, bool coop, uint32_t seed = 1);
    void update(const PadState pads[2]);   // um quadro (1/FPS s)
    // Sons pendentes (nomes originais do SoundManager). A plataforma deve chamar clearSounds() depois de tocar.
    std::vector<const char*> sounds;
    void clearSounds() { sounds.clear(); }

    // --- estado público (leitura pela camada de desenho) ---
    int w = 0, h = 0, frameNumber = 0, endFrame = 0, phase = PHASE_PLAYING, stage = -1, winTime = 0, levelScore = 0;
    int curWave = -1, finishTimer = 0;   // curWave: índice em kWaveOrder; finishTimer > 0 = fase concluída, contando 50 quadros
    bool coop = false;
    float cameraX = 0, cameraY = 0;
    std::vector<int> tileId;          // id original do XML por célula
    std::vector<uint8_t> wall;
    Player players[2];
    std::vector<Enemy> enemies;
    std::vector<Fruit> fruits;
    std::vector<Obj> objs;
    std::vector<Ice> ices;
    std::vector<Ray> rays;
    bool isWallPublic(int x, int y) const { return isWall(x, y); }
    int iceAt(int x, int y) const { return inb(x, y) ? iceIdx[y * w + x] : -1; }
    bool inb(int x, int y) const { return x >= 0 && y >= 0 && x < w && y < h; }
    int timeBonus() const;

private:
    Rng rng;
    std::vector<int> iceIdx;
    std::vector<int> pathNum, jumpNum, seeNum, p1Num, p2Num;
    bool pathDirty = true;
    int anyAliveDeathFrames = 0;

    // utilidades
    void snd(const char* n) { sounds.push_back(n); }
    bool isWall(int x, int y) const { return !inb(x, y) || wall[y * w + x]; }
    const Obj* objAt(int type, int x, int y) const;
    bool playerAliveAt(int x, int y) const;
    bool enemyAt(int x, int y, const Enemy* ignore) const;
    bool canWalk(const Walker& wk, int dir, bool isPlayer, const Enemy* self) const;
    bool freeCell(int x, int y) const;       // sem parede, gelo, jogador vivo ou inimigo
    bool movement(Walker& wk);               // true quando chegou ao tile
    void startWalk(Walker& wk, int dir);
    void placeAt(Walker& wk, int tx, int ty);

    // gelo e raio
    void addIce(int x, int y, int state);
    void breakIce(int idx, bool quick);
    void meltIce(int idx);
    void updateIce();
    void updateRays();
    void spawnRay(const Player& p, int dir);

    // caminhos
    void findPath();
    void spfa(std::vector<int>& d, int mode, int seedMask);

    // entidades
    void updatePlayer(Player& p, const PadState& pad, int idx);
    void killPlayer(Player& p);
    void onPlayerStepped(Player& p);
    void updateObjs();
    void updateEnemy(Enemy& e);
    void enemyStepped(Enemy& e);
    void randomWalkStep(Enemy& e);
    int  descend(const Enemy& e, const std::vector<int>& field, int cur) const;
    void enemyWalk(Enemy& e, int dir);
    void breakerBreak(Enemy& e);
    void updateFruits();
    void fruitStepped(Fruit& f);
    void fruitRandomWalk(Fruit& f);
    bool fruitCanWalk(const Fruit& f, int dir) const;
    void advanceStage();
    void updateCamera();
    int  nearestFrontIce(const Player& p) const;
    int  cellCost(int x, int y, int mode) const;
    int  fieldDir(const Walker& wk, const std::vector<int>& f, int mode, bool jump) const;
    int  randomDir(const Walker& wk, bool isEnemy, bool allowBack);
    bool tpTarget(int& ox, int& oy);
    void startWave();
    void collide();
    void collect(Fruit& f, Player& p);
    bool anyPlayerAlive() const;
    bool fruitHere(int x, int y) const;
    void tickTimersAndRays();
};

}  // namespace bic
