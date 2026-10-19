"""
LockChime - NVDA Lock Key Sound Addon
Author: Leo
Version: 1.0.0

Plays a sound when Caps Lock, Num Lock, or Scroll Lock is turned on
or off.
"""

import globalPluginHandler
import addonHandler
import gui
import config
import wx
import os
import threading
import ctypes
import nvwave
import wave
import array
import tempfile

addonHandler.initTranslation()

VK_CAPITAL = 0x14
VK_NUMLOCK = 0x90
VK_SCROLL = 0x91

KEYS = ("caps", "num", "scroll")
KEY_LABELS = {
    "caps": "Caps Lock",
    "num": "Num Lock",
    "scroll": "Scroll Lock",
}
KEY_VK = {
    "caps": VK_CAPITAL,
    "num": VK_NUMLOCK,
    "scroll": VK_SCROLL,
}

confspec = {}
for key in KEYS:
    confspec[f"{key}Enabled"] = "boolean(default=True)"
    confspec[f"{key}Volume"] = "integer(default=100, min=0, max=100)"
    for state in ("On", "Off"):
        defaultSound = "pos1" if state == "On" else "neg1"
        confspec[f"{key}{state}Mode"] = "string(default='pack')"
        confspec[f"{key}{state}Sound"] = f"string(default='{defaultSound}')"
        confspec[f"{key}{state}CustomPath"] = "string(default='')"
config.conf.spec["LockChime"] = confspec

SOUND_PACK = {
    "pos1": "Classic Positive",
    "neg1": "Classic Negative",
    "pos2": "Soft Positive",
    "neg2": "Soft Negative",
    "bell": "Bell Ding",
    "hint": "Quick Hint",
    "coin": "Retro Coin",
    "notif": "Notification Ping",
}


def get_sounds_dir():
    for addon in addonHandler.getRunningAddons():
        if addon.manifest["name"] == "lockChime":
            return os.path.join(addon.path, "sounds")
    return os.path.join(os.path.dirname(__file__), "..", "sounds")


def get_pack_sound_path(sound_id):
    return os.path.join(get_sounds_dir(), sound_id + ".wav")


def apply_volume(src_path, volume_percent, cache_key):
    if volume_percent >= 100:
        return src_path
    try:
        with wave.open(src_path, "rb") as w:
            params = w.getparams()
            frames = w.readframes(w.getnframes())
        if params.sampwidth != 2:
            return src_path
        samples = array.array("h", frames)
        factor = max(0, min(100, volume_percent)) / 100.0
        for i in range(len(samples)):
            samples[i] = int(samples[i] * factor)
        out_path = os.path.join(tempfile.gettempdir(), f"lockchime_{cache_key}.wav")
        with wave.open(out_path, "wb") as out:
            out.setparams(params)
            out.writeframes(samples.tobytes())
        return out_path
    except Exception:
        return src_path


def play_sound(path, volume_percent=100, cache_key="tmp"):
    def _play():
        try:
            nvwave.playWaveFile(apply_volume(path, volume_percent, cache_key))
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def get_toggle_state(vk):
    return bool(ctypes.windll.user32.GetKeyState(vk) & 1)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(LockChimeSettingsPanel)

    def _handleToggle(self, key):
        if not config.conf["LockChime"][f"{key}Enabled"]:
            return
        state = get_toggle_state(KEY_VK[key])
        prefix = "On" if state else "Off"
        mode = config.conf["LockChime"][f"{key}{prefix}Mode"]
        sound_id = config.conf["LockChime"][f"{key}{prefix}Sound"]
        custom_path = config.conf["LockChime"][f"{key}{prefix}CustomPath"]
        volume = config.conf["LockChime"][f"{key}Volume"]

        if mode == "pack":
            path = get_pack_sound_path(sound_id)
            if os.path.isfile(path):
                play_sound(path, volume, f"{key}{prefix}")
        elif mode == "custom":
            if custom_path and os.path.isfile(custom_path):
                play_sound(custom_path, volume, f"{key}{prefix}")

    def script_capsLock(self, gesture):
        gesture.send()
        self._handleToggle("caps")
    script_capsLock.canPropagate = True

    def script_numLock(self, gesture):
        gesture.send()
        self._handleToggle("num")
    script_numLock.canPropagate = True

    def script_scrollLock(self, gesture):
        gesture.send()
        self._handleToggle("scroll")
    script_scrollLock.canPropagate = True

    __gestures = {
        "kb:capslock": "capsLock",
        "kb:numlock": "numLock",
        "kb:scrolllock": "scrollLock",
    }

    def terminate(self):
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(LockChimeSettingsPanel)
        super().terminate()


