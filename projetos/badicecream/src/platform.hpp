// Interface entre o jogo (portátil) e a plataforma (Xbox 360 via XSDK, ou host para testes).
#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include "engine.hpp"

namespace bic {

// Retângulo texturizado em coordenadas do palco (550x550). A plataforma escala para a tela.
struct Quad { float x0, y0, x1, y1, u0, v0, u1, v1, r, g, b, a; int page; };
struct TextItem { int x, y, scale; uint32_t argb; std::string s; };   // x,y em coordenadas do palco; scale 1..8 (fonte 10x20)
struct DrawList {
    std::vector<Quad> quads;
    std::vector<TextItem> texts;
    uint32_t clearArgb = 0xFF141B3A;
    void clear() { quads.clear(); texts.clear(); }
};

class Platform {
public:
    virtual ~Platform() {}
    virtual std::string dataDir() const = 0;                       // pasta com atlas.txt, levels/, snd/ (termina em '/')
    virtual bool init() = 0;
    virtual bool pump(PadState pads[2]) = 0;                       // lê os controles; false = encerrar
    virtual void uploadPage(int page, int w, int h, const uint32_t* argb) = 0;   // 0xAARRGGBB
    virtual void present(const DrawList& list) = 0;                // desenha e apresenta (sincronizado com o vblank)
    virtual void loadSound(const std::string& name, const int16_t* pcm, size_t frames, bool loop) = 0;   // mono 48 kHz
    virtual void playSound(const std::string& name) = 0;
    virtual void playMusic(const std::string& name) = 0;           // "" = parar
    virtual double now() = 0;                                      // segundos, monotônico
    virtual void shutdown() = 0;
};

struct Options {
    int startLevel = 0;
    int coop = -1;          // -1: o jogador escolhe no título; 0/1 força
    int skipTitle = 0;      // 1: começa direto na fase (testes)
};
int runGame(Platform& pf, const Options& opt);

}  // namespace bic
