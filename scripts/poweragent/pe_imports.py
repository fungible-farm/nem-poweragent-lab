"""List the DLLs a Windows PE file imports (load-time dependencies), without any third-party package.

usage: python3 pe_imports.py FILE.exe [...]     -> JSON {"file.exe": ["KERNEL32.dll", ...]}
Used by pack.py to write data/imports.json, which the installer's preflight resolves on the target machine.
Delay-load imports are not included; they fail at first use, not at start-up.
"""
import json, os, struct, sys


def imports(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path}: not a PE file")
    nsec, = struct.unpack_from("<H", d, pe + 6)
    opt_size, = struct.unpack_from("<H", d, pe + 20)
    magic, = struct.unpack_from("<H", d, pe + 24)
    data_dir = pe + 24 + (112 if magic == 0x20B else 96)
    imp_rva, = struct.unpack_from("<I", d, data_dir + 8)  # IMAGE_DIRECTORY_ENTRY_IMPORT
    sec_off = pe + 24 + opt_size
    secs = [struct.unpack_from("<8sIIII", d, sec_off + i * 40)[1:] for i in range(nsec)]  # vsize, va, rawsize, rawptr

    def off(rva):
        for vs, va, rs, rp in secs:
            if va <= rva < va + max(vs, rs):
                return rva - va + rp
        raise ValueError(f"{path}: RVA {rva:#x} not in any section")

    names = set()
    if imp_rva:
        o = off(imp_rva)
        while True:
            _, _, _, name_rva, _ = struct.unpack_from("<IIIII", d, o)
            if not name_rva:
                break
            p = off(name_rva)
            names.add(d[p:d.index(b"\0", p)].decode("ascii"))
            o += 20
    # Windows resolves DLL names case-insensitively; keep one spelling per name.
    seen, out = set(), []
    for n in sorted(names, key=str.lower):
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


if __name__ == "__main__":
    print(json.dumps({os.path.basename(p): imports(p) for p in sys.argv[1:]}, indent=1))
