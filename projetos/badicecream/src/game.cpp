// Fluxo do jogo: título, fases, vitória/derrota, HUD, som e música. Portátil: só fala com Platform.
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>

#include "atlas.hpp"
#include "engine.hpp"
#include "platform.hpp"
#include "render.hpp"

namespace bic {

namespace {

bool readFile(const std::string& path, std::vector<uint8_t>& out) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    out.resize(n > 0 ? (size_t)n : 0);
    size_t got = out.empty() ? 0 : fread(out.data(), 1, out.size(), f);
    fclose(f);
    return got == out.size();
}

const int kLevelCount = 40;
enum State { ST_TITLE, ST_PLAYING, ST_WON, ST_LOST, ST_END };

struct Game {
    Platform& pf; Options opt;
    Atlas atlas; World world; World titleWorld; DrawList list;
    bool titleDemoReady = false;
    State state = ST_TITLE;
    int level = 0, stateTimer = 0, totalScore = 0;
    bool coop = false;
    bool prevStart[2] = {false, false};
    std::string music;

    Game(Platform& p, const Options& o) : pf(p), opt(o) {}

    bool loadAssets() {
        const std::string dir = pf.dataDir();
        std::vector<uint8_t> buf;
        if (!readFile(dir + "atlas.txt", buf)) { printf("falta %satlas.txt\n", dir.c_str()); return false; }
        if (!atlas.parse(std::string(buf.begin(), buf.end()))) { printf("atlas.txt inválido\n"); return false; }
        for (size_t i = 0; i < atlas.pages.size(); i++) {
            const Atlas::Page& pg = atlas.pages[i];
            if (!readFile(dir + pg.file, buf) || buf.size() != (size_t)pg.w * pg.h * 4) { printf("página %s inválida\n", pg.file.c_str()); return false; }
            // Os bytes estão em ordem A,R,G,B: monta uint32 0xAARRGGBB independente da endianness do host.
            std::vector<uint32_t> px((size_t)pg.w * pg.h);
            for (size_t k = 0; k < px.size(); k++) px[k] = (uint32_t)buf[k * 4] << 24 | (uint32_t)buf[k * 4 + 1] << 16 | (uint32_t)buf[k * 4 + 2] << 8 | buf[k * 4 + 3];
            pf.uploadPage((int)i, pg.w, pg.h, px.data());
        }
        if (readFile(dir + "snd.txt", buf)) {
            std::string txt(buf.begin(), buf.end()); size_t pos = 0;
            while (pos < txt.size()) {
                size_t e = txt.find('\n', pos); if (e == std::string::npos) e = txt.size();
                char name[64], file[128]; int frames, loop;
                if (sscanf(txt.substr(pos, e - pos).c_str(), "%63s %127s %d %d", name, file, &frames, &loop) == 4) {
                    std::vector<uint8_t> raw;
                    if (readFile(dir + file, raw)) {
                        std::vector<int16_t> pcm(raw.size() / 2);
                        for (size_t k = 0; k < pcm.size(); k++) pcm[k] = (int16_t)((raw[k * 2] << 8) | raw[k * 2 + 1]);   // s16 big-endian
                        pf.loadSound(name, pcm.data(), pcm.size(), loop != 0);
                    }
                }
                pos = e + 1;
            }
        }
        titleDemoReady = resetTitleDemo();
        return true;
    }

    // Usa a própria fase inicial como demonstração animada no menu.
    bool resetTitleDemo() {
        std::vector<uint8_t> raw; LevelData lv;
        if (!readFile(pf.dataDir() + "levels/level00.xml", raw) ||
            !parseLevel(std::string(raw.begin(), raw.end()), lv)) return false;
        if (!titleWorld.load(lv, false, 0xB1C0FFEEu)) return false;
        titleWorld.stage = 0;
        return true;
    }

    void updateTitleDemo() {
        if (!titleDemoReady) return;
        PadState demo[2];
        demo[0].connected = true;
        const int f = titleWorld.frameNumber;
        switch ((f / 72) % 4) {
            case 0: demo[0].right = true; break;
            case 1: demo[0].down = true; break;
            case 2: demo[0].left = true; break;
            default: demo[0].up = true; break;
        }
        demo[0].shoot = (f % 84) == 8;
        titleWorld.update(demo);
        titleWorld.clearSounds();
        if (titleWorld.phase != PHASE_PLAYING) titleDemoReady = resetTitleDemo();
    }

    void addSnow() {
        const int f = titleDemoReady ? titleWorld.frameNumber : stateTimer;
        for (int i = 0; i < 34; ++i) {
            const int x = (i * 137 + f * (1 + i % 3)) % SCREEN;
            const int y = (i * 71 + f * (2 + i % 3)) % SCREEN;
            const char* flake = (i % 5 == 0) ? "*" : ".";
            const uint32_t color = (i % 3 == 0) ? 0xFFE8F7FF : 0xFFB9DFFF;
            text(x, y, (i % 7 == 0) ? 2 : 1, color, flake);
        }
    }

    void setMusic(const char* m) { if (music != m) { music = m; pf.playMusic(m); } }

    bool startLevel(int n) {
        char path[64]; snprintf(path, sizeof path, "levels/level%02d.xml", n);
        std::vector<uint8_t> buf; LevelData lv;
        if (!readFile(pf.dataDir() + path, buf) || !parseLevel(std::string(buf.begin(), buf.end()), lv)) return false;
        if (!world.load(lv, coop, 1234u + (uint32_t)n * 7919u)) return false;
        world.stage = n; level = n; state = ST_PLAYING; stateTimer = 0;
        setMusic("music_game");
        return true;
    }

