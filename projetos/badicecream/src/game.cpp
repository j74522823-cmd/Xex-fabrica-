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
enum State { ST_TITLE, ST_SELECT, ST_PLAYING, ST_PAUSED, ST_WON, ST_LOST, ST_END };

const char* const kCharacterNames[3] = {"BAUNILHA", "MORANGO", "CHOCOLATE"};
const char* const kCharacterClasses[3] = {"PlayerVanilla", "PlayerStrawberry", "PlayerChocolate"};

struct Game {
    Platform& pf; Options opt;
    Atlas atlas; World world; DrawList list;
    State state = ST_TITLE;
    int level = 0, stateTimer = 0, totalScore = 0;
    bool coop = false;
    bool demoReady = false;
    bool titleLogoAvailable = false;
    int demoFrames = 0;
    bool prevStart[2] = {false, false};
    bool prevShoot[2] = {false, false};
    bool selectionCoop = false;
    int selectedCharacter[2] = {0, 1};
    bool characterConfirmed[2] = {false, false};
    int previousSelectDirection[2] = {0, 0};
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
        // Arte extra do título: página 6, fora do atlas original.
        // Se o arquivo não existir, o menu continua funcionando com o título em texto.
        if (readFile(dir + "title_logo.argb", buf) && buf.size() == 512u * 512u * 4u) {
            std::vector<uint32_t> px(512u * 512u);
            for (size_t k = 0; k < px.size(); k++)
                px[k] = (uint32_t)buf[k * 4] << 24 | (uint32_t)buf[k * 4 + 1] << 16 |
                        (uint32_t)buf[k * 4 + 2] << 8 | buf[k * 4 + 3];
            pf.uploadPage(6, 512, 512, px.data());
            titleLogoAvailable = true;
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
        demoReady = loadTitleDemo();
        return true;
    }

    // Carrega a primeira fase como demonstração do título. A simulação usa
    // controles neutros; ao terminar ou após 20 s, reinicia sem sair do menu.
    bool loadTitleDemo() {
        std::vector<uint8_t> buf;
        LevelData lv;
        if (!readFile(pf.dataDir() + "levels/level00.xml", buf) ||
            !parseLevel(std::string(buf.begin(), buf.end()), lv) ||
            !world.load(lv, false, 0xB1C2026u)) {
            demoReady = false;
            return false;
        }
        world.stage = 0;
        demoFrames = 0;
        demoReady = true;
        return true;
    }

    void setMusic(const char* m) { if (music != m) { music = m; pf.playMusic(m); } }

    bool startLevel(int n) {
        char path[64]; snprintf(path, sizeof path, "levels/level%02d.xml", n);
        std::vector<uint8_t> buf; LevelData lv;
        if (!readFile(pf.dataDir() + path, buf) || !parseLevel(std::string(buf.begin(), buf.end()), lv)) return false;
        if (!world.load(lv, coop, 1234u + (uint32_t)n * 7919u)) return false;
        world.stage = n; level = n;
        for (int i = 0; i < 2; i++) if (world.players[i].present)
            world.players[i].characterId = std::max(0, std::min(2, selectedCharacter[i]));
        state = ST_PLAYING; stateTimer = 0;
        setMusic("music_game");
        return true;
    }

    void text(int x, int y, int scale, uint32_t argb, const std::string& s) { list.texts.push_back({x, y, scale, argb, s}); }
    void center(int y, int scale, uint32_t argb, const std::string& s) { text(std::max(0, (SCREEN - (int)s.size() * 10 * scale / 2) / 2), y, scale, argb, s); }

