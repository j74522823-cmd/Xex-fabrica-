// Atlas de sprites em tempo de execução (formato de tools/export_runtime.py).
#pragma once
#include <cstdio>
#include <cstdlib>
#include <string>
#include <unordered_map>
#include <vector>

namespace bic {

struct Frame { int page, x, y, w, h, ox, oy; };
struct Anim { std::vector<Frame> f; };

class Atlas {
public:
    struct Page { int w = 0, h = 0; std::string file; };
    std::vector<Page> pages;

    bool parse(const std::string& text) {
        size_t pos = 0;
        while (pos < text.size()) {
            size_t e = text.find('\n', pos);
            if (e == std::string::npos) e = text.size();
            std::string line = text.substr(pos, e - pos); pos = e + 1;
            if (line.compare(0, 5, "page ") == 0) {
                int n, w, h; char file[128];
                if (sscanf(line.c_str(), "page %d %d %d %127s", &n, &w, &h, file) == 4) {
                    if ((int)pages.size() <= n) pages.resize(n + 1);
                    pages[n].w = w; pages[n].h = h; pages[n].file = file;
                }
            } else if (line.compare(0, 2, "F ") == 0) {
                char cls[96], an[96]; int idx; Frame fr;
                if (sscanf(line.c_str(), "F %95s %95s %d %d %d %d %d %d %d %d", cls, an, &idx, &fr.page, &fr.x, &fr.y, &fr.w, &fr.h, &fr.ox, &fr.oy) == 10)
                    map_[std::string(cls) + "|" + an].f.push_back(fr);
            }
        }
        return !pages.empty() && !map_.empty();
    }
    const Anim* find(const std::string& cls, const std::string& anim) const {
        auto it = map_.find(cls + "|" + anim);
        return it == map_.end() ? nullptr : &it->second;
    }
    size_t animCount() const { return map_.size(); }

private:
    std::unordered_map<std::string, Anim> map_;
};

}  // namespace bic
