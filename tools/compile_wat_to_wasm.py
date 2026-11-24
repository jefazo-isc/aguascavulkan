#!/usr/bin/env python3
"""Pure-Python WebAssembly Text (.wat) to WebAssembly Binary (.wasm) assembler.

Supports standard W3C WebAssembly 1.0 MVP S-expression syntax (folded and flat
instructions, named identifiers for functions/params/locals/globals/labels/types,
inline and standalone exports, memories, globals, data segments, and comments).

Usage:
    python3 tools/compile_wat_to_wasm.py [input.wat] [output.wasm]

Defaults to:
    web/street_vulkan_core.wat -> web/street_vulkan_core.wasm
"""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path
from typing import Any


WASM_MAGIC = b"\x00asm"
WASM_VERSION = b"\x01\x00\x00\x00"

VALTYPE_CODES: dict[str, int] = {
    "i32": 0x7F,
    "i64": 0x7E,
    "f32": 0x7D,
    "f64": 0x7C,
    "funcref": 0x70,
    "anyfunc": 0x70,
}

# Memory instructions mapped to (opcode, default_align_log2)
MEM_OPCODES: dict[str, tuple[int, int]] = {
    "i32.load": (0x28, 2),
    "i64.load": (0x29, 3),
    "f32.load": (0x2A, 2),
    "f64.load": (0x2B, 3),
    "i32.load8_s": (0x2C, 0),
    "i32.load8_u": (0x2D, 0),
    "i32.load16_s": (0x2E, 1),
    "i32.load16_u": (0x2F, 1),
    "i64.load8_s": (0x30, 0),
    "i64.load8_u": (0x31, 0),
    "i64.load16_s": (0x32, 1),
    "i64.load16_u": (0x33, 1),
    "i64.load32_s": (0x34, 2),
    "i64.load32_u": (0x35, 2),
    "i32.store": (0x36, 2),
    "i64.store": (0x37, 3),
    "f32.store": (0x38, 2),
    "f64.store": (0x39, 3),
    "i32.store8": (0x3A, 0),
    "i32.store16": (0x3B, 1),
    "i64.store8": (0x3C, 0),
    "i64.store16": (0x3D, 1),
    "i64.store32": (0x3E, 2),
}