class LockChimeSettingsPanel(gui.settingsDialogs.SettingsPanel):
    title = "LockChime"

    def makeSettings(self, sizer):
        helper = gui.guiHelper.BoxSizerHelper(self, sizer=sizer)
        packIds = list(SOUND_PACK.keys())
        modeMap = {"pack": 0, "custom": 1, "disabled": 2}

        self._controls = {}

        for key in KEYS:
            helper.addItem(wx.StaticText(self, label=KEY_LABELS[key]))

            enabledCtrl = helper.addItem(wx.CheckBox(self, label=f"Enable {KEY_LABELS[key]} sounds"))
            enabledCtrl.SetValue(config.conf["LockChime"][f"{key}Enabled"])
            self._controls[f"{key}Enabled"] = enabledCtrl

            volumeCtrl = helper.addLabeledControl(
                f"{KEY_LABELS[key]} volume:", wx.SpinCtrl, min=0, max=100,
                initial=config.conf["LockChime"][f"{key}Volume"]
            )
            self._controls[f"{key}Volume"] = volumeCtrl

            for state in ("On", "Off"):
                modeCtrl = helper.addLabeledControl(
                    f"{state} sound:", wx.Choice, choices=["Pack sound", "Custom WAV", "Disabled"]
                )
                modeCtrl.SetSelection(modeMap.get(config.conf["LockChime"][f"{key}{state}Mode"], 0))
                self._controls[f"{key}{state}Mode"] = modeCtrl

                packCtrl = helper.addLabeledControl(
                    "Pack sound:", wx.Choice, choices=list(SOUND_PACK.values())
                )
                currentPack = config.conf["LockChime"][f"{key}{state}Sound"]
                packCtrl.SetSelection(packIds.index(currentPack) if currentPack in packIds else 0)
                self._controls[f"{key}{state}Sound"] = packCtrl

                pathSizer = wx.BoxSizer(wx.HORIZONTAL)
                pathCtrl = wx.TextCtrl(self, value=config.conf["LockChime"][f"{key}{state}CustomPath"])
                pathSizer.Add(pathCtrl, proportion=1)
                browseBtn = wx.Button(self, label="Browse...")
                browseBtn.Bind(wx.EVT_BUTTON, lambda e, p=pathCtrl: self._onBrowse(p))
                pathSizer.Add(browseBtn)
                helper.addItem(pathSizer)
                self._controls[f"{key}{state}CustomPath"] = pathCtrl

                previewBtn = helper.addItem(wx.Button(self, label=f"Test {KEY_LABELS[key]} {state}"))
                previewBtn.Bind(
                    wx.EVT_BUTTON,
                    lambda e, k=key, s=state: self._testSound(k, s),
                )

    def _onBrowse(self, targetField):
        with wx.FileDialog(
            self, message="Choose a WAV file",
            wildcard="WAV files (*.wav)|*.wav",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                targetField.SetValue(dlg.GetPath())

    def _testSound(self, key, state):
        packIds = list(SOUND_PACK.keys())
        modeCtrl = self._controls[f"{key}{state}Mode"]
        packCtrl = self._controls[f"{key}{state}Sound"]
        pathCtrl = self._controls[f"{key}{state}CustomPath"]

        sel = modeCtrl.GetSelection()
        if sel == 0:
            path = get_pack_sound_path(packIds[packCtrl.GetSelection()])
        elif sel == 1:
            path = pathCtrl.GetValue()
        else:
            gui.messageBox("Sound is set to Disabled.", "LockChime", wx.OK | wx.ICON_INFORMATION)
            return

        if path and os.path.isfile(path):
            volume = self._controls[f"{key}Volume"].GetValue()
            play_sound(path, volume, f"preview_{key}{state}")
        else:
            gui.messageBox(f"Sound file not found:\n{path}", "LockChime", wx.OK | wx.ICON_ERROR)

    def onSave(self):
        packIds = list(SOUND_PACK.keys())
        modeMap = {0: "pack", 1: "custom", 2: "disabled"}

        for key in KEYS:
            config.conf["LockChime"][f"{key}Enabled"] = self._controls[f"{key}Enabled"].GetValue()
            config.conf["LockChime"][f"{key}Volume"] = self._controls[f"{key}Volume"].GetValue()
            for state in ("On", "Off"):
                config.conf["LockChime"][f"{key}{state}Mode"] = modeMap[self._controls[f"{key}{state}Mode"].GetSelection()]
                config.conf["LockChime"][f"{key}{state}Sound"] = packIds[self._controls[f"{key}{state}Sound"].GetSelection()]
                config.conf["LockChime"][f"{key}{state}CustomPath"] = self._controls[f"{key}{state}CustomPath"].GetValue()
