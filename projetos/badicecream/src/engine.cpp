// Núcleo de simulação do Bad Ice-Cream (ver engine.hpp). Regras: docs/NOT_FINISH_YET.md + bytecode AS3.
// Tudo o que está marcado [SUPOSIÇÃO] não foi confirmado no bytecode.
#include "engine.hpp"

#include <algorithm>
#include <cmath>
#include <deque>

namespace bic {

namespace {
const int DX[5] = {0, -1, 1, 0, 0};
const int DY[5] = {0, 0, 0, -1, 1};
const int OPP[5] = {0, DIR_RIGHT, DIR_LEFT, DIR_DOWN, DIR_UP};
const int RIGHT_OF[5] = {0, DIR_UP, DIR_DOWN, DIR_RIGHT, DIR_LEFT};  // virar à direita estando virado para d
const int LEFT_OF[5] = {0, DIR_DOWN, DIR_UP, DIR_LEFT, DIR_RIGHT};

// Ordem das ondas de fruta (item do XML). NOT_FINISH_YET.md: Bananas, Cherries, Grapes, Kiwi, Lemon, Orange, Pear, Pineapple, Strawberry, Watermelon.
const int kWaveOrder[10] = {ITEM_BANANAS, ITEM_CHERRIES, ITEM_GRAPES, ITEM_KIWI, ITEM_LEMON,
                            ITEM_ORANGE,  ITEM_PEAR,     ITEM_PINEAPPLE, ITEM_STRAWBERRY, ITEM_WATERMELON};

const int ICE_ADD_FRAMES = 16, ICE_BREAK_FRAMES = 29, ICE_QUICK_FRAMES = 12, ICE_MELT_FRAMES = 46;
const int FRUIT_SCORE = 50, WIN_DELAY = 50, APPEAR_FRAMES = 20, COLLECT_FRAMES = 16;
const int CAMP_RELIGHT_WAIT = 100, CAMP_LIGHTING_FRAMES = 48;

inline int sgn(float v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }
}  // namespace

int World::timeBonus() const {
    // [SUPOSIÇÃO] a fórmula original usa 25 * 121 (segundos restantes de 121); o multiplicador 10 não foi confirmado.
    int left = (121 * FPS - frameNumber) / FPS;
    return left > 0 ? left * 10 : 0;
}

// ---------------------------------------------------------------- carga

bool World::load(const LevelData& lvl, bool coopMode, uint32_t seed) {
    *this = World();
    rng = Rng(seed);
    w = lvl.w; h = lvl.h; coop = coopMode;
    tileId = lvl.tiles;
    wall.assign(w * h, 0);
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            int id = tileId[y * w + x];
            if (id < FIRST_TILE_TYPE) continue;  // 0 = coberto por objeto grande (a pegada é marcada pelo objeto) ou chão
            int k = id - FIRST_TILE_TYPE;
            if (k >= kTileNameCount) { wall[y * w + x] = 1; continue; }
            const TileInfo& ti = kTileInfo[k];
            if (ti.free) continue;
            for (int yy = y; yy < std::min(h, y + ti.fh); yy++)
                for (int xx = x; xx < std::min(w, x + ti.fw); xx++) wall[yy * w + xx] = 1;
        }
    iceIdx.assign(w * h, -1);
    pathNum.assign(w * h, INF); seeNum = jumpNum = p1Num = p2Num = pathNum;

