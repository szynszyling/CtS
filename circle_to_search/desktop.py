"""Give the selection surface a Wayland overlay role, not an app-window role."""

import ctypes
import ctypes.util
import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QSurface
from PySide6.QtWidgets import QApplication

_library = None


def configure_overlay(widget):
    if QApplication.platformName() != "wayland":
        return None
    try:
        import shiboken6
        global _library
        if _library is None:
            _library = ctypes.CDLL(ctypes.util.find_library("LayerShellQtInterface") or "libLayerShellQtInterface.so.6")
        # LayerShellQt exposes a QObject with Qt properties. Only its stable
        # Window::get(QWindow*) accessor needs a native call; Qt handles enums,
        # ownership and all subsequent configuration through its meta-object.
        get_window = getattr(_library,"_ZN12LayerShellQt6Window3getEP7QWindow")
        get_window.argtypes = [ctypes.c_void_p]
        get_window.restype = ctypes.c_void_p
        widget.winId()  # create a QWindow, but do not map it
        window=widget.windowHandle()
        if window.surfaceType()==QSurface.SurfaceType.RasterSurface:
            # WebEngine's first rendered widget otherwise replaces this raster
            # QWindow with an OpenGL one and loses the attached layer role.
            # Select the final surface type before assigning the role/mapping.
            window.destroy()
            window.setSurfaceType(QSurface.SurfaceType.OpenGLSurface)
            window.create()
        pointer = get_window(shiboken6.getCppPointer(widget.windowHandle())[0])
        layer = shiboken6.wrapInstance(pointer,QObject)
        for name, value in [("layer",3),("anchors",15),("exclusionZone",-1),
                            ("keyboardInteractivity",2),("scope","utility"),
                            ("screen",widget.screen())]:
            if not layer.setProperty(name,value):
                raise RuntimeError("Could not set LayerShellQt property " + name)
        return layer
    except (OSError,AttributeError,RuntimeError) as exc:
        print("Circle to Search: desktop overlay integration unavailable: " + str(exc),file=sys.stderr)
        return None