# Zero-immediate instructions (control/parametric/numeric)
SIMPLE_OPCODES: dict[str, int] = {
    "unreachable": 0x00,
    "nop": 0x01,
    "return": 0x0F,
    "drop": 0x1A,
    "select": 0x1B,
    # i32 comparisons & math
    "i32.eqz": 0x45,
    "i32.eq": 0x46,
    "i32.ne": 0x47,
    "i32.lt_s": 0x48,
    "i32.lt_u": 0x49,
    "i32.gt_s": 0x4A,
    "i32.gt_u": 0x4B,
    "i32.le_s": 0x4C,
    "i32.le_u": 0x4D,
    "i32.ge_s": 0x4E,
    "i32.ge_u": 0x4F,
    "i32.clz": 0x67,
    "i32.ctz": 0x68,
    "i32.popcnt": 0x69,
    "i32.add": 0x6A,
    "i32.sub": 0x6B,
    "i32.mul": 0x6C,
    "i32.div_s": 0x6D,
    "i32.div_u": 0x6E,
    "i32.rem_s": 0x6F,
    "i32.rem_u": 0x70,
    "i32.and": 0x71,
    "i32.or": 0x72,
    "i32.xor": 0x73,
    "i32.shl": 0x74,
    "i32.shr_s": 0x75,
    "i32.shr_u": 0x76,
    "i32.rotl": 0x77,
    "i32.rotr": 0x78,
    # i64 comparisons & math
    "i64.eqz": 0x50,
    "i64.eq": 0x51,
    "i64.ne": 0x52,
    "i64.lt_s": 0x53,
    "i64.lt_u": 0x54,
    "i64.gt_s": 0x55,
    "i64.gt_u": 0x56,
    "i64.le_s": 0x57,
    "i64.le_u": 0x58,
    "i64.ge_s": 0x59,
    "i64.ge_u": 0x5A,
    "i64.clz": 0x79,
    "i64.ctz": 0x7A,
    "i64.popcnt": 0x7B,
    "i64.add": 0x7C,
    "i64.sub": 0x7D,
    "i64.mul": 0x7E,
    "i64.div_s": 0x7F,
    "i64.div_u": 0x80,
    "i64.rem_s": 0x81,
    "i64.rem_u": 0x82,
    "i64.and": 0x83,
    "i64.or": 0x84,
    "i64.xor": 0x85,
    "i64.shl": 0x86,
    "i64.shr_s": 0x87,
    "i64.shr_u": 0x88,
    "i64.rotl": 0x89,
    "i64.rotr": 0x8A,
    # f32 comparisons & math
    "f32.eq": 0x5B,
    "f32.ne": 0x5C,
    "f32.lt": 0x5D,
    "f32.gt": 0x5E,
    "f32.le": 0x5F,
    "f32.ge": 0x60,
    "f32.abs": 0x8B,
    "f32.neg": 0x8C,
    "f32.ceil": 0x8D,
    "f32.floor": 0x8E,
    "f32.trunc": 0x8F,
    "f32.nearest": 0x90,
    "f32.sqrt": 0x91,
    "f32.add": 0x92,
    "f32.sub": 0x93,
    "f32.mul": 0x94,
    "f32.div": 0x95,
    "f32.min": 0x96,
    "f32.max": 0x97,
    "f32.copysign": 0x98,
    # f64 comparisons & math
    "f64.eq": 0x61,
    "f64.ne": 0x62,
    "f64.lt": 0x63,
    "f64.gt": 0x64,
    "f64.le": 0x65,
    "f64.ge": 0x66,
    "f64.abs": 0x99,
    "f64.neg": 0x9A,
    "f64.ceil": 0x9B,
    "f64.floor": 0x9C,
    "f64.trunc": 0x9D,
    "f64.nearest": 0x9E,
    "f64.sqrt": 0x9F,
    "f64.add": 0xA0,
    "f64.sub": 0xA1,
    "f64.mul": 0xA2,
    "f64.div": 0xA3,
    "f64.min": 0xA4,
    "f64.max": 0xA5,
    "f64.copysign": 0xA6,
    # Conversions
    "i32.wrap_i64": 0xA7,
    "i32.trunc_f32_s": 0xA8,
    "i32.trunc_f32_u": 0xA9,
    "i32.trunc_f64_s": 0xAA,
    "i32.trunc_f64_u": 0xAB,
    "i64.extend_i32_s": 0xAC,
    "i64.extend_i32_u": 0xAD,
    "i64.trunc_f32_s": 0xAE,
    "i64.trunc_f32_u": 0xAF,
    "i64.trunc_f64_s": 0xB0,
    "i64.trunc_f64_u": 0xB1,
    "f32.convert_i32_s": 0xB2,
    "f32.convert_i32_u": 0xB3,
    "f32.convert_i64_s": 0xB4,
    "f32.convert_i64_u": 0xB5,
    "f32.demote_f64": 0xB6,
    "f64.convert_i32_s": 0xB7,
    "f64.convert_i32_u": 0xB8,
    "f64.convert_i64_s": 0xB9,
    "f64.convert_i64_u": 0xBA,
    "f64.promote_f32": 0xBB,
    "i32.reinterpret_f32": 0xBC,
    "i64.reinterpret_f64": 0xBD,
    "f32.reinterpret_i32": 0xBE,
    "f64.reinterpret_i64": 0xBF,
}


class WatString:
    """Represents a quoted WAT string literal with raw byte payload."""

    def __init__(self, raw_bytes: bytes) -> None:
        self.raw_bytes = raw_bytes

    def as_utf8(self) -> str:
        return self.raw_bytes.decode("utf-8")


class WatSyntaxError(ValueError):
    """Raised when WAT input has invalid syntax or unsupported forms."""


def uleb128(value: int) -> bytes:
    if value < 0:
        raise ValueError(f"ULEB128 requires non-negative integer, got {value}")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def sleb128(value: int) -> bytes:
    out = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40) != 0):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def encode_vec(items: list[bytes]) -> bytes:
    return uleb128(len(items)) + b"".join(items)


def encode_section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + uleb128(len(payload)) + payload


def encode_name(name: str) -> bytes:
    data = name.encode("utf-8")
    return uleb128(len(data)) + data