    for (const LevelItem& it : lvl.items) {
        int t = it.type, x = it.x, y = it.y;
        if (!inb(x, y)) continue;
        if (t == ITEM_PLAYER1 || t == ITEM_PLAYER2) {
            Player& p = players[t - 1];
            p.num = t; p.present = (t == 1) || coop; p.dead = false;
            p.tx = x; p.ty = y; p.x = x * TILE_SIZE; p.y = y * TILE_SIZE; p.speed = 6; p.lastDir = DIR_DOWN;
        } else if (t >= ITEM_BANANAS && t <= ITEM_CHERRIES) {
            Fruit f; f.itemType = t; f.tx = x; f.ty = y; f.x = x * TILE_SIZE; f.y = y * TILE_SIZE;
            f.speed = 3;
            if (t == ITEM_KIWI || t == ITEM_PEAR) f.speed = 2;
            if (t == ITEM_STRAWBERRY) f.speed = 1.5f;
            f.lastDir = DIR_DOWN;
            fruits.push_back(f);
        } else if (t >= ITEM_SIMPLE1 && t <= ITEM_CHASER) {
            Enemy e; e.itemType = t; e.tx = x; e.ty = y; e.x = x * TILE_SIZE; e.y = y * TILE_SIZE;
            e.lastDir = DIR_DOWN; e.speed = 3;
            switch (t) {
                case ITEM_SIMPLE1: e.kind = EK_SIMPLE; e.speed = 1.5f; e.rightTurn = true; e.randomWalk = false; break;
                case ITEM_SIMPLE2: e.kind = EK_SIMPLE; e.speed = 3; e.chase = true; break;
                case ITEM_SIMPLE3: e.kind = EK_SIMPLE; e.speed = 1; break;
                case ITEM_SIMPLE4: e.kind = EK_SIMPLE; e.speed = 4; e.chase = true; break;
                case ITEM_BREAKER_BLUE: e.kind = EK_BREAKER; e.speed = 3; break;
                case ITEM_BREAKER_GREEN: e.kind = EK_BREAKER; e.speed = 3; break;
                case ITEM_BREAKER_YELLOW: e.kind = EK_BREAKER; e.speed = 2; break;
                case ITEM_FLYING: e.kind = EK_FLYING; break;
                case ITEM_LOG_ENEMY: e.kind = EK_LOG; break;
                case ITEM_TOWER: e.kind = EK_TOWER; break;
                case ITEM_CHASER: e.kind = EK_CHASER; break;
            }
            enemies.push_back(e);
        } else if (t >= ITEM_ARROW_LEFT && t <= ITEM_INVISIBLE_TILE) {
            Obj o; o.type = t; o.x = x; o.y = y; o.state = (t == ITEM_CAMPFIRE) ? CAMP_LIT : 0;
            objs.push_back(o);
        } else if (t == ITEM_ICE) {
            if (!wall[y * w + x] && iceIdx[y * w + x] < 0) addIce(x, y, ICE_STATIC);
        }
    }
    if (!players[0].present) return false;
    players[0].present = true;
    cameraX = std::max(0.f, std::min((float)(w * TILE_SIZE - SCREEN), players[0].x - SCREEN / 2.f));
    cameraY = std::max(0.f, std::min((float)(h * TILE_SIZE - SCREEN), players[0].y - SCREEN / 2.f));
    findPath();
    curWave = -1; startWave();
    return true;
}

// ---------------------------------------------------------------- utilidades

const Obj* World::objAt(int type, int x, int y) const {
    for (const Obj& o : objs) if (o.type == type && o.x == x && o.y == y) return &o;
    return nullptr;
}
bool World::playerAliveAt(int x, int y) const {
    for (const Player& p : players) if (p.present && !p.dead && p.tx == x && p.ty == y) return true;
    return false;
}
bool World::enemyAt(int x, int y, const Enemy* ignore) const {
    for (const Enemy& e : enemies) if (&e != ignore && e.tx == x && e.ty == y) return true;
    return false;
}
bool World::fruitHere(int x, int y) const {
    for (const Fruit& f : fruits) if (f.visible && !f.collected && f.tx == x && f.ty == y) return true;
    return false;
}
bool World::anyPlayerAlive() const {
    for (const Player& p : players) if (p.present && !p.dead) return true;
    return false;
}
bool World::freeCell(int x, int y) const {
    return !isWall(x, y) && iceAt(x, y) < 0 && !playerAliveAt(x, y) && !enemyAt(x, y, nullptr);
}
void World::placeAt(Walker& wk, int tx, int ty) { wk.tx = tx; wk.ty = ty; wk.x = tx * TILE_SIZE; wk.y = ty * TILE_SIZE; wk.moveDir = 0; }

void World::startWalk(Walker& wk, int dir) {
    wk.moveDir = dir; wk.lastDir = dir; wk.tx += DX[dir]; wk.ty += DY[dir];
}
// Desliza o corpo para o tile de destino; true ao chegar.
bool World::movement(Walker& wk) {
    float gx = wk.tx * TILE_SIZE, gy = wk.ty * TILE_SIZE;
    float dx = gx - wk.x, dy = gy - wk.y;
    float dist = std::fabs(dx) + std::fabs(dy);
    if (dist <= wk.speed) { wk.x = gx; wk.y = gy; wk.moveDir = 0; return true; }
    if (dx != 0) wk.x += sgn(dx) * std::min(wk.speed, std::fabs(dx));
    else wk.y += sgn(dy) * std::min(wk.speed, std::fabs(dy));
    return false;
}
bool World::canWalk(const Walker& wk, int dir, bool isPlayer, const Enemy* self) const {
    int nx = wk.tx + DX[dir], ny = wk.ty + DY[dir];
    if (isWall(nx, ny) || iceAt(nx, ny) >= 0) return false;
    if (isPlayer) {
        // Coop: os jogadores não saem da tela (a câmera segue a média dos vivos).
        if (coop && players[0].present && players[1].present && !players[0].dead && !players[1].dead) {
            float px = nx * TILE_SIZE, py = ny * TILE_SIZE;
            if (px < cameraX || px > cameraX + SCREEN - TILE_SIZE || py < cameraY || py > cameraY + SCREEN - TILE_SIZE) return false;
        }
    }
    (void)self;
    return true;
}

