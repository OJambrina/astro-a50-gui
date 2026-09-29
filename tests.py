"""Unit tests for the GUI's pure logic.

Run with:
    .venv/bin/python -m unittest tests.py
"""
import json
import os
import string
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gui
import i18n
import settings
import templates
import themes
from base_info_dialog import format_base_info
from eq_widget import EqTemplatesWidget
from vendor.eh_fifty import DeviceInfo, FirmwareVersion


class BuiltinTemplatesTest(unittest.TestCase):
    BANDS = (1, 2, 3, 4, 5)

    def test_five_builtin_templates(self):
        self.assertEqual(
            set(templates._EQ_TEMPLATES),
            {"A50 MOD KIT", "ASTRO", "MEDIA", "PRO", "STUDIO"},
        )

    def test_template_shape(self):
        for name, tpl in templates._EQ_TEMPLATES.items():
            with self.subTest(name=name):
                self.assertIn("gain", tpl)
                self.assertIn("bands", tpl)
                self.assertEqual(len(tpl["gain"]), 5,
                                 f"{name}: gain must have 5 entries")
                self.assertEqual(set(tpl["bands"]), set(self.BANDS),
                                 f"{name}: bands must be {{1..5}}")
                for g in tpl["gain"]:
                    self.assertGreaterEqual(g, -7)
                    self.assertLessEqual(g, 7)
                # Bands 1 and 5 are highpass/lowpass: bandwidth must be 0.
                for edge in (1, 5):
                    _, bw = tpl["bands"][edge]
                    self.assertEqual(bw, 0,
                                     f"{name}: band {edge} must have bw=0")


class UserTemplatesIOTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "user-templates.json"
        self._patcher = mock.patch.object(templates, "USER_TEMPLATES_FILE", self.path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.tmpdir.cleanup()

    def test_load_when_file_missing(self):
        self.assertEqual(templates._load_user_templates(), {})

    def test_save_then_load_roundtrip(self):
        tpl = {
            "MyMix": {
                "gain": [3, -2, 0, 5, 2],
                "bands": {1: (100, 0), 2: (400, 4096), 3: (1000, 8192),
                          4: (4000, 2048), 5: (8000, 0)},
            },
        }
        templates._save_user_templates(tpl)
        loaded = templates._load_user_templates()
        self.assertEqual(loaded, tpl)

    def test_load_skips_malformed_entries(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "Valid": {"gain": [0]*5, "bands": {str(b): [100*b, 0] for b in (1,2,3,4,5)}},
            "BadShape": {"foo": "bar"},
            "MissingBands": {"gain": [0]*5},
        }))
        loaded = templates._load_user_templates()
        self.assertIn("Valid", loaded)
        self.assertNotIn("BadShape", loaded)
        self.assertNotIn("MissingBands", loaded)

    def test_load_returns_empty_dict_on_invalid_json(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json")
        self.assertEqual(templates._load_user_templates(), {})


class BaseInfoDialogTest(unittest.TestCase):
    def test_format_base_info(self):
        lines = format_base_info(
            DeviceInfo(vendor_id=0x9886, product_id=0x002C),
            FirmwareVersion(major=1, minor=2),
            FirmwareVersion(major=3, minor=4),
            [("0x03", b"\x01\x02"), ("0x83(01)", b"\xaa")],
        )
        joined = "\n".join(lines)
        self.assertIn("9886:002c", joined)
        self.assertIn("1.2", joined)
        self.assertIn("3.4", joined)
        self.assertIn("0x03:", joined)
        self.assertIn("0102", joined)
        self.assertIn("0x83(01):", joined)
        self.assertIn("aa", joined)


class AppVersionTest(unittest.TestCase):
    def test_reads_pyproject_version(self):
        text = (Path(gui.__file__).parent / "pyproject.toml").read_text()
        self.assertIn(f'version = "{gui.app_version()}"', text)

    def test_missing_pyproject_gives_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            gui, "SCRIPT_PATH", Path(tmp) / "gui.py"
        ):
            self.assertEqual(gui.app_version(), "?")


def setUpModule():
    # i18n.LANG is detected at import, from the developer's own settings.json
    # and locale: run the tests in English whatever those are.
    patcher = mock.patch.object(i18n, "LANG", "en")
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def _isolated_settings(tmp: str):
    """Point settings.json at a temp dir, so the user's real preferences never leak in."""
    return mock.patch.object(settings, "SETTINGS_PATH", Path(tmp) / "settings.json")


class I18nTest(unittest.TestCase):
    def test_known_key_in_active_language(self):
        # `t` proxies through the module-level LANG; force FR for the test.
        with mock.patch.object(i18n, "LANG", "fr"):
            self.assertEqual(i18n.t("err_title"), "Erreur")
        with mock.patch.object(i18n, "LANG", "en"):
            self.assertEqual(i18n.t("err_title"), "Error")

    def test_unknown_key_returns_key(self):
        with mock.patch.object(i18n, "LANG", "fr"):
            self.assertEqual(i18n.t("__nonexistent__"), "__nonexistent__")

    def test_kwargs_formatting(self):
        with mock.patch.object(i18n, "LANG", "fr"):
            self.assertEqual(
                i18n.t("msg_eq_set", name="MEDIA"),
                "Preset EQ → MEDIA",
            )

    def test_fr_falls_back_to_en_for_missing_translation(self):
        # Patch FR table so a key only exists in EN.
        with mock.patch.dict(i18n.TRANSLATIONS["fr"], clear=False) as _:
            i18n.TRANSLATIONS["fr"].pop("err_title", None)
            with mock.patch.object(i18n, "LANG", "fr"):
                self.assertEqual(i18n.t("err_title"), "Error")
        # Restore — mock.patch.dict resets dict; safe.

    def test_every_language_has_the_same_keys_as_en(self):
        reference = set(i18n.TRANSLATIONS["en"])
        for lang, strings in i18n.TRANSLATIONS.items():
            with self.subTest(lang=lang):
                self.assertEqual(set(strings), reference)

    def test_placeholders_match_en(self):
        # A misspelled or extra placeholder raises KeyError at runtime; a missing
        # one silently drops the value from the message.
        def fields(text: str) -> set[str]:
            return {f for _, f, _, _ in string.Formatter().parse(text) if f}

        for lang, strings in i18n.TRANSLATIONS.items():
            for key, text in strings.items():
                with self.subTest(lang=lang, key=key):
                    self.assertEqual(fields(text), fields(i18n.TRANSLATIONS["en"][key]))

    def test_spanish_is_detected(self):
        with mock.patch.object(i18n, "LANG", "es"):
            self.assertEqual(i18n.t("btn_refresh"), "Actualizar")
            self.assertEqual(i18n.t("gate_tournament"), "TORNEO")
        with mock.patch.dict(os.environ, {"A50_LANG": "es"}):
            self.assertEqual(i18n._detect_lang(), "es")
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.dict(os.environ, {"A50_LANG": ""}),
            mock.patch.object(i18n, "QLocale") as qlocale,
        ):
            qlocale.system.return_value.name.return_value = "es_ES"
            self.assertEqual(i18n._detect_lang(), "es")
            qlocale.system.return_value.name.return_value = "de_DE"
            self.assertEqual(i18n._detect_lang(), "en")  # unsupported: English

    def test_gate_labels_fall_back_to_the_mode_name(self):
        with mock.patch.object(i18n, "LANG", "es"):
            self.assertEqual(i18n.gate_label("HOME"), "CASA")
            self.assertEqual(i18n.gate_label("NEW_MODE"), "NEW_MODE")


