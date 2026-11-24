# Makefile para StreetVulkan

ifeq ($(origin CC),default)
CC = gcc
endif
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

# Default target: Web-First WebGL2 / WebAssembly Client
all: web-build

web: web-build

# Legacy C11 / Vulkan 1.2 Desktop Reference Targets (optional)
legacy-native: $(BUILDDIR) $(SPV_VERT) $(SPV_FRAG) $(TARGET)
native: legacy-native

debug: CFLAGS += -DDEBUG -g -O0
debug: all

$(BUILDDIR):
	mkdir -p $(BUILDDIR)

$(SHADERDIR)/%.spv: $(SHADERDIR)/%.vert
	glslangValidator -V $< -o $@

$(SHADERDIR)/%.spv: $(SHADERDIR)/%.frag
	glslangValidator -V $< -o $@

$(BUILDDIR)/%.o: $(SRCDIR)/%.c | $(BUILDDIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -o $(TARGET) $(LIBS)

TEST_BIN = $(BUILDDIR)/test_c_modules
TEST_ASAN_BIN = $(BUILDDIR)/test_c_modules_asan
TEST_MODULES = logger traffic_system road_graph obj_loader ped_system vulkan_memory_pool car_system sector_system vulkan_gltf vulkan_swapchain vulkan_pipeline
TEST_SRCS = tests/test_c_modules.c $(patsubst %, $(SRCDIR)/%.c, $(TEST_MODULES))
TEST_OBJS = $(BUILDDIR)/test_c_modules.o $(patsubst %, $(BUILDDIR)/%.o, $(TEST_MODULES))
TEST_DEPS = $(BUILDDIR)/test_c_modules.d

ASAN_BUILDDIR = $(BUILDDIR)/asan
ASAN_CFLAGS = -Wall -Wextra -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude -MMD -MP
ASAN_OBJS = $(patsubst $(BUILDDIR)/%.o, $(ASAN_BUILDDIR)/%.o, $(TEST_OBJS))
ASAN_DEPS = $(ASAN_OBJS:.o=.d)

-include $(DEPS) $(TEST_DEPS) $(ASAN_DEPS)

clean:
	rm -rf $(BUILDDIR) $(TARGET) $(SHADERDIR)/*.spv
	rm -rf tools/__pycache__ tests/__pycache__ tools/metrics/__pycache__

$(BUILDDIR)/test_c_modules.o: tests/test_c_modules.c | $(BUILDDIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(TEST_BIN): $(TEST_OBJS) | $(BUILDDIR)
	$(CC) $(TEST_OBJS) -o $(TEST_BIN) $(LIBS)

test: $(TEST_BIN)
	./$(TEST_BIN)
	python3 -m unittest discover -s tests -v

$(ASAN_BUILDDIR):
	mkdir -p $(ASAN_BUILDDIR)

$(ASAN_BUILDDIR)/%.o: $(SRCDIR)/%.c | $(ASAN_BUILDDIR)
	$(CC) $(ASAN_CFLAGS) -c $< -o $@

$(ASAN_BUILDDIR)/test_c_modules.o: tests/test_c_modules.c | $(ASAN_BUILDDIR)
	$(CC) $(ASAN_CFLAGS) -c $< -o $@

$(TEST_ASAN_BIN): $(ASAN_OBJS) | $(ASAN_BUILDDIR)
	$(CC) -fsanitize=address,undefined -static-libasan $(ASAN_OBJS) -o $(TEST_ASAN_BIN) $(LIBS)

asan-test: $(TEST_ASAN_BIN)
	./$(TEST_ASAN_BIN)

metrics: $(SPV_VERT) $(SPV_FRAG)
	python3 tools/metrics/evaluate_iso25040.py

quality:
	$(MAKE) clean
	$(MAKE) all
	$(MAKE) test
	$(MAKE) asan-test
	$(MAKE) metrics

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

.PHONY: all web legacy-native native clean debug test asan-test metrics quality web-build web-test serve
