// Monta a lista de desenho (quads em coordenadas do palco) a partir do estado do mundo.
#pragma once
#include "atlas.hpp"
#include "engine.hpp"
#include "platform.hpp"

namespace bic {
void buildScene(const World& w, const Atlas& atlas, DrawList& out);
}