class EqWidgetHasPendingTest(unittest.TestCase):
    """Tests for EqTemplatesWidget.has_pending() — the dirty signal used by
    the main window's sync button.

    Uses ``__new__`` to bypass the Qt-based __init__; we only set the
    attributes the method reads.
    """

    def _make(
        self,
        slot_pending: dict[int, set[int]] | None = None,
        selected_slot: int = 1,
        device_active: int | None = 1,
    ):
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._slot_pending = slot_pending or {1: set(), 2: set(), 3: set()}
        widget._selected_slot = selected_slot
        widget._device_active_eq = device_active
        return widget

    def test_clean_state(self):
        widget = self._make()
        self.assertFalse(widget.has_pending())

    def test_pending_band(self):
        widget = self._make(slot_pending={1: {3}, 2: set(), 3: set()})
        self.assertTrue(widget.has_pending())

    def test_radio_differs_from_device(self):
        widget = self._make(selected_slot=2, device_active=1)
        self.assertTrue(widget.has_pending())

    def test_radio_matches_device(self):
        widget = self._make(selected_slot=2, device_active=2)
        self.assertFalse(widget.has_pending())

    def test_no_device_active_yet(self):
        # Before reload, _device_active_eq is None and changing the radio
        # should not flag dirty (we don't know the device state).
        widget = self._make(selected_slot=2, device_active=None)
        self.assertFalse(widget.has_pending())


class EqWidgetMatchTemplateTest(unittest.TestCase):
    def _make(self, user_templates: dict | None = None):
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._user_templates = user_templates or {}
        return widget

    def test_match_builtin(self):
        widget = self._make()
        media = templates._EQ_TEMPLATES["MEDIA"]
        data = {"name": "MEDIA", "gain": media["gain"], "bands": media["bands"]}
        self.assertEqual(widget._match_template(data), "MEDIA")

    def test_no_match_on_gain_diff(self):
        widget = self._make()
        media = templates._EQ_TEMPLATES["MEDIA"]
        gain = list(media["gain"])
        gain[2] = gain[2] + 1
        data = {"name": "MEDIA", "gain": gain, "bands": media["bands"]}
        self.assertIsNone(widget._match_template(data))

    def test_match_user_template(self):
        user_tpl = {
            "gain": [1, 2, 3, 4, 5],
            "bands": {1: (100, 0), 2: (400, 4096), 3: (1000, 8192),
                      4: (4000, 2048), 5: (8000, 0)},
        }
        widget = self._make(user_templates={"MyMix": user_tpl})
        data = {"name": "MyMix", "gain": user_tpl["gain"], "bands": user_tpl["bands"]}
        self.assertEqual(widget._match_template(data), "MyMix")


class _MockCombo:
    """Stands in for QComboBox in tests that bypass Qt.

    Supports the subset of the QComboBox API that the EQ widget calls:
    ``currentData``, ``findData``, ``itemData``, ``setCurrentIndex``,
    ``blockSignals``. Optionally fires a "signal handler" callback when
    ``setCurrentIndex`` is invoked while signals are unblocked — used by
    the reload regression test to detect that signals are properly
    suppressed around `combo.setCurrentIndex()` during reload.
    """
    def __init__(self, items=None, current_data=None, signal_handler=None):
        # items: list of (display_name, data); kept in insertion order
        if items is None and current_data is not None:
            items = [(current_data, current_data)]
        self._items = list(items) if items else []
        self._current = 0
        if current_data is not None:
            for i, (_, d) in enumerate(self._items):
                if d == current_data:
                    self._current = i
                    break
        self._signals_blocked = False
        self._signal_handler = signal_handler
        self.set_current_index_log = []  # (idx, was_blocked)

    def currentData(self):
        if not self._items:
            return None
        return self._items[self._current][1]

    def findData(self, data):
        for i, (_, d) in enumerate(self._items):
            if d == data:
                return i
        return -1

    def itemData(self, idx):
        if 0 <= idx < len(self._items):
            return self._items[idx][1]
        return None

    def itemText(self, idx):
        if 0 <= idx < len(self._items):
            return self._items[idx][0]
        return None

    def insertItem(self, idx, _icon, text, data):
        self._items.insert(idx, (text, data))
        if self._items and idx <= self._current and len(self._items) > 1:
            self._current += 1

    def removeItem(self, idx):
        if 0 <= idx < len(self._items):
            del self._items[idx]
            if idx < self._current or self._current >= len(self._items):
                self._current = max(self._current - 1, 0)

    def setCurrentIndex(self, idx):
        if 0 <= idx < len(self._items):
            self._current = idx
        self.set_current_index_log.append((idx, self._signals_blocked))
        if not self._signals_blocked and self._signal_handler is not None:
            self._signal_handler()

    def blockSignals(self, block):
        prev = self._signals_blocked
        self._signals_blocked = block
        return prev


class _MockRadio:
    """Stands in for QRadioButton — only setChecked is exercised."""
    def __init__(self):
        self.checked = False

    def setChecked(self, value):
        self.checked = value


# A preset set up in Astro Command Center, as the base reports it: no builtin
# or user template matches it (issue #11).
_ARCTURUS_ON_BASE = {
    "name": "ARCTURUS",
    "gain": [5, 6, 4, 6, 5],
    "bands": {1: (100, 0), 2: (1775, 9011), 3: (4664, 8192), 4: (8210, 9011), 5: (11125, 0)},
}


