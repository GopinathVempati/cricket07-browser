"""Run with python3 tests/check_flush.py (requires a C compiler via CC or cc)."""
import os
from pathlib import Path
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / "host/kernel32.c").read_text()
body = source.split("W(FlushFileBuffers) {", 1)[1].split("\nW(SetEndOfFile)", 1)[0]
errors = source.split("enum { ERROR_FILE_NOT_FOUND", 1)[1].split("};", 1)[0]
harness = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
typedef struct { uint32_t eax, arg; } CPU;
typedef struct { int fd; } WinHandle;
enum { H_FILE = 1 };
static WinHandle file = { 42 };
static int calls, interrupted, failure, last_error;
static WinHandle *handle_get(uint32_t h, int type) {
    assert(type == H_FILE);
    return h == 7 ? &file : 0;
}
static void set_error(int e) { last_error = e; }
static int fsync(int fd) {
    assert(fd == 42);
    ++calls;
    if (interrupted) { interrupted = 0; errno = EINTR; return -1; }
    if (failure) { errno = failure; return -1; }
    return 0;
}
#define ARG(i) (c->arg)
#define RET(n, value) do { c->eax = (value); return; } while (0)
""" + "enum { ERROR_FILE_NOT_FOUND" + errors + "};\nstatic void flush(CPU *c) {" + body + r"""
int main(void) {
    CPU c = { 0, 7 };
    flush(&c); assert(c.eax == 1 && calls == 1);
    interrupted = 1;
    flush(&c); assert(c.eax == 1 && calls == 3);
    failure = EIO;
    flush(&c); assert(c.eax == 0 && last_error == ERROR_WRITE_FAULT);
    failure = ENOSPC;
    flush(&c); assert(c.eax == 0 && last_error == ERROR_DISK_FULL);
    c.arg = 0; calls = 0;
    flush(&c); assert(c.eax == 0 && last_error == ERROR_INVALID_HANDLE && calls == 0);
}
"""
with tempfile.TemporaryDirectory() as tmp:
    cfile = Path(tmp) / "check.c"
    exe = Path(tmp) / ("check.exe" if os.name == "nt" else "check")
    cfile.write_text(harness)
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("FlushFileBuffers checks passed")