// ---------------------------------------------------------------- gelo e raio

void World::addIce(int x, int y, int state) {
    Ice ic; ic.x = x; ic.y = y; ic.state = state; ic.timer = 0;
    iceIdx[y * w + x] = (int)ices.size();
    ices.push_back(ic);
    pathDirty = true;
    // Gelo sobre fogueira acesa apaga a fogueira (NOT_FINISH_YET.md).
    for (Obj& o : objs)
        if (o.type == ITEM_CAMPFIRE && o.x == x && o.y == y && o.state != CAMP_UNLIT) { o.state = CAMP_UNLIT; o.timer = 0; snd("flametile"); }
}
void World::breakIce(int idx, bool quick) {
    Ice& ic = ices[idx];
    if (ic.state == ICE_BREAK || ic.state == ICE_QUICKBREAK || ic.state == ICE_MELT) return;
    ic.state = quick ? ICE_QUICKBREAK : ICE_BREAK; ic.timer = 0;
    snd("ice_wall_destroy");
}
void World::meltIce(int idx) {
    Ice& ic = ices[idx];
    if (ic.state == ICE_MELT) return;
    ic.state = ICE_MELT; ic.timer = 0;
}
void World::updateIce() {
    bool removed = false;
    for (Ice& ic : ices) {
        ic.timer++;
        if (ic.state == ICE_ADD && ic.timer >= ICE_ADD_FRAMES) { ic.state = ICE_STATIC; ic.timer = 0; }
        else if (ic.state == ICE_BREAK && ic.timer >= ICE_BREAK_FRAMES) ic.state = ICE_GONE;
        else if (ic.state == ICE_QUICKBREAK && ic.timer >= ICE_QUICK_FRAMES) ic.state = ICE_GONE;
        else if (ic.state == ICE_MELT && ic.timer >= ICE_MELT_FRAMES) ic.state = ICE_GONE;
        if (ic.state == ICE_GONE) removed = true;
    }
    if (removed) {
        ices.erase(std::remove_if(ices.begin(), ices.end(), [](const Ice& i) { return i.state == ICE_GONE; }), ices.end());
        std::fill(iceIdx.begin(), iceIdx.end(), -1);
        for (size_t i = 0; i < ices.size(); i++) iceIdx[ices[i].y * w + ices[i].x] = (int)i;
        pathDirty = true;
    }
}
void World::spawnRay(const Player& p, int dir) {
    Ray r; r.owner = p.num; r.dx = DX[dir]; r.dy = DY[dir]; r.dir = dir;
    r.cx = p.tx + r.dx; r.cy = p.ty + r.dy;
    r.adding = (iceAt(r.cx, r.cy) < 0); r.checkAdding = true; r.timer = 2;  // 1º passo no mesmo quadro
    rays.push_back(r);
    snd(r.adding ? "icecream_breath_out" : "icecream_breath_in");
}
void World::updateRays() {
    for (Ray& r : rays) {
        if (r.dead) continue;
        if (++r.timer < 2) continue;   // avança 1 tile a cada 2 quadros
        r.timer = 0;
        if (!inb(r.cx, r.cy) || isWall(r.cx, r.cy)) { r.dead = true; continue; }
        // Setas redirecionam o raio.
        for (const Obj& o : objs)
            if (o.x == r.cx && o.y == r.cy && o.type >= ITEM_ARROW_LEFT && o.type <= ITEM_ARROW_DOWN) {
                int d = o.type - ITEM_ARROW_LEFT + 1;  // 24 L,25 R,26 U,27 D -> 1..4
                r.dx = DX[d]; r.dy = DY[d]; r.dir = d; snd("directional_tile");
            }
        int ii = iceAt(r.cx, r.cy);
        if (r.adding) {
            if (ii >= 0 || enemyAt(r.cx, r.cy, nullptr)) { r.dead = true; continue; }
            bool playerThere = false;
            for (const Player& p : players) if (p.present && !p.dead && p.tx == r.cx && p.ty == r.cy) playerThere = true;
            if (playerThere) { r.dead = true; continue; }
            addIce(r.cx, r.cy, ICE_ADD); snd("ice_wall");
        } else {
            if (ii < 0) { r.dead = true; continue; }
            breakIce(ii, r.range > 0);
            r.range++;
        }
        r.cx += r.dx; r.cy += r.dy;
    }
    rays.erase(std::remove_if(rays.begin(), rays.end(), [](const Ray& r) { return r.dead; }), rays.end());
}