def parse_int_literal(token: str, bits: int = 32) -> int:
    clean = token.replace("_", "")
    val = int(clean, 0)
    mask = (1 << bits) - 1
    sign_bit = 1 << (bits - 1)
    if val >= sign_bit:
        # Allow unsigned hex bit patterns like 0xffffffff for i32.const
        if val <= mask:
            return val - (1 << bits)
    return val


def parse_uint_literal(token: str) -> int:
    return int(token.replace("_", ""), 0)


def parse_float_literal(token: str) -> float:
    clean = token.replace("_", "").lower()
    if clean in ("inf", "+inf"):
        return math.inf
    if clean == "-inf":
        return -math.inf
    if clean in ("nan", "+nan"):
        return math.nan
    if clean == "-nan":
        return -math.nan
    if clean.startswith("0x") or clean.startswith("-0x") or clean.startswith("+0x"):
        return float.fromhex(clean)
    return float(clean)


def tokenize_wat(source: str) -> list[Any]:
    tokens: list[Any] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        # Line comment ;;
        if ch == ";" and i + 1 < n and source[i + 1] == ";":
            newline = source.find("\n", i + 2)
            i = n if newline == -1 else newline + 1
            continue
        # Block comment (; ... ;) with nesting
        if ch == "(" and i + 1 < n and source[i + 1] == ";":
            depth = 1
            i += 2
            while i < n and depth > 0:
                if source[i] == "(" and i + 1 < n and source[i + 1] == ";":
                    depth += 1
                    i += 2
                elif source[i] == ";" and i + 1 < n and source[i + 1] == ")":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth != 0:
                raise WatSyntaxError("Unterminated block comment '(;'")
            continue
        if ch == "(" or ch == ")":
            tokens.append(ch)
            i += 1
            continue
        if ch == '"':
            i += 1
            buf = bytearray()
            while i < n and source[i] != '"':
                c = source[i]
                if c == "\\":
                    i += 1
                    if i >= n:
                        raise WatSyntaxError("Unterminated string escape")
                    esc = source[i]
                    if esc == "n":
                        buf.append(0x0A)
                    elif esc == "r":
                        buf.append(0x0D)
                    elif esc == "t":
                        buf.append(0x09)
                    elif esc == '"':
                        buf.append(0x22)
                    elif esc == "'":
                        buf.append(0x27)
                    elif esc == "\\":
                        buf.append(0x5C)
                    elif esc in "0123456789abcdefABCDEF" and i + 1 < n:
                        buf.append(int(source[i : i + 2], 16))
                        i += 1
                    else:
                        raise WatSyntaxError(f"Invalid string escape \\{esc}")
                    i += 1
                else:
                    buf.extend(c.encode("utf-8"))
                    i += 1
            if i >= n or source[i] != '"':
                raise WatSyntaxError("Unterminated string literal")
            i += 1
            tokens.append(WatString(bytes(buf)))
            continue
        # Atom token
        start = i
        while i < n and not source[i].isspace() and source[i] not in ('(', ')', '"'):
            if source[i] == ";" and i + 1 < n and source[i + 1] == ";":
                break
            i += 1
        tokens.append(source[start:i])
    return tokens


def parse_sexprs(tokens: list[Any]) -> list[Any]:
    stack: list[list[Any]] = [[]]
    for tok in tokens:
        if tok == "(":
            new_list: list[Any] = []
            stack[-1].append(new_list)
            stack.append(new_list)
        elif tok == ")":
            if len(stack) == 1:
                raise WatSyntaxError("Unexpected closing ')'")
            stack.pop()
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise WatSyntaxError("Unclosed '(' in WAT file")
    return stack[0]


def is_id(tok: Any) -> bool:
    return isinstance(tok, str) and tok.startswith("$")


def parse_memarg(items: list[Any], pos: int, default_align: int) -> tuple[int, int, int]:
    offset = 0
    align_log2 = default_align
    while pos < len(items) and isinstance(items[pos], str):
        tok = items[pos]
        if tok.startswith("offset="):
            offset = parse_uint_literal(tok.split("=", 1)[1])
            pos += 1
        elif tok.startswith("align="):
            align_bytes = parse_uint_literal(tok.split("=", 1)[1])
            if align_bytes <= 0 or (align_bytes & (align_bytes - 1)) != 0:
                raise WatSyntaxError(f"align must be power of 2, got {align_bytes}")
            align_log2 = align_bytes.bit_length() - 1
            pos += 1
        else:
            break
    if align_log2 > default_align:
        raise WatSyntaxError(f"Alignment 2^{align_log2} exceeds natural alignment 2^{default_align}")
    return align_log2, offset, pos


