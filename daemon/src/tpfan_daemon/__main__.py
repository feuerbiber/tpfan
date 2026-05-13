from __future__ import annotations
import logging, os, signal, sys
from pathlib import Path

from gi.repository import GLib
from dasbus.connection import SystemMessageBus

from .daemon import Daemon
from .hw.sensors import Sensors
from .hw.fan import Fan
from .ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
from .ipc.polkit import authorize

CONFIG_PATH = Path(os.environ.get("TPFAN_CONFIG", "/etc/tpfan/config.toml"))


def _setup_logging():
    level = os.environ.get("TPFAN_LOG", "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)


def _sd_notify(msg: str) -> None:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s.sendto(msg.encode(), addr)
    finally:
        s.close()


def main() -> int:
    _setup_logging()
    log = logging.getLogger("tpfan-daemon")

    sensors = Sensors()
    sensors.discover()
    fan = Fan()
    if not fan.writable():
        log.error("/proc/acpi/ibm/fan not writable — load thinkpad_acpi with fan_control=1")
        return 1

    daemon = Daemon(CONFIG_PATH, sensors, fan)
    bus = SystemMessageBus()

    def authorizer(sender: str, action: str) -> None:
        authorize(bus, sender, action)

    service = TpfanService(
        state_getter=lambda: _state_dict(daemon, sensors),
        command_handler=daemon.handle,
        authorizer=authorizer,
        sender_getter=lambda: "",
    )

    bus.publish_object(OBJECT_PATH, service)
    bus.register_service(BUS_NAME)

    _sd_notify("READY=1")
    main_loop = GLib.MainLoop()

    def shutdown(*_):
        log.info("shutdown — resetting fan to auto")
        try: fan.set_level("auto")
        except Exception: pass
        main_loop.quit()

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, shutdown)

    def tick():
        try:
            tr = daemon.loop.tick()
            fan_state = fan.read()
            fans_payload = [(fan_state.speed_rpm, _lvl_to_int(tr.target_level))]
            service.Tick(tr.temps, fans_payload, tr.target_level)
            if tr.emergency:
                service.EmergencyTriggered(tr.emergency[0], tr.emergency[1])
            _sd_notify("WATCHDOG=1")
        except Exception:
            log.exception("tick failed")
        return True

    GLib.timeout_add_seconds(1, tick)
    main_loop.run()
    return 0


def _state_dict(d: Daemon, sensors: Sensors) -> dict:
    return {
        "mode": d.loop.config.mode,
        "level": d.loop._last_level,
        "temps": sensors.read_all(),
        "sensor_describe": sensors.describe(),
        "fans": [],
        "curve": d.loop.config.curve,
        "curve_sensors": list(d.loop.config.curve.sensors),
        "failsafe_temp": d.loop.config.failsafe_temp,
    }


def _lvl_to_int(lvl: str) -> int:
    return int(lvl) if lvl.isdigit() else 0xFF


if __name__ == "__main__":
    sys.exit(main())