// ---------------------------------------------------------------- caminhos (BFS/SPFA multi-fonte)

// mode 0: gelo bloqueia; 1: gelo custa 2 (breakers); 2: gelo custa 10 (pato).
int World::cellCost(int x, int y, int mode) const {
    if (isWall(x, y)) return INF;
    if (iceAt(x, y) >= 0) return mode == 0 ? INF : (mode == 1 ? 2 : 10);
    return 1;
}
void World::spfa(std::vector<int>& d, int mode, int seedMask) {
    std::fill(d.begin(), d.end(), INF);
    std::deque<int> q;
    for (int i = 0; i < 2; i++)
        if ((seedMask >> i & 1) && players[i].present && !players[i].dead && inb(players[i].tx, players[i].ty)) {
            d[players[i].ty * w + players[i].tx] = 1; q.push_back(players[i].ty * w + players[i].tx);
        }
    while (!q.empty()) {
        int c = q.front(); q.pop_front();
        int cx = c % w, cy = c / w;
        for (int k = 1; k <= 4; k++) {
            int nx = cx + DX[k], ny = cy + DY[k];
            if (!inb(nx, ny)) continue;
            int cost = cellCost(nx, ny, mode);
            if (cost >= INF) continue;
            int nd = d[c] + cost;
            if (nd < d[ny * w + nx]) { d[ny * w + nx] = nd; q.push_back(ny * w + nx); }
        }
    }
}
void World::findPath() {
    spfa(pathNum, 0, 3); spfa(seeNum, 1, 3); spfa(jumpNum, 2, 3);
    spfa(p1Num, 0, 1);   spfa(p2Num, 0, 2);
    pathDirty = false;
}
// Direção do vizinho de menor valor no campo (0 = nenhuma). jump: pato pode pular 1 gelo (2 tiles).
int World::fieldDir(const Walker& wk, const std::vector<int>& f, int mode, bool jump) const {
    int here = f[wk.ty * w + wk.tx];
    if (here >= INF) return 0;
    int best = 0, bestV = here;
    for (int k = 1; k <= 4; k++) {
        int nx = wk.tx + DX[k], ny = wk.ty + DY[k];
        if (!inb(nx, ny) || isWall(nx, ny)) continue;
        bool ice = iceAt(nx, ny) >= 0;
        if (ice && mode == 0) continue;
        if (ice && jump) {
            int jx = nx + DX[k], jy = ny + DY[k];
            if (!inb(jx, jy) || isWall(jx, jy) || iceAt(jx, jy) >= 0) continue;
        }
        int v = f[ny * w + nx];
        if (v < bestV) { bestV = v; best = k; }
    }
    return best;
}
int World::randomDir(const Walker& wk, bool isEnemy, bool allowBack) {
    int opts[4], n = 0;
    for (int k = 1; k <= 4; k++) {
        if (!allowBack && k == OPP[wk.lastDir]) continue;
        if (canWalk(wk, k, !isEnemy, nullptr)) opts[n++] = k;
    }
    if (n == 0 && !allowBack) return randomDir(wk, isEnemy, true);
    return n ? opts[rng.range(n)] : 0;
}

// ---------------------------------------------------------------- jogadores

void World::killPlayer(Player& p) {
    if (p.dead) return;
    p.dead = true; p.deadFrames = 0; p.moveDir = 0; p.shootTimer = 0;
    p.x = p.tx * TILE_SIZE; p.y = p.ty * TILE_SIZE;
    snd("ice_cream_hurt");
    pathDirty = true;
}
void World::onPlayerStepped(Player& p) {
    pathDirty = true;
    for (const Obj& o : objs)
        if (o.type == ITEM_CAMPFIRE && o.x == p.tx && o.y == p.ty && o.state == CAMP_LIT) { killPlayer(p); return; }
}
int World::nearestFrontIce(const Player& p) const {
    int d = p.lastDir;
    return iceAt(p.tx + DX[d], p.ty + DY[d]);
}
void World::updatePlayer(Player& p, const PadState& pad, int idx) {
    (void)idx;
    if (!p.present) return;
    if (p.dead) { p.deadFrames++; return; }
    p.animFrame++;
    if (p.moveDir && movement(p)) onPlayerStepped(p);
    if (p.dead || p.moveDir) return;

    // Tiro / quebra em andamento: animação 12 (Shoot) ou 15 (Break) quadros; o raio nasce no quadro 7.
    if (p.shootTimer > 0) {
        p.shootTimer++;
        if (p.shootTimer == 7) spawnRay(p, p.lastDir);
        if (p.shootTimer > (p.shootBreak ? 15 : 12)) {
            p.shootTimer = 0;
            if (p.shootBreak) p.lastDir = DIR_DOWN;   // depois do Break olha para baixo
        }
        p.spaceKey = pad.shoot;
        return;
    }
    if (pad.shoot && !p.spaceKey) {
        int d = p.lastDir;
        int nx = p.tx + DX[d], ny = p.ty + DY[d];
        p.spaceKey = true;
        if (iceAt(nx, ny) >= 0) { p.shootBreak = true; p.shootTimer = 1; return; }
        if (!isWall(nx, ny)) { p.shootBreak = false; p.shootTimer = 1; return; }
        // parede à frente: não faz nada
    }
    p.spaceKey = pad.shoot;

    int want = pad.left ? DIR_LEFT : pad.right ? DIR_RIGHT : pad.up ? DIR_UP : pad.down ? DIR_DOWN : 0;
    if (!want) { p.turnTimer = 0; return; }
    if (want != p.lastDir) { p.lastDir = want; p.turnTimer = 2; return; }   // virar primeiro...
    if (p.turnTimer > 0) { p.turnTimer--; return; }                          // ...andar depois
    if (canWalk(p, want, true, nullptr)) startWalk(p, want);
}