class ModuleAssembler:
    """Compiles a parsed WAT `(module ...)` S-expression to W3C WASM binary."""

    def __init__(self) -> None:
        self.types: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
        self.type_map: dict[tuple[tuple[int, ...], tuple[int, ...]], int] = {}
        self.named_types: dict[str, int] = {}

        self.funcs: list[dict[str, Any]] = []
        self.func_names: dict[str, int] = {}

        self.memories: list[dict[str, Any]] = []
        self.mem_names: dict[str, int] = {}

        self.globals: list[dict[str, Any]] = []
        self.global_names: dict[str, int] = {}

        self.exports: list[tuple[str, int, Any]] = []
        self.data_segments: list[tuple[int, bytes, bytes]] = []
        self.start_func: Any = None

    def intern_type(self, params: list[int], results: list[int]) -> int:
        key = (tuple(params), tuple(results))
        if key not in self.type_map:
            idx = len(self.types)
            self.types.append(key)
            self.type_map[key] = idx
        return self.type_map[key]

    def resolve_func(self, ref: Any) -> int:
        if isinstance(ref, str) and ref.startswith("$"):
            if ref not in self.func_names:
                raise WatSyntaxError(f"Unknown function identifier {ref}")
            return self.func_names[ref]
        return parse_uint_literal(str(ref))

    def resolve_global(self, ref: Any) -> int:
        if isinstance(ref, str) and ref.startswith("$"):
            if ref not in self.global_names:
                raise WatSyntaxError(f"Unknown global identifier {ref}")
            return self.global_names[ref]
        return parse_uint_literal(str(ref))

    def resolve_mem(self, ref: Any) -> int:
        if isinstance(ref, str) and ref.startswith("$"):
            if ref not in self.mem_names:
                raise WatSyntaxError(f"Unknown memory identifier {ref}")
            return self.mem_names[ref]
        return parse_uint_literal(str(ref))

    def assemble(self, module_expr: list[Any]) -> bytes:
        if not module_expr or module_expr[0] != "module":
            raise WatSyntaxError("Top-level S-expression must be '(module ...)'")

        idx = 1
        if idx < len(module_expr) and is_id(module_expr[idx]):
            idx += 1

        # Pass 1: register declarations (types, memories, globals, func signatures, exports, data)
        for item in module_expr[idx:]:
            if not isinstance(item, list) or not item:
                raise WatSyntaxError(f"Expected S-expression inside module, got {item!r}")
            kind = item[0]
            if kind == "type":
                self._parse_type_decl(item)
            elif kind == "memory":
                self._parse_memory_decl(item)
            elif kind == "global":
                self._parse_global_decl(item)
            elif kind == "func":
                self._parse_func_header(item)
            elif kind == "export":
                self._parse_export_decl(item)
            elif kind == "start":
                self.start_func = item[1]
            elif kind == "data":
                self._parse_data_decl(item)
            else:
                raise WatSyntaxError(f"Unsupported top-level module section '{kind}'")

        # Pass 2: assemble function bodies
        code_bodies: list[bytes] = []
        for f in self.funcs:
            code_bodies.append(self._assemble_func_body(f))

        # Assemble binary sections
        out = bytearray(WASM_MAGIC + WASM_VERSION)

        # Section 1: Type
        if self.types:
            type_entries = []
            for params, results in self.types:
                entry = (
                    b"\x60"
                    + uleb128(len(params))
                    + bytes(params)
                    + uleb128(len(results))
                    + bytes(results)
                )
                type_entries.append(entry)
            out.extend(encode_section(1, encode_vec(type_entries)))

        # Section 3: Function
        if self.funcs:
            func_type_indices = [uleb128(f["type_idx"]) for f in self.funcs]
            out.extend(encode_section(3, encode_vec(func_type_indices)))

        # Section 5: Memory
        if self.memories:
            mem_entries = []
            for m in self.memories:
                if m["max"] is not None:
                    mem_entries.append(b"\x01" + uleb128(m["min"]) + uleb128(m["max"]))
                else:
                    mem_entries.append(b"\x00" + uleb128(m["min"]))
            out.extend(encode_section(5, encode_vec(mem_entries)))

        # Section 6: Global
        if self.globals:
            glob_entries = []
            for g in self.globals:
                mut_byte = 0x01 if g["mutable"] else 0x00
                glob_entries.append(bytes([g["valtype"], mut_byte]) + g["init_bytes"] + b"\x0b")
            out.extend(encode_section(6, encode_vec(glob_entries)))

        # Section 7: Export
        if self.exports:
            exp_entries = []
            for name, kind_code, ref in self.exports:
                if kind_code == 0x00:
                    target_idx = self.resolve_func(ref)
                elif kind_code == 0x02:
                    target_idx = self.resolve_mem(ref)
                elif kind_code == 0x03:
                    target_idx = self.resolve_global(ref)
                else:
                    raise WatSyntaxError(f"Unsupported export kind {kind_code}")
                exp_entries.append(encode_name(name) + bytes([kind_code]) + uleb128(target_idx))
            out.extend(encode_section(7, encode_vec(exp_entries)))

        # Section 8: Start
        if self.start_func is not None:
            start_idx = self.resolve_func(self.start_func)
            out.extend(encode_section(8, uleb128(start_idx)))

        # Section 10: Code
        if code_bodies:
            out.extend(encode_section(10, encode_vec(code_bodies)))

        # Section 11: Data
        if self.data_segments:
            seg_entries = []
            for mem_idx, offset_expr, data_bytes in self.data_segments:
                seg_entries.append(
                    uleb128(mem_idx)
                    + offset_expr
                    + b"\x0b"
                    + uleb128(len(data_bytes))
                    + data_bytes
                )
            out.extend(encode_section(11, encode_vec(seg_entries)))

        return bytes(out)

    def _parse_type_decl(self, item: list[Any]) -> None:
        pos = 1
        name = None
        if pos < len(item) and is_id(item[pos]):
            name = item[pos]
            pos += 1
        func_sig = item[pos]
        if not isinstance(func_sig, list) or func_sig[0] != "func":
            raise WatSyntaxError("Expected '(func ...)' in type declaration")
        params: list[int] = []
        results: list[int] = []
        for sub in func_sig[1:]:
            if isinstance(sub, list) and sub[0] == "param":
                p = 1
                if p < len(sub) and is_id(sub[p]):
                    p += 1
                for vt in sub[p:]:
                    params.append(VALTYPE_CODES[vt])
            elif isinstance(sub, list) and sub[0] == "result":
                for vt in sub[1:]:
                    results.append(VALTYPE_CODES[vt])
        t_idx = self.intern_type(params, results)
        if name is not None:
            self.named_types[name] = t_idx

    def _parse_memory_decl(self, item: list[Any]) -> None:
        mem_idx = len(self.memories)
        pos = 1
        if pos < len(item) and is_id(item[pos]):
            self.mem_names[item[pos]] = mem_idx
            pos += 1
        while pos < len(item) and isinstance(item[pos], list) and item[pos][0] == "export":
            exp_name = item[pos][1].as_utf8()
            self.exports.append((exp_name, 0x02, mem_idx))
            pos += 1
        min_pages = parse_uint_literal(str(item[pos]))
        pos += 1
        max_pages = parse_uint_literal(str(item[pos])) if pos < len(item) else None
        self.memories.append({"min": min_pages, "max": max_pages})

    def _parse_global_decl(self, item: list[Any]) -> None:
        g_idx = len(self.globals)
        pos = 1
        if pos < len(item) and is_id(item[pos]):
            self.global_names[item[pos]] = g_idx
            pos += 1
        while pos < len(item) and isinstance(item[pos], list) and item[pos][0] == "export":
            exp_name = item[pos][1].as_utf8()
            self.exports.append((exp_name, 0x03, g_idx))
            pos += 1
        type_spec = item[pos]
        pos += 1
        if isinstance(type_spec, list) and type_spec[0] == "mut":
            mutable = True
            valtype = VALTYPE_CODES[type_spec[1]]
        else:
            mutable = False
            valtype = VALTYPE_CODES[type_spec]
        init_bytes = self._compile_const_expr(item[pos])
        self.globals.append({"valtype": valtype, "mutable": mutable, "init_bytes": init_bytes})

    def _compile_const_expr(self, expr: list[Any]) -> bytes:
        op = expr[0]
        if op == "i32.const":
            return b"\x41" + sleb128(parse_int_literal(expr[1], 32))
        if op == "i64.const":
            return b"\x42" + sleb128(parse_int_literal(expr[1], 64))
        if op == "f32.const":
            return b"\x43" + struct.pack("<f", parse_float_literal(expr[1]))
        if op == "f64.const":
            return b"\x44" + struct.pack("<d", parse_float_literal(expr[1]))
        if op == "global.get":
            return b"\x23" + uleb128(self.resolve_global(expr[1]))
        raise WatSyntaxError(f"Unsupported constant initializer expression: {expr!r}")

    def _parse_export_decl(self, item: list[Any]) -> None:
        name = item[1].as_utf8()
        desc = item[2]
        kind_str = desc[0]
        kind_map = {"func": 0x00, "memory": 0x02, "global": 0x03}
        if kind_str not in kind_map:
            raise WatSyntaxError(f"Unsupported export kind '{kind_str}'")
        self.exports.append((name, kind_map[kind_str], desc[1]))

    def _parse_data_decl(self, item: list[Any]) -> None:
        pos = 1
        mem_idx = 0
        if pos < len(item) and is_id(item[pos]):
            pos += 1
        if pos < len(item) and isinstance(item[pos], list) and item[pos][0] == "memory":
            mem_idx = self.resolve_mem(item[pos][1])
            pos += 1
        offset_expr_node = item[pos]
        if isinstance(offset_expr_node, list) and offset_expr_node[0] == "offset":
            offset_expr_node = offset_expr_node[1]
        offset_bytes = self._compile_const_expr(offset_expr_node)
        pos += 1
        payload = bytearray()
        while pos < len(item):
            s = item[pos]
            if not isinstance(s, WatString):
                raise WatSyntaxError(f"Expected string literal in data segment, got {s!r}")
            payload.extend(s.raw_bytes)
            pos += 1
        self.data_segments.append((mem_idx, offset_bytes, bytes(payload)))

    def _parse_func_header(self, item: list[Any]) -> None:
        func_idx = len(self.funcs)
        pos = 1
        if pos < len(item) and is_id(item[pos]):
            self.func_names[item[pos]] = func_idx
            pos += 1

        while pos < len(item) and isinstance(item[pos], list) and item[pos][0] == "export":
            exp_name = item[pos][1].as_utf8()
            self.exports.append((exp_name, 0x00, func_idx))
            pos += 1

        explicit_type: int | None = None
        if pos < len(item) and isinstance(item[pos], list) and item[pos][0] == "type":
            tref = item[pos][1]
            explicit_type = self.named_types[tref] if is_id(tref) else parse_uint_literal(str(tref))
            pos += 1

        params: list[int] = []
        results: list[int] = []
        local_names: dict[str, int] = {}
        locals_list: list[int] = []

        while pos < len(item) and isinstance(item[pos], list) and item[pos][0] in ("param", "result", "local"):
            sub = item[pos]
            tag = sub[0]
            if tag == "param":
                if len(sub) >= 2 and is_id(sub[1]):
                    if len(sub) != 3:
                        raise WatSyntaxError(f"Named param must have exactly one type: {sub!r}")
                    local_names[sub[1]] = len(params)
                    params.append(VALTYPE_CODES[sub[2]])
                else:
                    for vt in sub[1:]:
                        params.append(VALTYPE_CODES[vt])
            elif tag == "result":
                for vt in sub[1:]:
                    results.append(VALTYPE_CODES[vt])
            elif tag == "local":
                if len(sub) >= 2 and is_id(sub[1]):
                    if len(sub) != 3:
                        raise WatSyntaxError(f"Named local must have exactly one type: {sub!r}")
                    local_names[sub[1]] = len(params) + len(locals_list)
                    locals_list.append(VALTYPE_CODES[sub[2]])
                else:
                    for vt in sub[1:]:
                        locals_list.append(VALTYPE_CODES[vt])
            pos += 1

        type_idx = explicit_type if explicit_type is not None else self.intern_type(params, results)
        self.funcs.append(
            {
                "type_idx": type_idx,
                "local_names": local_names,
                "locals": locals_list,
                "body": item[pos:],
            }
        )

    def _assemble_func_body(self, func: dict[str, Any]) -> bytes:
        # Run-length encode locals
        groups: list[tuple[int, int]] = []
        for vt in func["locals"]:
            if groups and groups[-1][1] == vt:
                groups[-1] = (groups[-1][0] + 1, vt)
            else:
                groups.append((1, vt))
        local_header = encode_vec([uleb128(cnt) + bytes([vt]) for cnt, vt in groups])

        code = bytearray()
        label_stack: list[str | None] = []
        self._compile_seq(func["body"], func["local_names"], label_stack, code)
        if label_stack:
            raise WatSyntaxError(f"Unclosed block/loop/if labels in function body: {label_stack}")
        body = local_header + bytes(code) + b"\x0b"
        return uleb128(len(body)) + body

    def _resolve_local(self, ref: Any, local_names: dict[str, int]) -> int:
        if is_id(ref):
            if ref not in local_names:
                raise WatSyntaxError(f"Unknown local identifier {ref}")
            return local_names[ref]
        return parse_uint_literal(str(ref))

    def _resolve_label(self, ref: Any, label_stack: list[str | None]) -> int:
        if is_id(ref):
            for depth, lbl in enumerate(reversed(label_stack)):
                if lbl == ref:
                    return depth
            raise WatSyntaxError(f"Unknown branch label {ref}")
        return parse_uint_literal(str(ref))

    def _parse_block_sig(self, items: list[Any], pos: int) -> tuple[str | None, int, int]:
        label: str | None = None
        blocktype = 0x40
        if pos < len(items) and is_id(items[pos]):
            label = items[pos]
            pos += 1
        if pos < len(items) and isinstance(items[pos], list) and items[pos][0] == "result":
            res_list = items[pos][1:]
            if len(res_list) != 1:
                raise WatSyntaxError("Multi-value block results are not supported in MVP")
            blocktype = VALTYPE_CODES[res_list[0]]
            pos += 1
        return label, blocktype, pos

    def _compile_seq(
        self,
        items: list[Any],
        local_names: dict[str, int],
        label_stack: list[str | None],
        out: bytearray,
    ) -> None:
        pos = 0
        while pos < len(items):
            node = items[pos]
            if isinstance(node, list):
                self._compile_folded(node, local_names, label_stack, out)
                pos += 1
            else:
                pos = self._compile_flat(items, pos, local_names, label_stack, out)

    def _compile_folded(
        self,
        node: list[Any],
        local_names: dict[str, int],
        label_stack: list[str | None],
        out: bytearray,
    ) -> None:
        if not node or not isinstance(node[0], str):
            raise WatSyntaxError(f"Invalid folded expression: {node!r}")
        op = node[0]

        if op in ("block", "loop"):
            label, btype, pos = self._parse_block_sig(node, 1)
            out.append(0x02 if op == "block" else 0x03)
            out.append(btype)
            label_stack.append(label)
            self._compile_seq(node[pos:], local_names, label_stack, out)
            label_stack.pop()
            out.append(0x0B)
            return

        if op == "if":
            label, btype, pos = self._parse_block_sig(node, 1)
            cond_exprs: list[Any] = []
            then_node: list[Any] | None = None
            else_node: list[Any] | None = None
            while pos < len(node):
                sub = node[pos]
                if isinstance(sub, list) and sub and sub[0] == "then":
                    then_node = sub
                    pos += 1
                    break
                cond_exprs.append(sub)
                pos += 1
            if pos < len(node) and isinstance(node[pos], list) and node[pos][0] == "else":
                else_node = node[pos]
                pos += 1
            if then_node is None or pos != len(node):
                raise WatSyntaxError(f"Malformed folded 'if' expression: {node!r}")

            self._compile_seq(cond_exprs, local_names, label_stack, out)
            out.append(0x04)
            out.append(btype)
            label_stack.append(label)
            self._compile_seq(then_node[1:], local_names, label_stack, out)
            if else_node is not None:
                out.append(0x05)
                self._compile_seq(else_node[1:], local_names, label_stack, out)
            label_stack.pop()
            out.append(0x0B)
            return

        # Standard folded instruction: (op imms... operand_exprs...)
        imm_bytes, next_pos = self._parse_immediates(op, node, 1, local_names, label_stack)
        if next_pos < len(node):
            self._compile_seq(node[next_pos:], local_names, label_stack, out)
        self._emit_instruction(op, imm_bytes, out)

    def _compile_flat(
        self,
        items: list[Any],
        pos: int,
        local_names: dict[str, int],
        label_stack: list[str | None],
        out: bytearray,
    ) -> int:
        op = items[pos]
        pos += 1

        if op in ("block", "loop"):
            label, btype, pos = self._parse_block_sig(items, pos)
            out.append(0x02 if op == "block" else 0x03)
            out.append(btype)
            label_stack.append(label)
            return pos
        if op == "if":
            label, btype, pos = self._parse_block_sig(items, pos)
            out.append(0x04)
            out.append(btype)
            label_stack.append(label)
            return pos
        if op == "else":
            out.append(0x05)
            return pos
        if op == "end":
            if not label_stack:
                raise WatSyntaxError("Unexpected 'end' instruction")
            label_stack.pop()
            out.append(0x0B)
            return pos

        imm_bytes, next_pos = self._parse_immediates(op, items, pos, local_names, label_stack)
        self._emit_instruction(op, imm_bytes, out)
        return next_pos

    def _parse_immediates(
        self,
        op: str,
        items: list[Any],
        pos: int,
        local_names: dict[str, int],
        label_stack: list[str | None],
    ) -> tuple[bytes, int]:
        if op in ("local.get", "local.set", "local.tee"):
            return uleb128(self._resolve_local(items[pos], local_names)), pos + 1
        if op in ("global.get", "global.set"):
            return uleb128(self.resolve_global(items[pos])), pos + 1
        if op == "call":
            return uleb128(self.resolve_func(items[pos])), pos + 1
        if op in ("br", "br_if"):
            return uleb128(self._resolve_label(items[pos], label_stack)), pos + 1
        if op == "i32.const":
            return sleb128(parse_int_literal(items[pos], 32)), pos + 1
        if op == "i64.const":
            return sleb128(parse_int_literal(items[pos], 64)), pos + 1
        if op == "f32.const":
            return struct.pack("<f", parse_float_literal(items[pos])), pos + 1
        if op == "f64.const":
            return struct.pack("<d", parse_float_literal(items[pos])), pos + 1
        if op in MEM_OPCODES:
            _, default_align = MEM_OPCODES[op]
            align_log2, offset, next_pos = parse_memarg(items, pos, default_align)
            return uleb128(align_log2) + uleb128(offset), next_pos
        if op in ("memory.size", "memory.grow"):
            return b"\x00", pos
        return b"", pos

    def _emit_instruction(self, op: str, imm_bytes: bytes, out: bytearray) -> None:
        direct_opcodes = {
            "br": 0x0C,
            "br_if": 0x0D,
            "call": 0x10,
            "local.get": 0x20,
            "local.set": 0x21,
            "local.tee": 0x22,
            "global.get": 0x23,
            "global.set": 0x24,
            "memory.size": 0x3F,
            "memory.grow": 0x40,
            "i32.const": 0x41,
            "i64.const": 0x42,
            "f32.const": 0x43,
            "f64.const": 0x44,
        }
        if op in direct_opcodes:
            out.append(direct_opcodes[op])
            out.extend(imm_bytes)
        elif op in MEM_OPCODES:
            opcode, _ = MEM_OPCODES[op]
            out.append(opcode)
            out.extend(imm_bytes)
        elif op in SIMPLE_OPCODES:
            out.append(SIMPLE_OPCODES[op])
        else:
            raise WatSyntaxError(f"Unsupported WASM instruction '{op}'")


def compile_wat_to_wasm(wat_path: Path, wasm_path: Path) -> bytes:
    source = wat_path.read_text(encoding="utf-8")
    tokens = tokenize_wat(source)
    exprs = parse_sexprs(tokens)
    if len(exprs) != 1:
        raise WatSyntaxError(f"Expected 1 top-level '(module ...)' form, found {len(exprs)}")
    wasm_bytes = ModuleAssembler().assemble(exprs[0])
    wasm_path.parent.mkdir(parents=True, exist_ok=True)
    wasm_path.write_bytes(wasm_bytes)
    return wasm_bytes


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    wat_path = Path(argv[1]) if len(argv) >= 2 else repo_root / "web" / "street_vulkan_core.wat"
    wasm_path = Path(argv[2]) if len(argv) >= 3 else repo_root / "web" / "street_vulkan_core.wasm"

    wasm_bytes = compile_wat_to_wasm(wat_path, wasm_path)
    print(f"[compile_wat_to_wasm] Compiled {wat_path} -> {wasm_path} ({len(wasm_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
