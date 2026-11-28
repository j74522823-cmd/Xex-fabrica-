# Testes no PC (nao precisa do xsdk). O jogo do Xbox usa o CMakeLists.txt.
CC ?= gcc
CFLAGS = -O2 -Wall -Wextra -std=c11 -D_POSIX_C_SOURCE=199309L
CORE = src/map.c src/collision.c src/game.c
MAP ?= build/farm.rfm

all: build/sim build/draw_test

build/sim: tests/sim.c $(CORE)
	@mkdir -p build
	$(CC) $(CFLAGS) -o $@ tests/sim.c $(CORE) -lm

build/draw_test: tests/draw_test.c tests/render_stub.c src/draw_scene.c $(CORE)
	@mkdir -p build
	$(CC) $(CFLAGS) -o $@ tests/draw_test.c tests/render_stub.c src/draw_scene.c $(CORE) -lm

test: all
	./build/sim $(MAP)
	./build/draw_test $(MAP)

.PHONY: all test
