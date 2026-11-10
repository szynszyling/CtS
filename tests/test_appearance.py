import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import DARK, LIGHT, ThemeManager
from circle_to_search.platforms.base import ThemeSource
from circle_to_search.platforms.linux.kde.theme import PlasmaThemeSource

APP = QApplication.instance() or QApplication([])


class PlasmaThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "kdeglobals"

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_window_colors_support_custom_schemes_and_hex_or_rgb(self):
        self.path.write_text(
            "[General]\nColorScheme=CustomName\n[Colors:Window]\nBackgroundNormal=#1d1d1e\n"
        )
        self.assertEqual(PlasmaThemeSource(self.path).is_dark(), True)
        self.path.write_text("[Colors:Window]\nBackgroundNormal=239,240,241\n")
        self.assertEqual(PlasmaThemeSource(self.path).is_dark(), False)
        self.path.write_text("[Colors:Window]\nBackgroundNormal=32,33,36\n")
        self.assertEqual(PlasmaThemeSource(self.path).is_dark(), True)

    def test_named_scheme_resolved_from_xdg_data_not_guessed_from_name(self):
        schemes = self.root / "color-schemes"
        schemes.mkdir()
        (schemes / "MyLightName.colors").write_text("[Colors:Window]\nBackgroundNormal=30,30,30\n")
        self.path.write_text("[General]\nColorScheme=MyLightName\n")
        self.assertEqual(PlasmaThemeSource(self.path, [self.root]).is_dark(), True)

    def test_missing_or_invalid_config_defaults_to_light(self):
        self.assertEqual(PlasmaThemeSource(self.path, []).is_dark(), False)
        for value in (
            "not a config",
            "[Colors:Window]\nBackgroundNormal=999,2,3\n",
            "[Colors:Window]\nBackgroundNormal=invalid\n",
        ):
            self.path.write_text(value)
            self.assertEqual(PlasmaThemeSource(self.path, []).is_dark(), False)


class ThemeManagerTests(unittest.TestCase):
    def setUp(self):
        PlasmaThemeTests.setUp(self)
        self.previous = getattr(APP, "_cts_appearance", None)
        self.palette = APP.palette()
        self.path.write_text("[Colors:Window]\nBackgroundNormal=#202124\n")
        self.settings = QSettings(str(self.root / "appearance.ini"), QSettings.IniFormat)
        self.manager = ThemeManager(
            APP, settings=self.settings, source=PlasmaThemeSource(self.path)
        )

    def tearDown(self):
        self.manager.watcher.blockSignals(True)
        self.manager.debounce.stop()
        APP._cts_appearance = self.previous
        APP.setPalette(self.palette)
        self.manager.deleteLater()
        APP.processEvents()
        PlasmaThemeTests.tearDown(self)

    def test_default_automatic_uses_plasma_and_manual_override_persists(self):
        self.assertEqual(self.manager.mode, "auto")
        self.assertEqual(self.manager.theme, DARK)
        self.manager.set_mode("light")
        self.assertEqual(self.settings.value("theme"), "light")
        self.assertEqual(self.manager.theme, LIGHT)
        self.manager.refresh()
        self.assertEqual(self.manager.theme, LIGHT)
        self.manager.set_mode("auto")
        self.assertEqual(self.manager.theme, DARK)

    def test_atomic_replacement_and_subsequent_changes_follow_plasma(self):
        replacement = self.root / "replacement"
        replacement.write_text("[Colors:Window]\nBackgroundNormal=255,255,255\n")
        replacement.replace(self.path)
        QTest.qWait(350)
        self.assertEqual(self.manager.theme, LIGHT)
        self.path.write_text("[Colors:Window]\nBackgroundNormal=20,20,20\n")
        QTest.qWait(350)
        self.assertEqual(self.manager.theme, DARK)

    def test_cover_signal_precedes_palette_and_effective_change_is_deduplicated(self):
        changes = []
        self.manager.aboutToChange.connect(
            lambda target: changes.append(("cover", self.manager.theme, target))
        )
        self.manager.changed.connect(
            lambda target: changes.append(("ready", self.manager.theme, target))
        )
        self.manager.set_mode("light")
        self.manager.set_mode("light")
        self.assertEqual(changes, [("cover", DARK, LIGHT), ("ready", LIGHT, LIGHT)])
        with self.assertRaises(ValueError):
            self.manager.set_mode("invalid")

    def test_session_override_does_not_replace_saved_preference(self):
        self.manager.set_mode("dark")
        temporary = ThemeManager(
            APP,
            mode="light",
            settings=self.settings,
            source=PlasmaThemeSource(self.path),
            watch=False,
        )
        self.assertEqual(temporary.theme, LIGHT)
        self.assertEqual(self.settings.value("theme"), "dark")
        APP._cts_appearance = self.manager
        temporary.deleteLater()

    def test_native_theme_notifications_need_no_plasma_file(self):
        class NativeThemeSource(ThemeSource):
            dark = False

            def is_dark(self):
                return self.dark

        source = NativeThemeSource()
        manager = ThemeManager(APP, mode="auto", settings=self.settings, source=source)
        self.assertEqual(manager.theme, LIGHT)
        self.assertEqual(manager.watcher.files(), [])
        source.dark = True
        source.changed.emit()
        QTest.qWait(200)
        self.assertEqual(manager.theme, DARK)
        APP._cts_appearance = self.manager
        manager.deleteLater()


if __name__ == "__main__":
    unittest.main()
