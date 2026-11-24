# Makefile para StreetVulkan

CC = gcc
CFLAGS = -Wall -Wextra -O2 -Iinclude -MMD -MP
LIBS = -lSDL2 -lvulkan -lm -lpthread

SRCDIR = src
INCDIR = include
BUILDDIR = build
SHADERDIR = shaders

SOURCES = $(wildcard $(SRCDIR)/*.c)
OBJECTS = $(patsubst $(SRCDIR)/%.c, $(BUILDDIR)/%.o, $(SOURCES))
DEPS = $(OBJECTS:.o=.d)
TARGET = street_vulkan

SHADERS_VERT = $(wildcard $(SHADERDIR)/*.vert)
SHADERS_FRAG = $(wildcard $(SHADERDIR)/*.frag)
SPV_VERT = $(patsubst $(SHADERDIR)/%.vert, $(SHADERDIR)/%.spv, $(SHADERS_VERT))
SPV_FRAG = $(patsubst $(SHADERDIR)/%.frag, $(SHADERDIR)/%.spv, $(SHADERS_FRAG))

all: $(BUILDDIR) $(SPV_VERT) $(SPV_FRAG) $(TARGET)

debug: CFLAGS += -DDEBUG -g -O0
debug: all

$(BUILDDIR):
	mkdir -p $(BUILDDIR)

$(SHADERDIR)/%.spv: $(SHADERDIR)/%.vert
	glslangValidator -V $< -o $@

$(SHADERDIR)/%.spv: $(SHADERDIR)/%.frag
	glslangValidator -V $< -o $@

$(BUILDDIR)/%.o: $(SRCDIR)/%.c
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -o $(TARGET) $(LIBS)

-include $(DEPS)

clean:
	rm -rf $(BUILDDIR) $(TARGET) $(SHADERDIR)/*.spv
	rm -rf tools/__pycache__ tests/__pycache__ tools/metrics/__pycache__

TEST_BIN = $(BUILDDIR)/test_c_modules
TEST_ASAN_BIN = $(BUILDDIR)/test_c_modules_asan
TEST_SRCS = tests/test_c_modules.c src/logger.c src/traffic_system.c src/road_graph.c src/obj_loader.c src/ped_system.c src/vulkan_memory_pool.c src/car_system.c src/sector_system.c src/vulkan_gltf.c src/vulkan_swapchain.c src/vulkan_pipeline.c

test: $(BUILDDIR)
	$(CC) $(CFLAGS) $(TEST_SRCS) -o $(TEST_BIN) $(LIBS)
	./$(TEST_BIN)
	python3 -m unittest discover -s tests -v

asan-test: $(BUILDDIR)
	$(CC) -Wall -Wextra -O1 -g -fsanitize=address,undefined -static-libasan -fno-omit-frame-pointer -Iinclude $(TEST_SRCS) -o $(TEST_ASAN_BIN) $(LIBS)
	./$(TEST_ASAN_BIN)

metrics:
	python3 tools/metrics/evaluate_iso25040.py

quality: clean all test asan-test metrics

web-build:
	python3 tools/compile_wat_to_wasm.py
	node --check web/app.js
	node --check web/renderer_webgpu.js
	node --check web/renderer_webgl2.js

web-test: web-build
	python3 -m unittest discover -s tests -v

serve: web-build
	@echo "Lanzando servidor StreetVulkan Web en http://localhost:8080/web/ ..."
	python3 -m http.server 8080

.PHONY: all clean debug test asan-test metrics quality web-build web-test serve