// ---------------------------------------------------------------- objetos (fogueiras)

void World::updateObjs() {
    for (Obj& o : objs) {
        if (o.type != ITEM_CAMPFIRE) continue;
        o.timer++;
        if (o.state == CAMP_UNLIT && o.timer >= CAMP_RELIGHT_WAIT) { o.state = CAMP_LIGHTING; o.timer = 0; }
        else if (o.state == CAMP_LIGHTING && o.timer >= CAMP_LIGHTING_FRAMES) {
            o.state = CAMP_LIT; o.timer = 0;
            int ii = iceAt(o.x, o.y);          // [SUPOSIÇÃO] gelo em cima de uma fogueira que reacende derrete
            if (ii >= 0) meltIce(ii);
        }
    }
}

// ---------------------------------------------------------------- inimigos

void World::breakerBreak(Enemy& e) {
    int d = e.breakDir;
    auto br = [&](int x, int y) { int i = iceAt(x, y); if (i >= 0 && (ices[i].state == ICE_STATIC || ices[i].state == ICE_ADD)) breakIce(i, false); };
    if (e.itemType == ITEM_BREAKER_BLUE) {           // fileira inteira à frente
        int x = e.tx + DX[d], y = e.ty + DY[d];
        while (inb(x, y) && iceAt(x, y) >= 0) { br(x, y); x += DX[d]; y += DY[d]; }
    } else if (e.itemType == ITEM_BREAKER_GREEN) {   // 8 vizinhos
        for (int yy = -1; yy <= 1; yy++) for (int xx = -1; xx <= 1; xx++) if (xx || yy) br(e.tx + xx, e.ty + yy);
    } else {                                         // amarelo: 1 tile
        br(e.tx + DX[d], e.ty + DY[d]);
    }
}
void World::enemyWalk(Enemy& e, int dir) { startWalk(e, dir); }

void World::randomWalkStep(Enemy& e) {
    int d = randomDir(e, true, false);
    if (d) enemyWalk(e, d);
}

bool World::tpTarget(int& ox, int& oy) {
    for (int tries = 0; tries < 200; tries++) {
        int x = rng.range(w), y = rng.range(h);
        if (!freeCell(x, y)) continue;
        bool near = false;
        for (const Player& p : players) if (p.present && !p.dead && std::abs(p.tx - x) + std::abs(p.ty - y) < 4) near = true;
        if (near) continue;
        ox = x; oy = y; return true;
    }
    return false;
}

void World::enemyStepped(Enemy& e) { e.moves++; }

