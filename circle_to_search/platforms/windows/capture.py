"""Capture each physical monitor separately, preserving mixed-DPI text detail."""

import ctypes
from ctypes import wintypes as w

from PySide6.QtGui import QImage

from ..base import Capture
from .native import checked, libraries


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("monitor", w.RECT),
        ("work", w.RECT),
        ("flags", w.DWORD),
        ("device", w.WCHAR * 32),
    ]


class BitmapHeader(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("width", w.LONG),
        ("height", w.LONG),
        ("planes", w.WORD),
        ("bits", w.WORD),
        ("compression", w.DWORD),
        ("image_size", w.DWORD),
        ("xppm", w.LONG),
        ("yppm", w.LONG),
        ("used", w.DWORD),
        ("important", w.DWORD),
    ]


def monitor_rectangles():
    user, _, _ = libraries()
    rectangles, errors = {}, []
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)

    @callback_type
    def visit(handle, dc, rectangle, parameter):
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if not user.GetMonitorInfoW(handle, ctypes.byref(info)):
            errors.append(ctypes.get_last_error())
            return False
        rect = info.monitor
        rectangles[info.device] = (
            rect.left,
            rect.top,
            rect.right - rect.left,
            rect.bottom - rect.top,
        )
        return True

    checked(user.EnumDisplayMonitors(None, None, visit, 0), "enumerate desktop monitors")
    if errors or not rectangles:
        raise RuntimeError("Windows did not return an accessible desktop monitor.")
    return rectangles


def capture_rect(rectangle):
    user, gdi, _ = libraries()
    x, y, width, height = rectangle
    if width <= 0 or height <= 0:
        raise RuntimeError("The display layout changed. Try capturing again.")
    desktop = checked(user.GetDC(None), "access the desktop")
    memory = bitmap = previous = None
    try:
        memory = checked(gdi.CreateCompatibleDC(desktop), "create a capture context")
        bitmap = checked(
            gdi.CreateCompatibleBitmap(desktop, width, height), "create a capture bitmap"
        )
        previous = checked(gdi.SelectObject(memory, bitmap), "select the capture bitmap")
        checked(
            gdi.BitBlt(memory, 0, 0, width, height, desktop, x, y, 0x40CC0020), "capture the screen"
        )
        gdi.SelectObject(memory, previous)
        previous = None
        header = BitmapHeader()
        header.size, header.width, header.height = ctypes.sizeof(header), width, -height
        header.planes, header.bits = 1, 32
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0)
        if lines != height:
            raise RuntimeError("Windows could not read the entire desktop capture.")
        # GDI's fourth byte is undefined. RGB888 drops it rather than treating
        # it as transparency; the copied QImage owns its pixels after return.
        return QImage(
            buffer.raw, width, height, width * 4, QImage.Format.Format_RGB32
        ).convertToFormat(QImage.Format.Format_RGB888)
    finally:
        if previous:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        user.ReleaseDC(None, desktop)


def capture_desktop(workspace, current_screen):
    # Qt on Windows scales monitor sizes but keeps their physical origins.
    # Friendly display names may be duplicated and need not match DISPLAYn.
    images = {rectangle[:2]: capture_rect(rectangle) for rectangle in monitor_rectangles().values()}
    return Capture(QImage(), workspace, images)
