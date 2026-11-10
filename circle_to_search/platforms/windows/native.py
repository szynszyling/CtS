"""Typed Win32 entry points, with pointer-sized handles on 64-bit Windows."""

import ctypes
from ctypes import wintypes as w
from functools import lru_cache


@lru_cache
def libraries():
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    signatures = [
        (user, "SetProcessDpiAwarenessContext", [w.HANDLE], w.BOOL),
        (user, "GetDC", [w.HWND], w.HDC),
        (user, "ReleaseDC", [w.HWND, w.HDC], ctypes.c_int),
        (user, "GetMonitorInfoW", [w.HANDLE, ctypes.c_void_p], w.BOOL),
        (user, "EnumDisplayMonitors", [w.HDC, ctypes.c_void_p, ctypes.c_void_p, w.LPARAM], w.BOOL),
        (user, "RegisterHotKey", [w.HWND, ctypes.c_int, w.UINT, w.UINT], w.BOOL),
        (user, "UnregisterHotKey", [w.HWND, ctypes.c_int], w.BOOL),
        (user, "SetForegroundWindow", [w.HWND], w.BOOL),
        (user, "GetForegroundWindow", [], w.HWND),
        (gdi, "CreateCompatibleDC", [w.HDC], w.HDC),
        (gdi, "DeleteDC", [w.HDC], w.BOOL),
        (gdi, "CreateCompatibleBitmap", [w.HDC, ctypes.c_int, ctypes.c_int], w.HBITMAP),
        (gdi, "SelectObject", [w.HDC, w.HANDLE], w.HANDLE),
        (gdi, "DeleteObject", [w.HANDLE], w.BOOL),
        (
            gdi,
            "BitBlt",
            [
                w.HDC,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                w.HDC,
                ctypes.c_int,
                ctypes.c_int,
                w.DWORD,
            ],
            w.BOOL,
        ),
        (
            gdi,
            "GetDIBits",
            [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT],
            ctypes.c_int,
        ),
        (dwm, "DwmSetWindowAttribute", [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD], ctypes.c_long),
    ]
    for library, name, arguments, result in signatures:
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    return user, gdi, dwm


def checked(result, operation):
    if not result:
        raise RuntimeError(
            f"Windows could not {operation}: {ctypes.WinError(ctypes.get_last_error())}"
        )
    return result