void World::updateEnemy(Enemy& e) {
    e.animFrame++;
    // ---- estados que impedem andar
    if (e.kind == EK_BREAKER && e.breaking) {
        e.breakFrame++;
        if (e.breakFrame == 24) { breakerBreak(e); pathDirty = true; }
        if (e.breakFrame >= 48) { e.breaking = false; e.breakFrame = 0; }
        return;
    }
    if (e.kind == EK_TOWER && e.tpState) {
        e.tpTimer++;
        if (e.tpState == 1 && e.tpTimer >= 48) {
            int nx, ny;
            if (tpTarget(nx, ny)) placeAt(e, nx, ny);
            e.tpState = 2; e.tpTimer = 0;
        } else if (e.tpState == 2 && e.tpTimer >= 48) { e.tpState = 0; e.moves = 0; }
        return;
    }
    if (e.kind == EK_FLYING && e.flying) {
        e.jumpFrame++;
        float t = std::min(1.f, e.jumpFrame / 24.f);
        e.x = e.fx0 + (e.fx1 - e.fx0) * t; e.y = e.fy0 + (e.fy1 - e.fy0) * t;
        if (e.jumpFrame >= 24) { e.flying = false; e.moveDir = 0; e.x = e.tx * TILE_SIZE; e.y = e.ty * TILE_SIZE; pathDirty = true; }
        return;
    }
    if (e.kind == EK_LOG && e.trans > 0) { if (--e.trans == 0 && e.transStart) { e.rolling = true; e.transStart = false; } return; }

    if (e.moveDir) {
        if (movement(e)) {
            enemyStepped(e);
            if (e.kind == EK_LOG && e.rolling) {
                int nx = e.tx + DX[e.lastDir], ny = e.ty + DY[e.lastDir];
                if (isWall(nx, ny) || iceAt(nx, ny) >= 0) { snd("log_roll_hit"); e.rolling = false; e.speed = 3; e.trans = 18; e.transStart = false; return; }   // EndRoll
                startWalk(e, e.lastDir); return;
            }
        } else return;
    }

    // ---- decisão num tile (parado)
    const int* f = nullptr;
    switch (e.kind) {
        case EK_SIMPLE: {
            if (e.rightTurn) {
                int d = e.lastDir ? e.lastDir : DIR_DOWN;
                int order[4] = {RIGHT_OF[d], d, LEFT_OF[d], OPP[d]};
                for (int k = 0; k < 4; k++) if (canWalk(e, order[k], false, &e)) { enemyWalk(e, order[k]); return; }
                return;
            }
            if (e.chase) {
                int d = fieldDir(e, pathNum, 0, false);
                if (d && canWalk(e, d, false, &e)) { enemyWalk(e, d); return; }
            }
            randomWalkStep(e); return;
        }
        case EK_BREAKER: {
            int d = fieldDir(e, seeNum, 1, false);
            if (d) {
                if (iceAt(e.tx + DX[d], e.ty + DY[d]) >= 0) { e.lastDir = d; e.breakDir = d; e.breaking = true; e.breakFrame = 0; snd(e.itemType == ITEM_BREAKER_BLUE ? "squid_electric" : e.itemType == ITEM_BREAKER_GREEN ? "squid_ground_pound" : "squid_slap"); return; }
                if (canWalk(e, d, false, &e)) { enemyWalk(e, d); return; }
            }
            randomWalkStep(e); return;
        }
        case EK_FLYING: {
            int d = fieldDir(e, jumpNum, 2, true);
            if (d) {
                int nx = e.tx + DX[d], ny = e.ty + DY[d];
                if (iceAt(nx, ny) >= 0) {   // pula 2 tiles sobre 1 gelo
                    e.lastDir = d; e.fx0 = e.x; e.fy0 = e.y;
                    e.tx = nx + DX[d]; e.ty = ny + DY[d];
                    e.fx1 = e.tx * TILE_SIZE; e.fy1 = e.ty * TILE_SIZE;
                    e.flying = true; e.jumpFrame = 0; e.moveDir = d; snd("duck"); return;
                }
                if (canWalk(e, d, false, &e)) { enemyWalk(e, d); return; }
            }
            randomWalkStep(e); return;
        }
        case EK_LOG: {
            // Se vê um jogador em linha reta (sem parede/gelo no meio), rola a 10 px/quadro até bater.
            for (int k = 1; k <= 4 && !e.rolling; k++) {
                int x = e.tx + DX[k], y = e.ty + DY[k];
                while (inb(x, y) && !isWall(x, y) && iceAt(x, y) < 0) {
                    if (playerAliveAt(x, y)) {
                        e.lastDir = k; e.trans = 18; e.transStart = true; e.speed = 10;   // StartRoll
                        return;
                    }
                    x += DX[k]; y += DY[k];
                }
            }
            if (e.rolling) { if (canWalk(e, e.lastDir, false, &e)) startWalk(e, e.lastDir); else { e.rolling = false; e.speed = 3; e.trans = 18; } return; }
            randomWalkStep(e); return;
        }
        case EK_TOWER: {
            if (e.moves >= 8 && rng.range(4) == 0) { e.tpState = 1; e.tpTimer = 0; return; }   // [SUPOSIÇÃO] chance 1/4 a partir de 8 passos
            int d = fieldDir(e, pathNum, 0, false);
            if (d && canWalk(e, d, false, &e)) { enemyWalk(e, d); return; }
            randomWalkStep(e); return;
        }
        case EK_CHASER: {
            // [SUPOSIÇÃO] fases: 0 aleatório 180q; 1 retract 20q; 2 persegue 120q; 3 popup 36q.
            e.chTimer++;
            if (e.chState == 0) { if (e.chTimer >= 180) { e.chState = 1; e.chTimer = 0; snd("change_flower"); e.chasing = (coop && e.followP2Next && players[1].present && !players[1].dead) ? 1 : 0; e.followP2Next = !e.followP2Next; } randomWalkStep(e); return; }
            if (e.chState == 1) { if (e.chTimer >= 20) { e.chState = 2; e.chTimer = 0; } return; }
            if (e.chState == 2) {
                if (e.chTimer >= 120) { e.chState = 3; e.chTimer = 0; return; }
                const std::vector<int>& fl = (e.chasing == 1) ? p2Num : p1Num;
                int d = fieldDir(e, fl, 0, false);
                if (d == 0) d = fieldDir(e, pathNum, 0, false);
                if (d && canWalk(e, d, false, &e)) { enemyWalk(e, d); return; }
                randomWalkStep(e); return;
            }
            if (e.chTimer >= 36) { e.chState = 0; e.chTimer = 0; }
            return;
        }
    }
    (void)f;
}

