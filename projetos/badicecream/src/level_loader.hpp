// Carregador das fases do Bad Ice-Cream (formato XML original, sem dependências externas).
// <t>  : grade w*h em RLE "id:contagem,id,..." (contagem omitida = 1), linha a linha.
// <i>  : itens "tipo,x,y|tipo,x,y|..." (x,y em células).
#pragma once
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

struct LevelItem { int type, x, y; };
struct LevelData {
    int w = 0, h = 0;
    std::vector<int> tiles;       // w*h, índice = y*w + x
    std::vector<LevelItem> items;
    int tile(int x, int y) const { return tiles[y * w + x]; }
};

namespace lvl_detail {
inline std::string slice(const std::string& s, const std::string& open, const std::string& close) {
    size_t a = s.find(open); if (a == std::string::npos) return "";
    a += open.size(); size_t b = s.find(close, a);
    return b == std::string::npos ? "" : s.substr(a, b - a);
}
inline int attr(const std::string& s, char name) {  // aceita aspas simples ou duplas
    size_t a = s.find(std::string(" ") + name + "=");
    return a == std::string::npos ? 0 : std::atoi(s.c_str() + a + 4);
}
inline std::vector<std::string> split(const std::string& s, char c) {
    std::vector<std::string> out; std::string cur; std::stringstream ss(s);
    while (std::getline(ss, cur, c)) out.push_back(cur);
    return out;
}
}  // namespace lvl_detail

inline bool parseLevel(const std::string& xml, LevelData& out) {
    using namespace lvl_detail;
    out = LevelData();
    out.w = attr(xml, 'w'); out.h = attr(xml, 'h');
    if (out.w <= 0 || out.h <= 0) return false;
    for (const auto& tok : split(slice(xml, "<t>", "</t>"), ',')) {
        if (tok.empty()) continue;
        size_t c = tok.find(':');
        int id = std::atoi(tok.c_str());
        int n = c == std::string::npos ? 1 : std::atoi(tok.c_str() + c + 1);
        out.tiles.insert(out.tiles.end(), n, id);
    }
    if ((int)out.tiles.size() != out.w * out.h) return false;
    for (const auto& it : split(slice(xml, "<i>", "</i>"), '|')) {
        auto f = split(it, ',');
        if (f.size() == 3) out.items.push_back({std::atoi(f[0].c_str()), std::atoi(f[1].c_str()), std::atoi(f[2].c_str())});
    }
    return true;
}

inline bool loadLevelFile(const std::string& path, LevelData& out) {
    std::ifstream f(path, std::ios::binary); if (!f) return false;
    std::stringstream ss; ss << f.rdbuf();
    return parseLevel(ss.str(), out);
}
