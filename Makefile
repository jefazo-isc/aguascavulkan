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
	rm -rf tools/__pycache__

.PHONY: all clean