// ---------------------------------------------------------------- frutas e ondas

void World::startWave() {
    for (int i = curWave + 1; i < 10; i++) {
        bool any = false;
        for (Fruit& f : fruits) if (f.itemType == kWaveOrder[i]) any = true;
        if (!any) continue;
        curWave = i;
        for (Fruit& f : fruits) if (f.itemType == kWaveOrder[i]) { f.appearing = true; f.appearTimer = 0; f.visible = true; }
        return;
    }
    curWave = 10;   // acabaram as ondas
    if (!finishTimer) finishTimer = WIN_DELAY;
}
bool World::fruitCanWalk(const Fruit& f, int dir) const {
    int nx = f.tx + DX[dir], ny = f.ty + DY[dir];
    if (isWall(nx, ny)) return false;
    if (iceAt(nx, ny) >= 0 && f.itemType != ITEM_PINEAPPLE) return false;
    return true;
}
void World::collect(Fruit& f, Player& p) {
    f.collected = true; f.collectTimer = 0; f.moveDir = 0; p.score += FRUIT_SCORE; levelScore += FRUIT_SCORE; snd("pick_up_fruit");
}
void World::fruitRandomWalk(Fruit& f) {
    int opts[4], n = 0;
    for (int k = 1; k <= 4; k++) if (k != OPP[f.lastDir] && fruitCanWalk(f, k)) opts[n++] = k;
    if (!n) for (int k = 1; k <= 4; k++) if (fruitCanWalk(f, k)) opts[n++] = k;
    if (n) startWalk(f, opts[rng.range(n)]);
}
void World::fruitStepped(Fruit&) {}
void World::updateFruits() {
    for (Fruit& f : fruits) {
        f.animFrame++;
        if (!f.visible) continue;
        if (f.collected) { if (++f.collectTimer >= COLLECT_FRAMES) f.visible = false; continue; }
        if (f.appearing) { if (++f.appearTimer >= APPEAR_FRAMES) f.appearing = false; continue; }
        switch (f.itemType) {
            case ITEM_CHERRIES: {   // teleporta a cada ~200 quadros (TeleportOut 92 + TeleportIn 83)
                f.tpTimer++;
                if (f.tpState == 0 && f.tpTimer >= 200) { f.tpState = 1; f.tpTimer = 0; snd("cherry_transport"); }
                else if (f.tpState == 1 && f.tpTimer >= 92) {
                    for (int tries = 0; tries < 200; tries++) {
                        int x = rng.range(w), y = rng.range(h);
                        if (!isWall(x, y) && iceAt(x, y) < 0 && !playerAliveAt(x, y) && !fruitHere(x, y)) { placeAt(f, x, y); break; }
                    }
                    f.tpState = 2; f.tpTimer = 0;
                } else if (f.tpState == 2 && f.tpTimer >= 83) { f.tpState = 0; f.tpTimer = 0; }
                break;
            }
            case ITEM_KIWI: case ITEM_PEAR: case ITEM_STRAWBERRY: case ITEM_PINEAPPLE: {
                if (f.moveDir) { if (movement(f)) fruitStepped(f); else break; }
                if (f.itemType == ITEM_PINEAPPLE && f.jumping) break;
                if (f.itemType == ITEM_STRAWBERRY) {   // mão direita, 1.5 px/quadro
                    int d = f.lastDir ? f.lastDir : DIR_DOWN;
                    int order[4] = {RIGHT_OF[d], d, LEFT_OF[d], OPP[d]};
                    for (int k = 0; k < 4; k++) if (fruitCanWalk(f, order[k])) { startWalk(f, order[k]); break; }
                } else if (f.itemType == ITEM_PINEAPPLE) {
                    fruitRandomWalk(f);
                } else {   // Kiwi/Pera: fogem. [SUPOSIÇÃO] 2 px/quadro; 6 quando um jogador está a menos de 5 tiles
                    int near = 99;
                    for (const Player& p : players) if (p.present && !p.dead) near = std::min(near, std::abs(p.tx - f.tx) + std::abs(p.ty - f.ty));
                    f.speed = near < 5 ? 6 : 2;
                    int best = 0, bestV = pathNum[f.ty * w + f.tx];
                    for (int k = 1; k <= 4; k++) {
                        if (!fruitCanWalk(f, k)) continue;
                        int v = pathNum[(f.ty + DY[k]) * w + f.tx + DX[k]];
                        if (v != INF && v > bestV) { bestV = v; best = k; }
                    }
                    if (best) startWalk(f, best);
                }
                break;
            }
            default: break;   // Bananas, Lemon, Orange, Grapes, Watermelon: paradas
        }
    }
}