    void text(int x, int y, int scale, uint32_t argb, const std::string& s) { list.texts.push_back({x, y, scale, argb, s}); }
    void center(int y, int scale, uint32_t argb, const std::string& s) { text(std::max(0, (SCREEN - (int)s.size() * 10 * scale / 2) / 2), y, scale, argb, s); }

    void hud() {
        char b[96];
        if (state == ST_PLAYING || state == ST_WON || state == ST_LOST) {
            snprintf(b, sizeof b, "FASE %d", level + 1); text(8, 4, 1, 0xFFFFFFFF, b);
            int secs = world.frameNumber / FPS; snprintf(b, sizeof b, "%d:%02d", secs / 60, secs % 60); text(SCREEN - 8 - 5 * 10, 4, 1, 0xFFFFFFFF, b);
            snprintf(b, sizeof b, "P1 %d", world.players[0].score); text(8, SCREEN - 24, 1, 0xFFFFE070, b);
            if (coop) { snprintf(b, sizeof b, "P2 %d", world.players[1].score); text(SCREEN - 8 - (int)strlen(b) * 10, SCREEN - 24, 1, 0xFFFF90B0, b); }
        }
        if (state == ST_TITLE) {
            center(120, 3, 0xFFFFFFFF, "BAD ICE-CREAM");
            center(190, 1, 0xFFB0D0FF, "versao Xbox 360");
            center(290, 2, 0xFFFFE070, "START no controle 1: 1 jogador");
            center(330, 2, 0xFFFF90B0, "START no controle 2: COOP (2 jogadores)");
            center(440, 1, 0xFFB0B0B0, "Direcional/analogico: andar   A/B/X/Y: soprar gelo   BACK: sair");
        } else if (state == ST_WON) {
            snprintf(b, sizeof b, "FASE COMPLETA!  +%d", world.timeBonus()); center(240, 2, 0xFFFFFFFF, b);
            if (stateTimer > 60) center(280, 1, 0xFFB0D0FF, "START: proxima fase");
        } else if (state == ST_LOST) {
            center(240, 2, 0xFFFF6060, "FIM DE JOGO");
            if (stateTimer > 40) center(280, 1, 0xFFB0D0FF, "START: tentar de novo");
        } else if (state == ST_END) {
            center(200, 3, 0xFFFFFFFF, "PARABENS!");
            snprintf(b, sizeof b, "Pontuacao final: %d", totalScore); center(260, 2, 0xFFFFE070, b);
            center(320, 1, 0xFFB0D0FF, "START: voltar ao titulo");
        }
    }

    // Um quadro lógico (1/FPS s).
    void tick(PadState pads[2]) {
        bool st[2]; for (int i = 0; i < 2; i++) { st[i] = pads[i].start && !prevStart[i]; prevStart[i] = pads[i].start; }
        stateTimer++;
        switch (state) {
            case ST_TITLE:
                setMusic("music_menu");
                if (opt.skipTitle) { coop = opt.coop == 1; startLevel(opt.startLevel); break; }
                if (!titleDemoReady) titleDemoReady = resetTitleDemo();
                updateTitleDemo();
                if (st[0] || st[1]) {
                    coop = (st[1] && pads[1].connected) || opt.coop == 1;
                    if (opt.coop == 0) coop = false;
                    pf.playSound("select"); totalScore = 0;
                    if (!startLevel(opt.startLevel)) printf("falha ao carregar a fase\n");
                }
                break;
            case ST_PLAYING:
                world.update(pads);
                for (const char* s : world.sounds) pf.playSound(s);
                world.clearSounds();
                if (world.phase == PHASE_WON) { state = ST_WON; stateTimer = 0; totalScore += world.levelScore; setMusic("music_win"); }
                else if (world.phase == PHASE_LOST) { state = ST_LOST; stateTimer = 0; setMusic("music_lose"); }
                break;
            case ST_WON:
                world.frameNumber++;   // mantém as animações andando
                if (st[0] || st[1] || stateTimer > 250) {
                    if (level + 1 >= kLevelCount) { state = ST_END; stateTimer = 0; setMusic("music_menu"); }
                    else if (!startLevel(level + 1)) state = ST_TITLE;
                }
                break;
            case ST_LOST:
                world.frameNumber++;
                for (Player& p : world.players) if (p.present && p.dead) p.deadFrames++;
                if (stateTimer > 40 && (st[0] || st[1])) startLevel(level);
                break;
            case ST_END:
                if (st[0] || st[1]) { state = ST_TITLE; stateTimer = 0; }
                break;
        }
        if (state == ST_TITLE && titleDemoReady) buildScene(titleWorld, atlas, list);
        else if (state == ST_PLAYING || state == ST_WON || state == ST_LOST) buildScene(world, atlas, list);
        else { list.clear(); }
        hud();
        if (state == ST_TITLE) addSnow();
    }
};

}  // namespace

int runGame(Platform& pf, const Options& opt) {
    Game g(pf, opt);
    if (!pf.init()) return 1;
    if (!g.loadAssets()) { pf.shutdown(); return 2; }
    const double dt = 1.0 / FPS;
    double last = pf.now(), acc = dt;   // acc = dt: o primeiro quadro lógico sai logo
    PadState pads[2];
    for (;;) {
        if (!pf.pump(pads)) break;
        if (pads[0].back) break;
        double t = pf.now(); acc += t - last; last = t;
        if (acc > dt * 4) acc = dt * 4;   // não tenta recuperar mais de 4 quadros
        bool ticked = false;
        while (acc >= dt) {
            g.list.texts.clear();
            PadState p2[2] = {pads[0], pads[1]};
            g.tick(p2); acc -= dt; ticked = true;
        }
        (void)ticked;
        pf.present(g.list);
    }
    pf.shutdown();
    return 0;
}

}  // namespace bic