class EqWidgetPushPendingTest(unittest.TestCase):
    """Tests for EqTemplatesWidget.push_pending_to_device() — the sync
    flow that writes the visible state to the headset and (for user
    presets) overwrites their local definition.

    Bypasses Qt via ``__new__``; only the attributes/methods the function
    reads are populated. ``_save_user_templates`` is patched at the
    module level to avoid touching disk.
    """

    def _make(
        self,
        *,
        user_templates: dict | None = None,
        device_templates: dict[int, str | None] | None = None,
        slot_bands: dict[int, list[tuple[int, int]]] | None = None,
        slot_modified: dict[int, set[int]] | None = None,
        slot_pending: dict[int, set[int]] | None = None,
        combos: dict[int, str | None] | None = None,
        selected_slot: int = 1,
        device_active: int | None = 1,
    ):
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._user_templates = user_templates or {}
        widget._device_templates = device_templates or {1: None, 2: None, 3: None}
        widget._slot_bands = slot_bands or {1: [], 2: [], 3: []}
        widget._slot_modified = slot_modified or {1: set(), 2: set(), 3: set()}
        widget._slot_pending = slot_pending or {1: set(), 2: set(), 3: set()}
        widget._selected_slot = selected_slot
        widget._device_active_eq = device_active
        widget._last_dirty = False
        widget._refresh_meter = lambda: None
        widget._update_apply_enabled = lambda: None
        widget._emit_dirty_if_changed = lambda: None
        widget.device = mock.MagicMock()
        widget.template_combos = {
            slot: _MockCombo(current_data=(combos or {}).get(slot))
            for slot in (1, 2, 3)
        }
        return widget

    @staticmethod
    def _bands_from_template(name: str) -> list[tuple[int, int]]:
        tpl = templates._EQ_TEMPLATES[name]
        return [(tpl["bands"][b][0], tpl["gain"][b - 1]) for b in range(1, 6)]

    def test_no_pending_skips_all_slots(self):
        widget = self._make(combos={1: "MEDIA", 2: "PRO", 3: "ASTRO"})
        with mock.patch("eq_widget._save_user_templates") as save:
            widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_not_called()
        widget.device.set_eq_preset_gain.assert_not_called()
        widget.device.set_eq_preset_freq_and_bw.assert_not_called()
        widget.device.set_active_eq_preset.assert_not_called()
        save.assert_not_called()

    def test_active_slot_change_pushes_only_active(self):
        widget = self._make(
            combos={1: "MEDIA", 2: "PRO", 3: "ASTRO"},
            selected_slot=2, device_active=1,
        )
        widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_not_called()
        widget.device.set_active_eq_preset.assert_called_once_with(2)
        self.assertEqual(widget._device_active_eq, 2)

    def test_modified_builtin_pushes_as_is_without_local_save(self):
        bands = self._bands_from_template("MEDIA")
        bands[2] = (bands[2][0], 5)  # band 3 gain bumped
        widget = self._make(
            combos={1: "MEDIA", 2: None, 3: None},
            slot_bands={1: bands, 2: [], 3: []},
            slot_modified={1: {3}, 2: set(), 3: set()},
            slot_pending={1: {3}, 2: set(), 3: set()},
            device_templates={1: "MEDIA", 2: None, 3: None},
        )
        with mock.patch("eq_widget._save_user_templates") as save:
            widget.push_pending_to_device()
        # Builtin library untouched, no disk write.
        self.assertEqual(widget._user_templates, {})
        save.assert_not_called()
        # Device received the modified bands under the builtin's name.
        widget.device.set_eq_preset_name.assert_called_once_with(1, "MEDIA")
        expected_gain = [g for (_f, g) in bands]
        widget.device.set_eq_preset_gain.assert_called_once_with(1, expected_gain)
        self.assertEqual(widget.device.set_eq_preset_freq_and_bw.call_count, 5)
        # Slot no longer "matches" any template → off-template orange stays.
        self.assertIsNone(widget._device_templates[1])
        self.assertEqual(widget._slot_modified[1], {3})
        self.assertEqual(widget._slot_pending[1], set())

    def test_modified_user_preset_overwrites_local_and_pushes(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        user_tpl = {"gain": list(media["gain"]),
                    "bands": dict(media["bands"])}
        bands = [(media["bands"][b][0], media["gain"][b - 1]) for b in range(1, 6)]
        bands[2] = (bands[2][0], 4)  # user edits band 3
        widget = self._make(
            user_templates={"MyMix": user_tpl},
            combos={1: "MyMix", 2: None, 3: None},
            slot_bands={1: bands, 2: [], 3: []},
            slot_modified={1: {3}, 2: set(), 3: set()},
            slot_pending={1: {3}, 2: set(), 3: set()},
            device_templates={1: "MyMix", 2: None, 3: None},
        )
        with mock.patch("eq_widget._save_user_templates") as save:
            widget.push_pending_to_device()
        # User preset overwritten with the new band values, persisted once.
        self.assertEqual(widget._user_templates["MyMix"]["gain"][2], 4)
        save.assert_called_once_with(widget._user_templates)
        # Device received the user preset's new state.
        widget.device.set_eq_preset_name.assert_called_once_with(1, "MyMix")
        # Slot now matches the just-saved user preset → no orange, no pending.
        self.assertEqual(widget._device_templates[1], "MyMix")
        self.assertEqual(widget._slot_modified[1], set())
        self.assertEqual(widget._slot_pending[1], set())

    def test_combo_changed_to_other_template_pushes_template_values(self):
        # Simulates the state right after _on_template_combo_changed sets the
        # slot to PRO: _slot_bands holds PRO values, _slot_pending is full,
        # _slot_modified is empty.
        widget = self._make(
            combos={1: "PRO", 2: None, 3: None},
            slot_bands={1: self._bands_from_template("PRO"), 2: [], 3: []},
            slot_modified={1: set(), 2: set(), 3: set()},
            slot_pending={1: {1, 2, 3, 4, 5}, 2: set(), 3: set()},
            device_templates={1: "MEDIA", 2: None, 3: None},
        )
        with mock.patch("eq_widget._save_user_templates"):
            widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_called_once_with(1, "PRO")
        pro = templates._EQ_TEMPLATES["PRO"]
        widget.device.set_eq_preset_gain.assert_called_once_with(1, list(pro["gain"]))
        # Slot now matches PRO cleanly.
        self.assertEqual(widget._device_templates[1], "PRO")
        self.assertEqual(widget._slot_pending[1], set())

    def test_single_save_for_multiple_user_preset_slots(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        user_tpl = {"gain": list(media["gain"]),
                    "bands": dict(media["bands"])}
        bands1 = [(media["bands"][b][0], media["gain"][b - 1]) for b in range(1, 6)]
        bands1[2] = (bands1[2][0], 3)
        bands2 = [(media["bands"][b][0], media["gain"][b - 1]) for b in range(1, 6)]
        bands2[1] = (bands2[1][0], -2)
        widget = self._make(
            user_templates={"Mix1": dict(user_tpl), "Mix2": dict(user_tpl)},
            combos={1: "Mix1", 2: "Mix2", 3: None},
            slot_bands={1: bands1, 2: bands2, 3: []},
            slot_modified={1: {3}, 2: {2}, 3: set()},
            slot_pending={1: {3}, 2: {2}, 3: set()},
            device_templates={1: "Mix1", 2: "Mix2", 3: None},
        )
        with mock.patch("eq_widget._save_user_templates") as save:
            widget.push_pending_to_device()
        # Both user presets updated, but a single disk write.
        self.assertEqual(widget._user_templates["Mix1"]["gain"][2], 3)
        self.assertEqual(widget._user_templates["Mix2"]["gain"][1], -2)
        save.assert_called_once()

    def test_empty_slot_bands_skipped_even_if_pending(self):
        # Defensive: if a slot somehow has pending but no bands data
        # (device read failure during reload), don't crash and don't push.
        widget = self._make(
            combos={1: "MEDIA", 2: None, 3: None},
            slot_pending={1: {1}, 2: set(), 3: set()},
            slot_bands={1: [], 2: [], 3: []},
        )
        with mock.patch("eq_widget._save_user_templates"):
            widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_not_called()

    def test_unknown_device_preset_keeps_its_name_and_bandwidths(self):
        # Issue #11: syncing an edited "<name> (on the base)" slot keeps the
        # device's own name and bandwidths and leaves the library alone.
        widget = self._make(
            user_templates={"MINE": dict(templates._EQ_TEMPLATES["PRO"])},
            combos={1: EqTemplatesWidget.ON_DEVICE},
            slot_bands={1: [(100, 5), (1775, 7), (4664, 4), (8210, 6), (11125, 5)], 2: [], 3: []},
            slot_pending={1: {2}, 2: set(), 3: set()},
        )
        widget._slot_device[1] = dict(_ARCTURUS_ON_BASE)
        with mock.patch("eq_widget._save_user_templates") as save:
            widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_called_once_with(1, "ARCTURUS")
        widget.device.set_eq_preset_gain.assert_called_once_with(1, [5, 7, 4, 6, 5])
        widget.device.set_eq_preset_freq_and_bw.assert_any_call(1, 2, 1775, 9011)
        widget.device.set_eq_preset_freq_and_bw.assert_any_call(1, 3, 4664, 8192)
        save.assert_not_called()
        self.assertEqual(widget._slot_device[1]["gain"], [5, 7, 4, 6, 5])


class EqWidgetReloadUnderLockTest(unittest.TestCase):
    """Regression tests for ``reload_under_lock``.

    Key invariant: when reloading, the combo's ``setCurrentIndex`` must
    happen with signals blocked, otherwise ``_on_template_combo_changed``
    fires, overwrites ``_slot_bands`` with template values and populates
    ``_slot_pending`` with all 5 bands. That populates ``_last_dirty=True``
    during the final ``_emit_dirty_if_changed()`` — but the gui ignores
    that emission (still inside ``reload_all``'s ``_loading=True``). The
    EQ widget and the gui then desync, and any subsequent band edit
    short-circuits inside ``_emit_dirty_if_changed`` (``_last_dirty``
    already True → no signal), so the "Synchronisé" button never flips
    to orange.

    The mock combo here invokes its attached "signal handler" when
    ``setCurrentIndex`` is called while signals are unblocked, so if the
    fix is regressed the test fails loudly.
    """

    def _make_widget(self, device_data: dict[int, dict | None],
                     *, user_templates: dict | None = None):
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._user_templates = user_templates or {}
        widget._device_templates = {1: None, 2: None, 3: None}
        widget._slot_bands = {1: [], 2: [], 3: []}
        widget._slot_modified = {1: set(), 2: set(), 3: set()}
        widget._slot_pending = {1: set(), 2: set(), 3: set()}
        widget._selected_slot = 1
        widget._device_active_eq = None
        widget._last_dirty = False
        widget._loading = False
        widget._refresh_meter = lambda: None
        widget._update_apply_enabled = lambda: None
        widget._emit_dirty_if_changed = lambda: None
        widget.device = mock.MagicMock()

        def get_name(slot):
            return device_data[slot]["name"]

        def get_gain(slot):
            obj = mock.MagicMock()
            obj.gain = device_data[slot]["gain"]
            return obj

        def get_fb(slot, band):
            obj = mock.MagicMock()
            freq, bw = device_data[slot]["bands"][band]
            obj.center_freq = freq
            obj.bandwidth = bw
            return obj

        widget.device.get_eq_preset_name.side_effect = get_name
        widget.device.get_eq_preset_gain.side_effect = get_gain
        widget.device.get_eq_preset_freq_and_bw.side_effect = get_fb

        all_names = sorted(
            list(templates._EQ_TEMPLATES) + list(widget._user_templates),
            key=str.casefold,
        )
        items = [(n, n) for n in all_names]
        widget.template_combos = {}
        for slot in (1, 2, 3):
            combo = _MockCombo(items=items)
            combo._signal_handler = (
                lambda s=slot, w=widget: w._on_template_combo_changed(s)
            )
            widget.template_combos[slot] = combo
        widget.template_radios = {slot: _MockRadio() for slot in (1, 2, 3)}
        return widget

    def test_modified_builtin_reload_leaves_pending_empty(self):
        # Regression: previously _slot_pending[1] ended up as {1,2,3,4,5}.
        media = templates._EQ_TEMPLATES["MEDIA"]
        pro = templates._EQ_TEMPLATES["PRO"]
        astro = templates._EQ_TEMPLATES["ASTRO"]
        modified_gain = list(media["gain"])
        modified_gain[2] = max(-7, min(7, modified_gain[2] + 3))
        device_data = {
            1: {"name": "MEDIA", "gain": modified_gain,
                "bands": dict(media["bands"])},
            2: {"name": "PRO", "gain": list(pro["gain"]),
                "bands": dict(pro["bands"])},
            3: {"name": "ASTRO", "gain": list(astro["gain"]),
                "bands": dict(astro["bands"])},
        }
        widget = self._make_widget(device_data)
        widget.reload_under_lock(active_eq_preset=1)
        self.assertEqual(widget._slot_pending[1], set(),
                         "modified builtin must not populate _slot_pending")
        # Device values preserved (combo signal didn't overwrite them).
        self.assertEqual(widget._slot_bands[1][2][1], modified_gain[2])
        # Off-template band flagged so the meter renders it orange.
        self.assertEqual(widget._slot_modified[1], {3})
        self.assertIsNone(widget._device_templates[1])
        # has_pending mirrors the GUI's expected clean state.
        self.assertFalse(widget.has_pending())

    def test_reload_blocks_combo_signals_around_set_current_index(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        device_data = {
            s: {"name": "MEDIA", "gain": list(media["gain"]),
                "bands": dict(media["bands"])}
            for s in (1, 2, 3)
        }
        widget = self._make_widget(device_data)
        widget.reload_under_lock(active_eq_preset=1)
        for slot, combo in widget.template_combos.items():
            self.assertTrue(combo.set_current_index_log,
                            f"slot {slot}: setCurrentIndex never called")
            for idx, was_blocked in combo.set_current_index_log:
                self.assertTrue(
                    was_blocked,
                    f"slot {slot}: setCurrentIndex({idx}) fired with "
                    "signals unblocked — _on_template_combo_changed would "
                    "have desynced state during reload",
                )

    def test_clean_builtin_reload_matches_template_no_modified_flag(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        device_data = {
            s: {"name": "MEDIA", "gain": list(media["gain"]),
                "bands": dict(media["bands"])}
            for s in (1, 2, 3)
        }
        widget = self._make_widget(device_data)
        widget.reload_under_lock(active_eq_preset=2)
        for slot in (1, 2, 3):
            self.assertEqual(widget._slot_pending[slot], set())
            self.assertEqual(widget._slot_modified[slot], set())
            self.assertEqual(widget._device_templates[slot], "MEDIA")
        self.assertEqual(widget._device_active_eq, 2)
        self.assertEqual(widget._selected_slot, 2)
        self.assertFalse(widget.has_pending())

    def test_unknown_device_preset_shows_its_own_name(self):
        # Issue #11: the slot shows "<name> (on the base)", not the first
        # template, and its bands aren't flagged against an unrelated one.
        media = templates._EQ_TEMPLATES["MEDIA"]
        device_data = {
            1: dict(_ARCTURUS_ON_BASE),
            2: {"name": "MEDIA", "gain": list(media["gain"]), "bands": dict(media["bands"])},
            3: dict(_ARCTURUS_ON_BASE, name=""),
        }
        widget = self._make_widget(device_data)
        widget.reload_under_lock(active_eq_preset=1)
        combo = widget.template_combos[1]
        self.assertEqual(combo.currentData(), EqTemplatesWidget.ON_DEVICE)
        self.assertEqual(combo.itemText(0), "ARCTURUS (on the base)")
        self.assertEqual(widget._slot_modified[1], set())
        self.assertEqual(widget._slot_pending[1], set())
        # A matched slot gets no extra entry; a nameless one is labelled by slot.
        self.assertEqual(widget.template_combos[2].findData(EqTemplatesWidget.ON_DEVICE), -1)
        self.assertEqual(widget.template_combos[3].itemText(0), "Preset 3 (on the base)")

    def test_device_entry_restores_the_base_values(self):
        widget = self._make_widget({s: dict(_ARCTURUS_ON_BASE) for s in (1, 2, 3)})
        widget.reload_under_lock(active_eq_preset=1)
        combo = widget.template_combos[1]
        original = list(widget._slot_bands[1])
        combo.setCurrentIndex(combo.findData("MEDIA"))
        self.assertEqual(widget._slot_pending[1], {1, 2, 3, 4, 5})
        combo.setCurrentIndex(combo.findData(EqTemplatesWidget.ON_DEVICE))
        self.assertEqual(widget._slot_bands[1], original)
        self.assertEqual(widget._slot_pending[1], set())
        # Editing a band flags it against the base's own values; undoing it clears that.
        widget._on_band_modified(2, 7)
        self.assertIn(2, widget._slot_modified[1])
        widget._on_band_modified(2, 6)
        self.assertNotIn(2, widget._slot_modified[1])


class EqWidgetHandlersTest(unittest.TestCase):
    """Unit tests for ``_on_band_modified`` and ``_on_template_combo_changed``
    in isolation — to lock down the per-event state transitions used by the
    dirty signal."""

    def _make(self, *, combo_data: str | None = "MEDIA",
              device_template: str | None = "MEDIA",
              selected_slot: int = 1,
              user_templates: dict | None = None):
        media = templates._EQ_TEMPLATES["MEDIA"]
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._user_templates = user_templates or {}
        widget._device_templates = {1: device_template, 2: None, 3: None}
        widget._slot_bands = {
            1: [(media["bands"][b][0], media["gain"][b - 1])
                for b in range(1, 6)],
            2: [],
            3: [],
        }
        widget._slot_modified = {1: set(), 2: set(), 3: set()}
        widget._slot_pending = {1: set(), 2: set(), 3: set()}
        widget._selected_slot = selected_slot
        widget._device_active_eq = selected_slot
        widget._last_dirty = False
        widget._loading = False
        widget._refresh_meter = lambda: None
        widget._update_apply_enabled = lambda: None
        widget._emit_dirty_if_changed = lambda: None
        widget.device = mock.MagicMock()
        widget.template_combos = {
            1: _MockCombo(current_data=combo_data),
            2: _MockCombo(current_data=None),
            3: _MockCombo(current_data=None),
        }
        return widget

    def test_band_modified_off_template_marks_modified_and_pending(self):
        widget = self._make()
        widget._on_band_modified(3, 5)
        media = templates._EQ_TEMPLATES["MEDIA"]
        self.assertEqual(widget._slot_bands[1][2][1], 5)
        self.assertEqual(widget._slot_bands[1][2][0], media["bands"][3][0])
        self.assertIn(3, widget._slot_modified[1])
        self.assertIn(3, widget._slot_pending[1])
        self.assertTrue(widget.has_pending())

    def test_band_modified_back_to_template_clears_modified_keeps_pending(self):
        widget = self._make()
        widget._slot_modified[1] = {3}
        widget._slot_pending[1] = {3}
        media = templates._EQ_TEMPLATES["MEDIA"]
        # Drag it back to the template's gain for band 3.
        widget._on_band_modified(3, media["gain"][2])
        self.assertNotIn(3, widget._slot_modified[1])
        # Still pending (we touched the band — needs a sync).
        self.assertIn(3, widget._slot_pending[1])

    def test_band_modified_no_bands_returns_silently(self):
        widget = self._make()
        widget._slot_bands[1] = []
        widget._on_band_modified(3, 5)
        self.assertEqual(widget._slot_pending[1], set())
        self.assertEqual(widget._slot_modified[1], set())

    def test_band_modified_skipped_while_loading(self):
        widget = self._make()
        widget._loading = True
        widget._on_band_modified(3, 5)
        self.assertEqual(widget._slot_pending[1], set())

    def test_combo_change_to_other_template_pulls_template_values_and_pendings_all(self):
        widget = self._make(combo_data="PRO", device_template="MEDIA")
        widget._slot_modified[1] = {2}  # stale orange from previous template
        widget._on_template_combo_changed(1)
        pro = templates._EQ_TEMPLATES["PRO"]
        expected = [(pro["bands"][b][0], pro["gain"][b - 1])
                    for b in range(1, 6)]
        self.assertEqual(widget._slot_bands[1], expected)
        self.assertEqual(widget._slot_pending[1], {1, 2, 3, 4, 5})
        self.assertEqual(widget._slot_modified[1], set())
        self.assertTrue(widget.has_pending())

    def test_combo_change_back_to_device_template_clears_pending(self):
        widget = self._make(combo_data="MEDIA", device_template="MEDIA")
        widget._slot_pending[1] = {1, 2, 3, 4, 5}  # was pending from a prior change
        widget._on_template_combo_changed(1)
        self.assertEqual(widget._slot_pending[1], set())
        self.assertEqual(widget._slot_modified[1], set())


class EqWidgetPersistAndPushTest(unittest.TestCase):
    """Tests for ``_persist_and_push`` — the Save / Create-preset flow."""

    def _make(self, *, user_templates: dict | None = None,
              combo_data: str = "MEDIA"):
        import threading as _threading
        media = templates._EQ_TEMPLATES["MEDIA"]
        widget = EqTemplatesWidget.__new__(EqTemplatesWidget)
        widget._slot_device = {1: None, 2: None, 3: None}
        widget._user_templates = dict(user_templates or {})
        widget._device_templates = {1: combo_data, 2: None, 3: None}
        widget._slot_bands = {
            1: [(media["bands"][b][0], media["gain"][b - 1])
                for b in range(1, 6)],
            2: [],
            3: [],
        }
        widget._slot_modified = {1: {3}, 2: set(), 3: set()}
        widget._slot_pending = {1: {3}, 2: set(), 3: set()}
        widget._selected_slot = 1
        widget._device_active_eq = 1
        widget._last_dirty = True
        widget._loading = False
        widget._device_lock = _threading.RLock()
        widget._refresh_combos = lambda **kw: None
        widget.reload_under_lock = lambda *_a, **_k: None
        widget._refresh_meter = lambda: None
        widget._update_apply_enabled = lambda: None
        widget._emit_dirty_if_changed = lambda: None
        widget.device = mock.MagicMock()
        widget.template_combos = {
            1: _MockCombo(current_data=combo_data),
            2: _MockCombo(current_data=None),
            3: _MockCombo(current_data=None),
        }
        # Bump band 3 so there's something to save.
        widget._slot_bands[1][2] = (widget._slot_bands[1][2][0], 4)
        return widget

    def test_create_new_user_preset_saves_pushes_and_clears_pending(self):
        widget = self._make()
        btn = mock.MagicMock()
        with mock.patch("eq_widget.QApplication"), \
             mock.patch("eq_widget._save_user_templates") as save:
            widget._persist_and_push(
                1, "NewMix", is_new=True, btn=btn,
                busy_key="btn_apply_busy", idle_key="btn_apply",
            )
        # User templates library updated and persisted exactly once.
        self.assertIn("NewMix", widget._user_templates)
        self.assertEqual(widget._user_templates["NewMix"]["gain"][2], 4)
        save.assert_called_once_with(widget._user_templates)
        # Device received name + gain + 5 bands + save_values.
        widget.device.set_eq_preset_name.assert_called_once_with(1, "NewMix")
        widget.device.set_eq_preset_gain.assert_called_once()
        self.assertEqual(widget.device.set_eq_preset_freq_and_bw.call_count, 5)
        widget.device.save_values.assert_called_once()
        # State reset for that slot.
        self.assertEqual(widget._device_templates[1], "NewMix")
        self.assertEqual(widget._slot_pending[1], set())

    def test_update_existing_user_preset_overwrites_in_place(self):
        existing = {"gain": [0, 0, 0, 0, 0],
                    "bands": dict(templates._EQ_TEMPLATES["MEDIA"]["bands"])}
        widget = self._make(user_templates={"MyMix": existing},
                            combo_data="MyMix")
        btn = mock.MagicMock()
        with mock.patch("eq_widget.QApplication"), \
             mock.patch("eq_widget._save_user_templates") as save:
            widget._persist_and_push(
                1, "MyMix", is_new=False, btn=btn,
                busy_key="btn_save_eq_busy", idle_key="btn_save_eq",
            )
        self.assertEqual(widget._user_templates["MyMix"]["gain"][2], 4)
        save.assert_called_once()
        widget.device.set_eq_preset_name.assert_called_once_with(1, "MyMix")
        widget.device.save_values.assert_called_once()
        self.assertEqual(widget._device_templates[1], "MyMix")

    def test_persist_and_push_uses_prev_template_bandwidths(self):
        widget = self._make(combo_data="PRO")
        btn = mock.MagicMock()
        with mock.patch("eq_widget.QApplication"), \
             mock.patch("eq_widget._save_user_templates"):
            widget._persist_and_push(
                1, "FromPRO", is_new=True, btn=btn,
                busy_key="btn_apply_busy", idle_key="btn_apply",
            )
        pro = templates._EQ_TEMPLATES["PRO"]
        saved_bands = widget._user_templates["FromPRO"]["bands"]
        # Bands 1 and 5 are shelf filters: bandwidth always 0.
        self.assertEqual(saved_bands[1][1], 0)
        self.assertEqual(saved_bands[5][1], 0)
        # Bands 2-4 inherit PRO's bandwidths.
        for b in (2, 3, 4):
            self.assertEqual(saved_bands[b][1], pro["bands"][b][1])


class SettingsTest(unittest.TestCase):
    def test_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp, _isolated_settings(tmp):
            self.assertEqual(settings.get("theme", "auto"), "auto")
            settings.put("theme", "dark")
            self.assertEqual(settings.get("theme"), "dark")
            settings.SETTINGS_PATH.write_text("{not json")
            self.assertEqual(settings.load(), {})

    def test_wrong_types_fall_back_to_the_default(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.dict(os.environ, {"A50_LANG": ""}),
            mock.patch.object(i18n, "QLocale") as qlocale,
        ):
            settings.SETTINGS_PATH.write_text('{"language": ["es"], "theme": 3}')
            self.assertEqual(settings.get("language", "auto"), "auto")
            self.assertEqual(settings.get("theme", "auto"), "auto")
            qlocale.system.return_value.name.return_value = "fr_FR"
            self.assertEqual(i18n._detect_lang(), "fr")  # no TypeError at startup

    def test_a50_lang_accepts_a_region(self):
        for value in ("es", "es_ES", "es-ES", "ES_es"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"A50_LANG": value}):
                self.assertEqual(i18n._detect_lang(), "es")

    def test_put_never_leaves_a_truncated_file(self):
        with tempfile.TemporaryDirectory() as tmp, _isolated_settings(tmp):
            settings.put("theme", "dark")
            with (
                mock.patch.object(settings.os, "replace", side_effect=OSError("disk full")),
                self.assertRaises(OSError),
            ):
                settings.put("language", "es")
            self.assertEqual(settings.load(), {"theme": "dark"})  # old content intact
            self.assertEqual(sorted(p.name for p in Path(tmp).rglob("*") if p.is_file()),
                             ["settings.json"])  # no temp file left behind

    def test_language_priority(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(i18n, "QLocale") as qlocale,
        ):
            qlocale.system.return_value.name.return_value = "fr_FR"
            with mock.patch.dict(os.environ, {"A50_LANG": ""}):
                self.assertEqual(i18n._detect_lang(), "fr")  # system locale
                settings.put("language", "es")
                self.assertEqual(i18n._detect_lang(), "es")  # menu choice beats the locale
                settings.put("language", "auto")
                self.assertEqual(i18n._detect_lang(), "fr")
            with mock.patch.dict(os.environ, {"A50_LANG": "en"}):
                self.assertEqual(i18n._detect_lang(), "en")  # env var beats everything


class ThemesTest(unittest.TestCase):
    def test_bundled_themes_are_listed(self):
        self.assertEqual(themes.available(), ["dark", "light"])

    def test_auto_json_is_not_listed_twice(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(themes, "THEMES_DIR", Path(tmp)),
        ):
            for name in ("auto", "dark"):
                Path(tmp, f"{name}.json").write_text("{}")
            self.assertEqual(themes.available(), ["dark"])

    def test_labels(self):
        with mock.patch.object(i18n, "LANG", "es"):
            self.assertEqual(themes.label("auto"), "Automático (colores del sistema)")
            self.assertEqual(themes.label("light"), "Claro")
            self.assertEqual(themes.label("dark"), "Oscuro")
            self.assertEqual(themes.label("my-theme"), "My Theme")

    def test_themes_only_change_colours(self):
        palette_cls = themes.QPalette
        for name, window, disabled_text in (("dark", "#202326", "#6d6f71"), ("light", "#eff0f1", "#a8a9ab")):
            with self.subTest(theme=name):
                app = mock.MagicMock()
                with (
                    mock.patch.object(themes, "_native_palette", palette_cls()),
                    mock.patch.object(themes, "_current", themes.AUTO),
                ):
                    self.assertEqual(themes.apply(app, name), name)
                    self.assertEqual(themes.current(), name)
                palette = app.setPalette.call_args.args[0]
                self.assertEqual(palette.color(palette_cls.ColorRole.Window).name(), window)
                disabled = palette.color(palette_cls.ColorGroup.Disabled, palette_cls.ColorRole.Text)
                self.assertEqual(disabled.name(), disabled_text)
                app.setStyle.assert_not_called()
                app.setStyleSheet.assert_not_called()

    def test_missing_or_broken_theme_falls_back_to_auto(self):
        native = themes.QPalette()
        app = mock.MagicMock()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(themes, "THEMES_DIR", Path(tmp)),
            mock.patch.object(themes, "_native_palette", native),
            self.assertLogs(themes.LOGGER, "WARNING"),
        ):
            Path(tmp, "broken.json").write_text('{"NotARole": "#000000"}')
            self.assertEqual(themes.apply(app, "does-not-exist"), themes.AUTO)
            self.assertEqual(themes.apply(app, "broken"), themes.AUTO)
        app.setPalette.assert_called_with(native)

    def test_malformed_theme_files_fall_back_to_auto(self):
        native = themes.QPalette()
        bad_files = ["[]", '{"Window": null}', '{"disabled": []}', '{"Window": "#zzz"}', "{not json"]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(themes, "THEMES_DIR", Path(tmp)),
            mock.patch.object(themes, "_native_palette", native),
            mock.patch.object(themes, "_current", "dark"),
            self.assertLogs(themes.LOGGER, "WARNING"),
        ):
            for i, content in enumerate(bad_files):
                with self.subTest(content=content):
                    Path(tmp, f"bad{i}.json").write_text(content)
                    app = mock.MagicMock()
                    self.assertEqual(themes.apply(app, f"bad{i}"), themes.AUTO)
                    app.setPalette.assert_called_once_with(native)
                    self.assertEqual(themes.current(), themes.AUTO)


class RestartAppTest(unittest.TestCase):
    def test_drops_a50_lang_and_reports_failure(self):
        # Points 4 and 5: a failed start is reported, and the new process
        # doesn't inherit A50_LANG, so the language picked in the menu applies.
        with (
            mock.patch.dict(os.environ, {"A50_LANG": "fr"}),
            mock.patch.object(gui, "QProcess") as process_cls,
        ):
            process = process_cls.return_value
            process.startDetached.return_value = (False, -1)
            self.assertFalse(gui.restart_app())
            process.startDetached.return_value = (True, 1234)
            self.assertTrue(gui.restart_app())
        env = process.setProcessEnvironment.call_args.args[0]
        self.assertFalse(env.contains("A50_LANG"))
        process.setArguments.assert_called_with([str(gui.SCRIPT_PATH)])


class MenuSlotsTest(unittest.TestCase):
    """The menu slots never let an exception escape (PyQt6 would abort the app)."""

    def _window(self):
        window = mock.MagicMock()
        window._dirty = False
        window.eq.has_pending.return_value = False
        window._lang_actions = {c: mock.MagicMock() for c in ("auto", "en", "es", "fr")}
        window._theme_actions = {n: mock.MagicMock() for n in ("auto", "dark", "light")}
        window._save_setting = lambda key, value: gui.A50Window._save_setting(window, key, value)
        return window

    def test_unwritable_config_warns_instead_of_crashing(self):
        window = self._window()
        with (
            mock.patch.object(gui.settings, "put", side_effect=PermissionError("read-only")),
            mock.patch.object(gui.QMessageBox, "warning") as warning,
        ):
            self.assertFalse(gui.A50Window._save_setting(window, "theme", "dark"))
        warning.assert_called_once()

    def test_unsaved_language_restores_the_menu(self):
        window = self._window()
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(gui.settings, "put", side_effect=OSError("disk full")),
            mock.patch.object(gui.QMessageBox, "warning"),
            mock.patch.object(gui.QMessageBox, "question") as question,
        ):
            gui.A50Window._set_language(window, "es")
        window._lang_actions["auto"].setChecked.assert_called_with(True)
        question.assert_not_called()

    def test_unsaved_language_with_an_unknown_previous_one(self):
        # "de" has no menu entry (hand-edited file, newer version...): roll back
        # to Automatic instead of raising KeyError in the slot.
        window = self._window()
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(gui.QMessageBox, "warning"),
        ):
            settings.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            settings.SETTINGS_PATH.write_text('{"language": "de"}')
            with mock.patch.object(gui.settings, "put", side_effect=OSError("disk full")):
                gui.A50Window._set_language(window, "es")
        window._lang_actions["auto"].setChecked.assert_called_with(True)

    def test_no_restart_offered_when_the_language_does_not_change(self):
        # Running in Spanish after declining a restart to French: picking
        # Spanish again just saves it, it doesn't offer a pointless restart.
        window = self._window()
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(i18n, "LANG", "es"),
            mock.patch.object(gui.QMessageBox, "question") as question,
        ):
            settings.put("language", "fr")
            gui.A50Window._set_language(window, "es")
            self.assertEqual(settings.get("language"), "es")
        question.assert_not_called()

    def test_failed_restart_warns_and_keeps_the_window(self):
        window = self._window()
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(
                gui.QMessageBox, "question", return_value=gui.QMessageBox.StandardButton.Yes
            ),
            mock.patch.object(gui.QMessageBox, "warning") as warning,
            mock.patch.object(gui, "restart_app", return_value=False),
        ):
            gui.A50Window._set_language(window, "es")
            self.assertEqual(settings.get("language"), "es")
        warning.assert_called_once()
        window.close.assert_not_called()

    def test_failed_theme_checks_automatic_again(self):
        window = self._window()
        with (
            tempfile.TemporaryDirectory() as tmp,
            _isolated_settings(tmp),
            mock.patch.object(gui.themes, "apply", return_value=themes.AUTO),
            mock.patch.object(gui, "QApplication"),
        ):
            gui.A50Window._set_theme(window, "dark")
            self.assertEqual(settings.get("theme"), themes.AUTO)
        window._theme_actions[themes.AUTO].setChecked.assert_called_with(True)
        window.statusBar.return_value.showMessage.assert_called_once()


