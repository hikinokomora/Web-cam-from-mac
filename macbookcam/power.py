"""Пока идёт трансляция: Mac не засыпает и macOS не «усыпляет» приложение (App Nap)."""

import sys

# NSActivityUserInitiated = 0x00FFFFFF | NSActivityIdleSystemSleepDisabled; запасные значения на случай,
# если константы не экспортируются из Foundation
_IDLE_SYSTEM_SLEEP_DISABLED = 1 << 20
_USER_INITIATED = 0x00FFFFFF | _IDLE_SYSTEM_SLEEP_DISABLED
_LATENCY_CRITICAL = 0xFF00000000


class KeepAwake:
    def __init__(self):
        self._token = None

    @property
    def active(self):
        return self._token is not None

    def acquire(self, reason="MacBookCam is streaming the camera"):
        if sys.platform != "darwin" or self._token is not None:
            return
        try:
            import Foundation
            user_initiated = getattr(Foundation, "NSActivityUserInitiated", _USER_INITIATED)
            latency_critical = getattr(Foundation, "NSActivityLatencyCritical", _LATENCY_CRITICAL)
            self._token = Foundation.NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
                user_initiated | latency_critical, reason)
        except Exception:  # noqa: BLE001
            self._token = None

    def release(self):
        if self._token is None:
            return
        try:
            import Foundation
            Foundation.NSProcessInfo.processInfo().endActivity_(self._token)
        except Exception:  # noqa: BLE001
            pass
        self._token = None
