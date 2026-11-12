#include "render.hpp"

#include <algorithm>
#include <cmath>

namespace bic {

namespace {
const char* const kDir[5] = {"Down", "Left", "Right", "Up", "Down"};
const char* const kFruit[13] = {"", "", "", "Bananas", "Lemon", "Orange", "Grapes", "Watermelon", "Kiwi", "Strawberry", "Pear", "Pineapple", "Cherries"};

struct Item { int key, ord; Quad q; };

struct Ctx {
    const Atlas& atlas; const World& w; std::vector<Item>& items; std::vector<Quad>& floor;
    float camX, camY;
};

const Frame* pick(const Anim* a, int idx, bool loop) {
    if (!a || a->f.empty()) return nullptr;
    int n = (int)a->f.size();
    if (idx < 0) idx = 0;
    return &a->f[loop ? idx % n : std::min(idx, n - 1)];
}

// Desenha o quadro com (px,py) = canto superior esquerdo da célula, em coordenadas do mundo.
bool makeQuad(const Ctx& c, const Frame* f, float px, float py, float alpha, Quad& q) {
    if (!f) return false;
    float x0 = std::floor(px - f->ox - c.camX + 0.5f), y0 = std::floor(py - f->oy - c.camY + 0.5f);
    if (x0 > SCREEN || y0 > SCREEN || x0 + f->w < 0 || y0 + f->h < 0) return false;
    const Atlas::Page& pg = c.atlas.pages[f->page];
    q.x0 = x0; q.y0 = y0; q.x1 = x0 + f->w; q.y1 = y0 + f->h;
    q.u0 = (float)f->x / pg.w; q.v0 = (float)f->y / pg.h; q.u1 = (float)(f->x + f->w) / pg.w; q.v1 = (float)(f->y + f->h) / pg.h;
    q.r = q.g = q.b = 1; q.a = alpha; q.page = f->page;
    return true;
}
void addItem(Ctx& c, const std::string& cls, const std::string& anim, int idx, bool loop, float px, float py, int key, int ord, float alpha = 1.f) {
    Quad q;
    if (makeQuad(c, pick(c.atlas.find(cls, anim), idx, loop), px, py, alpha, q)) c.items.push_back({key, ord, q});
}
void addFloor(Ctx& c, const std::string& cls, const std::string& anim, int idx, bool loop, float px, float py) {
    Quad q;
    if (makeQuad(c, pick(c.atlas.find(cls, anim), idx, loop), px, py, 1.f, q)) c.floor.push_back(q);
}
}  // namespace

void buildScene(const World& w, const Atlas& atlas, DrawList& out) {
    out.clear();
    std::vector<Item> items; std::vector<Quad> floor;
    items.reserve(1024); floor.reserve(1024);
    Ctx c{atlas, w, items, floor, std::floor(w.cameraX + 0.5f), std::floor(w.cameraY + 0.5f)};
    const float T = TILE_SIZE;

    // ---- tiles
    int x0 = std::max(0, (int)(c.camX / T) - 1), x1 = std::min(w.w, (int)((c.camX + SCREEN) / T) + 2);
    int y0 = std::max(0, (int)(c.camY / T) - 1), y1 = std::min(w.h, (int)((c.camY + SCREEN) / T) + 4);
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++) {
            int id = w.tileId[y * w.w + x];
            if (id < FIRST_TILE_TYPE) continue;
            int k = id - FIRST_TILE_TYPE;
            if (k >= kTileNameCount) continue;
            const TileInfo& ti = kTileInfo[k];
            if (ti.free) addFloor(c, kTileNames[k], "_", 0, false, x * T, y * T);
            else addItem(c, kTileNames[k], "_", 0, false, x * T, y * T, (y + ti.fh - 1) * TILE_SIZE, 0);
        }
    // ---- objetos de chão
    for (const Obj& o : w.objs) {
        float px = o.x * T, py = o.y * T;
        if (o.type >= ITEM_ARROW_LEFT && o.type <= ITEM_ARROW_DOWN) {
            static const char* const nm[4] = {"ArrowTileLeft", "ArrowTileRight", "ArrowTileUp", "ArrowTileDown"};
            addFloor(c, nm[o.type - ITEM_ARROW_LEFT], "_", w.frameNumber, true, px, py);
        } else if (o.type == ITEM_FLAMEPAD) addFloor(c, "FlamePad", "_", w.frameNumber, true, px, py);
        else if (o.type == ITEM_CAMPFIRE) {
            addFloor(c, "CampfireBack", "_", 0, false, px, py);
            const char* an = o.state == CAMP_LIT ? "Lit" : o.state == CAMP_UNLIT ? "Unlit" : "Lighting";
            addItem(c, "Campfire", an, o.state == CAMP_LIT ? w.frameNumber : o.timer, o.state == CAMP_LIT, px, py, o.y * TILE_SIZE, 1);
        }
    }
    // ---- gelo
    for (const Ice& ic : w.ices) {
        const char* an = "Static"; int idx = ic.timer; bool loop = false;
        switch (ic.state) {
            case ICE_ADD: an = "Add"; break;
            case ICE_BREAK: an = "Break"; break;
            case ICE_QUICKBREAK: an = "QuickBreak"; break;
            case ICE_MELT: an = "Melt"; break;
            default: an = "Static"; idx = 0; break;
        }
        bool fruitInside = false;
        for (const Fruit& f : w.fruits) if (f.visible && !f.collected && f.tx == ic.x && f.ty == ic.y) fruitInside = true;
        if (fruitInside && ic.state == ICE_STATIC) an = "ItemInside";
        addItem(c, "IceTile", an, idx, loop, ic.x * T, ic.y * T, ic.y * TILE_SIZE, 2);
    }
    // ---- frutas
    for (const Fruit& f : w.fruits) {
        if (!f.visible || w.iceAt(f.tx, f.ty) >= 0) continue;
        std::string cls = std::string("Collectible") + kFruit[f.itemType];
        const char* an = "Normal"; int idx = f.animFrame;
        if (f.collected) { an = "Collect"; idx = f.collectTimer; }
        else if (f.appearing) { an = "Appear"; idx = f.appearTimer; }
        else if (f.itemType == ITEM_CHERRIES && f.tpState == 1) { an = "TeleportOut"; idx = f.tpTimer; }
        else if (f.itemType == ITEM_CHERRIES && f.tpState == 2) { an = "TeleportIn"; idx = f.tpTimer; }
        if (!f.collected && !f.appearing && f.tpState == 0) addItem(c, cls, "Shadow", 0, false, f.x, f.y, (int)f.y, 3);
        addItem(c, cls, an, idx, !f.collected && !f.appearing && an[0] == 'N', f.x, f.y, (int)f.y + 1, 3);
    }
    // ---- inimigos
    for (const Enemy& e : w.enemies) {
        const char* d = kDir[e.lastDir ? e.lastDir : DIR_DOWN];
        std::string cls, an; int idx = e.animFrame;
        switch (e.itemType) {
            case ITEM_SIMPLE1: case ITEM_SIMPLE2: case ITEM_SIMPLE3: case ITEM_SIMPLE4:
                cls = "SimpleEnemy" + std::to_string(e.itemType - ITEM_SIMPLE1 + 1); an = std::string(d) + "Walk"; break;
            case ITEM_BREAKER_BLUE: case ITEM_BREAKER_GREEN: case ITEM_BREAKER_YELLOW: {
                static const char* const nm[3] = {"BlueBreakerEnemy", "GreenBreakerEnemy", "YellowBreakerEnemy"};
                cls = nm[e.itemType - ITEM_BREAKER_BLUE];
                if (e.breaking) { an = std::string(d) + "Break"; idx = e.breakFrame; } else an = std::string(d) + "Walk";
                break;
            }
            case ITEM_FLYING: cls = "FlyingEnemy"; if (e.flying) { an = std::string(d) + "Fly"; idx = e.jumpFrame; } else an = std::string(d) + "Walk"; break;
            case ITEM_LOG_ENEMY:
                cls = "LogEnemy";
                if (e.rolling) an = std::string(d) + "Roll";
                else if (e.trans > 0) { an = std::string(d) + (e.transStart ? "StartRoll" : "EndRoll"); idx = 18 - e.trans; }
                else an = std::string(d) + "Walk";
                break;
            case ITEM_TOWER:
                cls = "TowerEnemy";
                if (e.tpState == 1) { an = "TeleportOut"; idx = e.tpTimer; } else if (e.tpState == 2) { an = "TeleportIn"; idx = e.tpTimer; } else an = std::string(d) + "Walk";
                break;
            default: {   // Chaser
                cls = "ChaserEnemy";
                if (e.chState == 1) { an = std::string("Retract1") + d; idx = e.chTimer; }
                else if (e.chState == 3) { an = std::string("Popup1") + d; idx = e.chTimer; }
                else an = std::string(e.chState == 2 ? "Walk1" : "Walk0") + d;
                break;
            }
        }
        addItem(c, cls, an, idx, true, e.x, e.y, (int)e.y + 1, 4);
    }
    // ---- jogadores
    for (int i = 0; i < 2; i++) {
        const Player& p = w.players[i];
        if (!p.present) continue;
        const char* cls = p.num == 1 ? "PlayerVanilla" : "PlayerStrawberry";
        const char* d = kDir[p.lastDir ? p.lastDir : DIR_DOWN];
        std::string an; int idx = p.animFrame; bool loop = true;
        if (p.dead) { an = "Die"; idx = p.deadFrames; loop = false; }
        else if (w.phase == PHASE_WON || w.finishTimer > 0) { an = "Win"; idx = w.frameNumber; loop = true; }
        else if (p.shootTimer > 0) { an = std::string(d) + (p.shootBreak ? "Break" : "Shoot"); idx = p.shootTimer - 1; loop = false; }
        else if (p.moveDir) an = std::string(d) + "Walk";
        else an = std::string(d) + "Stand";
        addItem(c, cls, an, idx, loop, p.x, p.y, (int)p.y + 2, 5);
    }

    std::stable_sort(items.begin(), items.end(), [](const Item& a, const Item& b) { return a.key != b.key ? a.key < b.key : a.ord < b.ord; });
    out.quads = floor;
    for (const Item& it : items) out.quads.push_back(it.q);
}

}  // namespace bic