class SweepRegressionTest(unittest.TestCase):
    """Regressions for the bugs found by the sweep of main at 5800fc1."""

    # --- templates.py -------------------------------------------------

    def test_load_tolerates_any_file_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "user-templates.json"
            with mock.patch.object(templates, "USER_TEMPLATES_FILE", path):
                for content in (b"[]", b"null", b"\xe9t\xe9",
                                json.dumps({"A": {"gain": [0] * 5, "bands": []}}).encode(),
                                json.dumps({"A": {"gain": [0, 0], "bands": {}}}).encode()):
                    path.write_bytes(content)
                    self.assertEqual(templates._load_user_templates(), {}, content)

    def test_interrupted_save_keeps_the_previous_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "user-templates.json"
            old = {"Mix": {"gain": [1, 2, 3, 4, 5],
                           "bands": {b: (100 * b, 0) for b in range(1, 6)}}}
            with mock.patch.object(templates, "USER_TEMPLATES_FILE", path):
                templates._save_user_templates(old)
                with (mock.patch.object(templates.os, "fsync", side_effect=OSError("disk full")),
                      self.assertRaises(OSError)):
                    templates._save_user_templates({})
                self.assertEqual(templates._load_user_templates(), old)

    # --- eq_widget.py -------------------------------------------------

    def test_delete_with_unwritable_library_warns_and_keeps_preset(self):
        widget = EqWidgetPersistAndPushTest._make(
            self, user_templates={"Mine": {"gain": [0] * 5, "bands": {}}}, combo_data="Mine")
        with (mock.patch("eq_widget.QMessageBox") as box,
              mock.patch("eq_widget._save_user_templates", side_effect=PermissionError("ro"))):
            box.StandardButton.Yes = "yes"
            box.question.return_value = "yes"
            widget._on_delete_template_for_slot(1)
        box.warning.assert_called_once()
        self.assertIn("Mine", widget._user_templates)

    def test_reload_keeps_a_device_preset_the_library_does_not_know(self):
        bands = {1: (80, 0), 2: (500, 1234), 3: (900, 4321), 4: (3000, 777), 5: (9000, 0)}
        foreign = {"name": "FROM ACC", "gain": [1, 2, 3, 4, 5], "bands": bands}
        media = templates._EQ_TEMPLATES["MEDIA"]
        device = {1: foreign, 2: dict(media, name="MEDIA"), 3: dict(media, name="MEDIA")}
        widget = EqWidgetReloadUnderLockTest._make_widget(self, device)
        widget.reload_under_lock(1)
        self.assertEqual(widget.template_combos[1].currentData(), EqTemplatesWidget.ON_DEVICE)
        self.assertEqual(widget._slot_modified[1], set())
        # An edit then Sync keeps the device's name and bandwidths.
        widget._slot_pending[1] = {3}
        widget.push_pending_to_device()
        widget.device.set_eq_preset_name.assert_called_with(1, "FROM ACC")
        widget.device.set_eq_preset_freq_and_bw.assert_any_call(1, 2, 500, 1234)

    def test_band_back_to_template_repaints_the_meter(self):
        widget = EqWidgetHandlersTest._make(self)
        painted = []
        widget._refresh_meter = lambda: painted.append(set(widget._slot_modified[1]))
        media = templates._EQ_TEMPLATES["MEDIA"]
        widget._on_band_modified(3, 5)
        widget._on_band_modified(3, media["gain"][2])
        self.assertEqual(painted[-1], set())

    def test_too_long_name_is_refused_before_anything_is_saved(self):
        widget = EqWidgetPersistAndPushTest._make(self)
        with (mock.patch("eq_widget.QInputDialog.getText",
                         side_effect=[("é" * 30, True), (None, False)]),
              mock.patch("eq_widget.QMessageBox") as box):
            self.assertIsNone(widget._prompt_new_template_name())
        box.warning.assert_called_once()

    def test_refused_device_write_leaves_library_and_disk_untouched(self):
        widget = EqWidgetPersistAndPushTest._make(self)
        widget.device.set_eq_preset_name.side_effect = AssertionError()
        with (mock.patch("eq_widget.QApplication"), mock.patch("eq_widget.QMessageBox") as box,
              mock.patch("eq_widget._save_user_templates") as save):
            widget._persist_and_push(1, "NewMix", is_new=True, btn=mock.MagicMock(),
                                     busy_key="btn_apply_busy", idle_key="btn_apply")
        self.assertNotIn("NewMix", widget._user_templates)
        save.assert_not_called()
        self.assertIn("AssertionError", str(box.warning.call_args))

    def test_create_keeps_other_slots_edits_and_the_active_slot(self):
        widget = EqWidgetPersistAndPushTest._make(self)
        widget.reload_under_lock = mock.MagicMock()
        widget._slot_pending[2] = {1}
        with mock.patch("eq_widget.QApplication"), mock.patch("eq_widget._save_user_templates"):
            widget._persist_and_push(1, "NewMix", is_new=True, btn=mock.MagicMock(),
                                     busy_key="btn_apply_busy", idle_key="btn_apply")
        widget.reload_under_lock.assert_not_called()
        self.assertEqual(widget._slot_pending[2], {1})
        self.assertEqual(widget._device_active_eq, 1)

    def test_failed_sync_keeps_the_user_preset(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        mine = {"gain": list(media["gain"]), "bands": dict(media["bands"])}
        widget = EqWidgetPushPendingTest._make(
            self, user_templates={"Mine": dict(mine)}, combos={1: "Mine"},
            slot_bands={1: [(f, g + 1) for f, g in
                            EqWidgetPushPendingTest._bands_from_template("MEDIA")], 2: [], 3: []},
            slot_modified={1: {1}, 2: set(), 3: set()}, slot_pending={1: {1}, 2: set(), 3: set()})
        widget.device.set_eq_preset_gain.side_effect = OSError("unplugged")
        with mock.patch("eq_widget._save_user_templates"), self.assertRaises(OSError):
            widget.push_pending_to_device()
        self.assertEqual(widget._user_templates["Mine"]["gain"], mine["gain"])
        self.assertEqual(widget._slot_modified[1], {1})

    def test_unread_active_slot_is_never_written(self):
        widget = EqWidgetPushPendingTest._make(self, device_active=None, selected_slot=1)
        widget.push_pending_to_device()
        widget.device.set_active_eq_preset.assert_not_called()

    # --- gui.py -------------------------------------------------------

    def _window(self, **reads):
        window = mock.MagicMock()
        window._loading = False
        window.slider_widgets = {}
        for name, value in reads.items():
            getattr(window.device, name).side_effect = (
                value if isinstance(value, Exception) else None)
            getattr(window.device, name).return_value = value
        return window

    def test_failed_reads_disable_controls_and_sync_skips_them(self):
        err = OSError("timeout")
        window = self._window(get_balance=err, get_noise_gate_mode=err,
                              get_alert_volume=err, get_active_eq_preset=err)
        window.cmb_gate.findData.return_value = -1
        gui.A50Window.reload_all(window)
        window.sld_balance.setEnabled.assert_called_with(False)
        window.cmb_gate.setEnabled.assert_called_with(False)
        window.sld_alert.setEnabled.assert_called_with(False)
        for w in (window.sld_balance, window.cmb_gate, window.sld_alert):
            w.isEnabled.return_value = False
        with mock.patch.object(gui, "QApplication"):
            gui.A50Window._on_save(window)
        window.device.set_default_balance.assert_not_called()
        window.device.set_noise_gate_mode.assert_not_called()
        window.device.set_alert_volume.assert_not_called()

    def test_sync_writes_the_default_balance_only_when_the_slider_moved(self):
        window = self._window(get_balance=120)
        window.cmb_gate.findData.return_value = 0
        gui.A50Window.reload_all(window)
        window.sld_balance.isEnabled.return_value = True
        window.sld_balance.value.return_value = 120
        with mock.patch.object(gui, "QApplication"):
            gui.A50Window._on_save(window)
        window.device.set_default_balance.assert_not_called()
        window.sld_balance.value.return_value = 200
        with mock.patch.object(gui, "QApplication"):
            gui.A50Window._on_save(window)
        window.device.set_default_balance.assert_called_once_with(200)

    def test_gate_change_announces_nothing_before_sync(self):
        window = mock.MagicMock()
        window._loading = False
        gui.A50Window._on_gate_changed(window, 0)
        window.statusBar.return_value.showMessage.assert_not_called()
        window._mark_dirty.assert_called_once()

    def test_apps_dir_follows_xdg_data_home(self):
        import importlib
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/xdg/data"}):
            try:
                self.assertEqual(importlib.reload(gui).APPS_DIR, Path("/xdg/data/applications"))
            finally:
                importlib.reload(gui)

    def test_base_info_shows_the_base_when_the_headset_is_off(self):
        window = mock.MagicMock()
        window._device_lock = mock.MagicMock()
        window.device.get_device_info.return_value = DeviceInfo(vendor_id=0x9886, product_id=0x2C)
        window.device.get_base_firmware_version.return_value = FirmwareVersion(major=40372, minor=43)
        window.device.get_headset_firmware_version.side_effect = AssertionError()
        with (mock.patch.object(gui, "_raw_request", side_effect=OSError("SLAVE")),
              mock.patch.object(gui, "QMessageBox") as box):
            gui.A50Window._show_base_info(window)
        box.warning.assert_not_called()
        text = box.information.call_args[0][2]
        self.assertIn("40372.43", text)
        self.assertIn("AssertionError", text)

    # --- raw_request.py -----------------------------------------------

    def test_raw_request_raises_on_an_error_answer(self):
        from raw_request import RawRequestError, _raw_request
        device = mock.MagicMock()
        device._dev.read.return_value = (bytes([0x02, 0x01, 29, 5, 0, 0, 1])
                                         + b"HID_ERROR_SLAVE_NO_SLAVE\x00")
        with self.assertRaisesRegex(RawRequestError, "SLAVE_NO_SLAVE"):
            _raw_request(device, 0x83, b"\x01")

    # --- menu_install.py ----------------------------------------------

    def test_exec_line_quotes_paths(self):
        import menu_install
        with tempfile.TemporaryDirectory() as tmp:
            apps = Path(tmp)
            with mock.patch.object(menu_install.sys, "executable", "/opt/my env/python"):
                menu_install.install_entry(apps, apps / "a.desktop", apps / "old.desktop",
                                           "astro-a50-gui", Path("/home/u/100% a/gui.py"))
            exec_line = next(line for line in (apps / "a.desktop").read_text().splitlines()
                             if line.startswith("Exec="))
        self.assertEqual(exec_line, 'Exec="/opt/my env/python" "/home/u/100%% a/gui.py"')

    def test_remove_entry_reports_a_failed_unlink(self):
        import menu_install
        with tempfile.TemporaryDirectory() as tmp:
            apps = Path(tmp)
            (apps / "a.desktop").write_text("x")
            with (mock.patch.object(Path, "unlink", side_effect=PermissionError("ro")),
                  self.assertRaises(OSError)):
                menu_install.remove_entry(apps, apps / "a.desktop", apps / "old.desktop")

    # --- process_lock.py ----------------------------------------------

    @staticmethod
    def _proc(root: Path, pid: int, *, comm: bytes, start: int, cmdline=b"", cwd="/"):
        d = root / str(pid)
        d.mkdir()
        (d / "comm").write_bytes(comm + b"\n")
        (d / "cmdline").write_bytes(cmdline)
        (d / "stat").write_bytes(f"{pid} (x) S".encode() + b" 0" * 18 + f" {start} 0".encode())
        (d / "exe").symlink_to("/usr/bin/python3")
        (d / "cwd").symlink_to(cwd)
        return d

    def test_instance_scan_survives_odd_processes_and_kills_only_older_ones(self):
        import process_lock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            me = os.getpid()
            name = process_lock.PROCESS_NAME.encode()
            self._proc(root, me, comm=name, start=500)
            self._proc(root, 10, comm=name, start=100)            # older: stop it
            self._proc(root, 99999, comm=name, start=900)         # newer: leave it
            self._proc(root, 11, comm=b"\xff\xfe", start=50)      # non-UTF-8 comm
            found = process_lock._find_other_instances(Path("/x/gui.py"), proc=root)
        self.assertEqual(found, [10])

    def test_relative_script_resolves_against_the_process_cwd(self):
        import process_lock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "other"
            other.mkdir()
            (other / "gui.py").write_text("")
            ours = (root / "ours.py").resolve()
            d = self._proc(root, 12, comm=b"python3", start=1,
                           cmdline=b"python3\x00gui.py\x00", cwd=str(other))
            with mock.patch.object(process_lock.Path, "cwd", return_value=root):
                self.assertFalse(process_lock._is_our_instance(d, ours.with_name("gui.py")))
            self.assertTrue(process_lock._is_our_instance(d, (other / "gui.py").resolve()))

    def test_wait_for_a_foreign_process_does_not_raise(self):
        import process_lock
        with mock.patch.object(process_lock.os, "kill", side_effect=PermissionError()):
            self.assertTrue(process_lock._wait_for_exit(1, timeout_s=0.1))

    # --- status_worker.py ---------------------------------------------

    def test_worker_reopens_the_base_after_the_handle_died(self):
        import threading

        import usb.core

        import status_worker
        device = mock.MagicMock()
        device.get_headset_status.side_effect = [usb.core.USBError("gone"), "status"]
        device.get_battery_status.side_effect = [usb.core.USBError("gone"), "battery"]
        worker = status_worker.StatusWorker.__new__(status_worker.StatusWorker)
        worker._device, worker._lock = device, threading.RLock()
        worker.statusReady = mock.MagicMock()
        worker.reconnected = mock.MagicMock()
        with mock.patch.object(status_worker.Device, "__init__", return_value=None) as init:
            worker.refresh()
        init.assert_called_once_with(device)
        worker.statusReady.emit.assert_called_once_with("status", "battery")
        worker.reconnected.emit.assert_called_once()

    def test_reconnect_reloads_only_what_failed_to_load(self):
        window = mock.MagicMock()
        window.slider_widgets = {}
        for c in (window.sld_balance, window.cmb_gate, window.sld_alert):
            c.isEnabled.return_value = True
        gui.A50Window._on_reconnected(window)
        window.reload_all.assert_not_called()
        window.sld_alert.isEnabled.return_value = False
        gui.A50Window._on_reconnected(window)
        window.reload_all.assert_called_once()

    def test_failed_library_write_after_create_keeps_device_state(self):
        widget = EqWidgetPersistAndPushTest._make(self)
        btn = mock.MagicMock()
        with (mock.patch("eq_widget.QApplication"), mock.patch("eq_widget.QMessageBox") as box,
              mock.patch("eq_widget._save_user_templates", side_effect=OSError("ro"))):
            widget._persist_and_push(1, "NewMix", is_new=True, btn=btn,
                                     busy_key="btn_apply_busy", idle_key="btn_apply")
        self.assertEqual(widget._device_templates[1], "NewMix")
        btn.setText.assert_called_with(gui.t("btn_apply"))
        box.warning.assert_called_once()
        self.assertEqual(widget._slot_pending[1], set())

    def test_save_of_a_preset_shown_in_another_slot_pends_that_slot(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        mine = {"gain": list(media["gain"]), "bands": dict(media["bands"])}
        widget = EqWidgetPersistAndPushTest._make(
            self, user_templates={"Mine": mine}, combo_data="Mine")
        widget.template_combos[2] = _MockCombo(current_data="Mine")
        widget._slot_bands[2] = [(f, g) for f, g in
                                 EqWidgetPushPendingTest._bands_from_template("MEDIA")]
        widget._device_templates[2] = "Mine"
        with mock.patch("eq_widget.QApplication"), mock.patch("eq_widget._save_user_templates"):
            widget._persist_and_push(1, "Mine", is_new=False, btn=mock.MagicMock(),
                                     busy_key="btn_save_eq_busy", idle_key="btn_save_eq")
        self.assertEqual(widget._slot_pending[2], {1, 2, 3, 4, 5})
        self.assertEqual(widget._slot_bands[2][2][1], 4)
        self.assertEqual(widget._slot_modified[2], set())

    def test_presets_the_device_took_are_saved_when_a_later_slot_fails(self):
        media = templates._EQ_TEMPLATES["MEDIA"]
        mine = {"gain": list(media["gain"]), "bands": dict(media["bands"])}
        edited = [(f, g + 1) for f, g in EqWidgetPushPendingTest._bands_from_template("MEDIA")]
        widget = EqWidgetPushPendingTest._make(
            self, user_templates={"Mine": dict(mine)}, combos={1: "Mine", 2: "PRO"},
            slot_bands={1: list(edited), 2: list(edited), 3: []},
            slot_pending={1: {1}, 2: {1}, 3: set()})
        widget.device.set_eq_preset_name.side_effect = [None, OSError("unplugged")]
        with mock.patch("eq_widget._save_user_templates") as save, self.assertRaises(OSError):
            widget.push_pending_to_device()
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