// ---------------------------------------------------------------- colisões

void World::collide() {
    for (Player& p : players) {
        if (!p.present || p.dead) continue;
        for (Enemy& e : enemies) {
            if ((e.kind == EK_TOWER && e.tpState) || (e.kind == EK_CHASER && (e.chState == 1))) continue;
            if (e.flying) { if (std::abs(e.tx * TILE_SIZE - p.x) < 24 && std::abs(e.ty * TILE_SIZE - p.y) < 24 && e.jumpFrame > 16) { killPlayer(p); break; } continue; }
            if ((p.tx == e.tx && p.ty == e.ty) || (std::fabs(p.x - e.x) < 26 && std::fabs(p.y - e.y) < 26)) { killPlayer(p); break; }
        }
        if (p.dead) continue;
        for (Fruit& f : fruits) {
            if (!f.visible || f.collected || f.appearing || f.tpState != 0) continue;
            if (iceAt(f.tx, f.ty) >= 0) continue;   // fruta dentro do gelo
            if (std::fabs(p.x - f.x) < 24 && std::fabs(p.y - f.y) < 24) collect(f, p);
        }
    }
}

// ---------------------------------------------------------------- câmera e laço principal

void World::updateCamera() {
    float sx = 0, sy = 0; int n = 0;
    for (const Player& p : players) if (p.present && !p.dead) { sx += p.x; sy += p.y; n++; }
    if (!n) return;
    float tx = sx / n + TILE_SIZE / 2.f - SCREEN / 2.f, ty = sy / n + TILE_SIZE / 2.f - SCREEN / 2.f;
    float maxX = (float)(w * TILE_SIZE - SCREEN), maxY = (float)(h * TILE_SIZE - SCREEN);
    tx = maxX <= 0 ? maxX / 2 : std::max(0.f, std::min(maxX, tx));
    ty = maxY <= 0 ? maxY / 2 : std::max(0.f, std::min(maxY, ty));
    // Suavização mais gradual: evita a câmera "grudar" no jogador e saltar
    // quando o próximo trecho do cenário entra no enquadramento.
    cameraX += (tx - cameraX) * 0.18f; cameraY += (ty - cameraY) * 0.18f;
}

void World::update(const PadState pads[2]) {
    frameNumber++;
    if (phase != PHASE_PLAYING) return;
    if (pathDirty || (frameNumber & 3) == 0) findPath();
    for (int i = 0; i < 2; i++) {
        PadState pd = pads[i];
        updatePlayer(players[i], pd, i);
    }
    updateRays();
    updateIce();
    updateObjs();
    for (Enemy& e : enemies) updateEnemy(e);
    updateFruits();
    collide();
    updateCamera();

    // onda terminou? (todas as frutas da onda coletadas)
    if (curWave >= 0 && curWave < 10) {
        bool left = false;
        for (const Fruit& f : fruits) if (f.itemType == kWaveOrder[curWave] && !f.collected) left = true;
        if (!left) startWave();
    }
    if (finishTimer > 0 && --finishTimer == 0) {
        winTime = frameNumber; levelScore += timeBonus();
        for (Player& p : players) if (p.present && !p.dead) p.score += 0;
        phase = PHASE_WON; snd("endlevel");
        return;
    }
    // Derrota: coop só falha quando os dois morrem; a animação Die tem 48 quadros.
    bool allDead = true, animDone = true;
    for (const Player& p : players) if (p.present) { if (!p.dead) allDead = false; else if (p.deadFrames < 48) animDone = false; }
    if (allDead && animDone) { phase = PHASE_LOST; }
}

void World::advanceStage() {}

}  // namespace bic