    void hud() {
        char b[96];
        if (state == ST_PLAYING || state == ST_PAUSED || state == ST_WON || state == ST_LOST) {
            snprintf(b, sizeof b, "FASE %d", level + 1); text(8, 4, 1, 0xFFFFFFFF, b);
            int secs = world.frameNumber / FPS; snprintf(b, sizeof b, "%d:%02d", secs / 60, secs % 60); text(SCREEN - 8 - 5 * 10, 4, 1, 0xFFFFFFFF, b);
            snprintf(b, sizeof b, "P1 %d", world.players[0].score); text(8, SCREEN - 24, 1, 0xFFFFE070, b);
            if (coop) { snprintf(b, sizeof b, "P2 %d", world.players[1].score); text(SCREEN - 8 - (int)strlen(b) * 10, SCREEN - 24, 1, 0xFFFF90B0, b); }
        }
        if (state == ST_TITLE) {
            if (titleLogoAvailable) {
                Quad q = {};
                q.x0 = 105; q.y0 = 4; q.x1 = 445; q.y1 = 344;
                q.u0 = 0; q.v0 = 0; q.u1 = 1; q.v1 = 1;
                q.r = q.g = q.b = q.a = 1; q.page = 6;
                list.quads.push_back(q);
            } else {
                center(72, 3, 0xFFFFFFFF, "BAD ICE-CREAM");
            }
            center(374, 2, 0xFFFFE070, "START");
            center(422, 2, 0xFFFF90B0, "CO-OP");
            center(480, 1, 0xFFE6F4FF, "P1 START: SOLO   P2 START: CO-OP");
        } else if (state == ST_SELECT) {
            center(54, 2, 0xFFFFFFFF, selectionCoop ? "ESCOLHA DOS SORVETES" : "ESCOLHA SEU SORVETE");
            center(112, 1, 0xFFE6F4FF, "D-PAD: TROCAR   BOTAO: CONFIRMAR");
            for (int i = 0; i < (selectionCoop ? 2 : 1); i++) {
                const int x = selectionCoop ? (i == 0 ? 150 : 400) : 275;
                const int id = std::max(0, std::min(2, selectedCharacter[i]));
                const Anim* preview = atlas.find(kCharacterClasses[id], "DownStand");
                if (preview && !preview->f.empty()) {
                    const Frame& f = preview->f[0];
                    const Atlas::Page& pg = atlas.pages[f.page];
                    Quad q = {};
                    q.x0 = (float)x - f.w * 0.5f; q.y0 = 190; q.x1 = q.x0 + f.w; q.y1 = q.y0 + f.h;
                    q.u0 = (float)f.x / pg.w; q.v0 = (float)f.y / pg.h;
                    q.u1 = (float)(f.x + f.w) / pg.w; q.v1 = (float)(f.y + f.h) / pg.h;
                    q.r = q.g = q.b = q.a = 1.f; q.page = f.page;
                    list.quads.push_back(q);
                }
                char label[64];
                snprintf(label, sizeof label, "P%d: %s", i + 1, kCharacterNames[id]);
                text(selectionCoop ? (i == 0 ? 65 : 315) : 190,
                     selectionCoop ? 340 : 340, 2,
                     characterConfirmed[i] ? 0xFF80FF90 : (i == 0 ? 0xFFFFE070 : 0xFFFF90B0), label);
                text(selectionCoop ? (i == 0 ? 65 : 315) : 190, 380, 1,
                     characterConfirmed[i] ? 0xFF80FF90 : 0xFFE6F4FF,
                     characterConfirmed[i] ? "CONFIRMADO" : "ESQUERDA / DIREITA");
            }
            if (selectionCoop && characterConfirmed[0] && characterConfirmed[1])
                center(475, 1, 0xFF80FF90, "INICIANDO...");
        } else if (state == ST_PAUSED) {
            center(205, 3, 0xFFFFFFFF, "PAUSADO");
            center(260, 1, 0xFFFFE070, "START: CONTINUAR");
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
        bool st[2], confirm[2];
        for (int i = 0; i < 2; i++) {
            st[i] = pads[i].start && !prevStart[i]; prevStart[i] = pads[i].start;
            confirm[i] = pads[i].shoot && !prevShoot[i]; prevShoot[i] = pads[i].shoot;
        }
        stateTimer++;
        switch (state) {
            case ST_TITLE:
                setMusic("music_menu");
                if (demoReady) {
                    PadState idle[2] = {};
                    world.update(idle);
                    world.clearSounds(); // a demonstração não dispara áudio de jogo
                    if (world.phase != PHASE_PLAYING || ++demoFrames > FPS * 20)
                        loadTitleDemo();
                }
                if (opt.skipTitle) { coop = opt.coop == 1; startLevel(opt.startLevel); break; }
                if (st[0] || st[1]) {
                    selectionCoop = (st[1] && pads[1].connected) || opt.coop == 1;
                    if (opt.coop == 0) selectionCoop = false;
                    selectedCharacter[0] = 0; selectedCharacter[1] = 1;
                    characterConfirmed[0] = characterConfirmed[1] = false;
                    previousSelectDirection[0] = previousSelectDirection[1] = 0;
                    coop = selectionCoop;
                    pf.playSound("select"); totalScore = 0;
                    state = ST_SELECT; stateTimer = 0;
                }
                break;
            case ST_SELECT:
                for (int i = 0; i < (selectionCoop ? 2 : 1); i++) {
                    if (characterConfirmed[i]) continue;
                    int step = (pads[i].right || pads[i].down) ? 1 : (pads[i].left || pads[i].up) ? -1 : 0;
                    if (step && step != previousSelectDirection[i])
                        selectedCharacter[i] = (selectedCharacter[i] + step + 3) % 3;
                    previousSelectDirection[i] = step;
                    if (confirm[i]) {
                        characterConfirmed[i] = true;
                        pf.playSound("select");
                    }
                }
                if (characterConfirmed[0] && (!selectionCoop || characterConfirmed[1])) {
                    coop = selectionCoop;
                    if (!startLevel(opt.startLevel)) {
                        printf("falha ao carregar a fase\n");
                        state = ST_TITLE;
                    }
                }
                break;
            case ST_PLAYING:
                // START pausa somente durante uma partida ativa. Não atualiza o
                // mundo neste quadro: inimigos, jogadores e relógio ficam congelados.
                if (st[0] || st[1]) {
                    state = ST_PAUSED;
                    stateTimer = 0;
                    break;
                }
                world.update(pads);
                for (const char* s : world.sounds) pf.playSound(s);
                world.clearSounds();
                if (world.phase == PHASE_WON) { state = ST_WON; stateTimer = 0; totalScore += world.levelScore; setMusic("music_win"); }
                else if (world.phase == PHASE_LOST) { state = ST_LOST; stateTimer = 0; setMusic("music_lose"); }
                break;
            case ST_PAUSED:
                // O mundo não recebe update enquanto pausado; START retoma.
                if (st[0] || st[1]) {
                    state = ST_PLAYING;
                    stateTimer = 0;
                }
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
        if (state == ST_PLAYING || state == ST_PAUSED || state == ST_WON || state == ST_LOST ||
            (state == ST_TITLE && demoReady))
            buildScene(world, atlas, list);
        else { list.clear(); }
        hud();
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
