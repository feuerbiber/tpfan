#!/usr/bin/env bash
#
# tpfan — System-Installer für ThinkPad E14 Gen 7
#
# Voll-Setup auf Fedora-artigen Distros:
#   1. Prüft root
#   2. Installiert System-Abhängigkeiten via dnf
#   3. Installiert daemon + GUI Python-Pakete systemweit
#   4. Kopiert Packaging-Dateien (systemd, D-Bus, polkit, modprobe, desktop)
#   5. Lädt thinkpad_acpi mit fan_control=1 neu
#   6. Aktiviert und startet tpfan-daemon.service
#   7. Smoke-Check (BusName + systemd-Status)
#
# Benutzung:
#   sudo ./scripts/install.sh           # Installation
#   sudo ./scripts/install.sh --uninstall   # Deinstallation
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGING="$REPO_DIR/packaging"

PY=${TPFAN_PY:-/usr/bin/python3}
VENV_DIR=${TPFAN_VENV:-/opt/tpfan/venv}
VENV_PY="$VENV_DIR/bin/python3"

DNF_DEPS=(python3-pip python3-gobject dbus-daemon polkit)
APT_DEPS=(python3-pip python3-venv python3-gi dbus policykit-1)
PACMAN_DEPS=(python-pip python-gobject dbus polkit)

log()  { printf '\033[1;34m[tpfan]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[tpfan]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[tpfan]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m[tpfan]\033[0m %s\n' "$*"; }

# step "Beschreibung" func [args...] — meldet 'done' oder 'FEHLER'.
step() {
    local desc=$1; shift
    log "$desc …"
    set +e
    "$@"
    local rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
        ok "  ✓ done — $desc"
    else
        err "  ✗ FEHLER — $desc (rc=$rc)"
        exit $rc
    fi
}

require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "muss als root laufen (sudo verwenden)"
        exit 1
    fi
}

detect_distro_family() {
    # Liefert: fedora | debian | arch | unknown
    local id="" id_like=""
    if [[ -r /etc/os-release ]]; then
        . /etc/os-release
        id="${ID:-}"
        id_like="${ID_LIKE:-}"
    fi
    case " $id $id_like " in
        *" fedora "*|*" rhel "*|*" centos "*) echo fedora ;;
        *" debian "*|*" ubuntu "*)             echo debian ;;
        *" arch "*)                            echo arch ;;
        *)                                     echo unknown ;;
    esac
}

install_system_deps_fedora() {
    local missing=()
    for pkg in "${DNF_DEPS[@]}"; do
        rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        log "System-Abhängigkeiten bereits installiert: ${DNF_DEPS[*]}"
        return 0
    fi
    log "installiere fehlende System-Abhängigkeiten via dnf: ${missing[*]}"
    dnf install -y --setopt=install_weak_deps=False "${missing[@]}"
}

install_system_deps_debian() {
    local missing=()
    for pkg in "${APT_DEPS[@]}"; do
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null \
            | grep -q "install ok installed" || missing+=("$pkg")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        log "System-Abhängigkeiten bereits installiert: ${APT_DEPS[*]}"
        return 0
    fi
    log "installiere fehlende System-Abhängigkeiten via apt: ${missing[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
}

install_system_deps_arch() {
    local missing=()
    for pkg in "${PACMAN_DEPS[@]}"; do
        pacman -Qi "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        log "System-Abhängigkeiten bereits installiert: ${PACMAN_DEPS[*]}"
        return 0
    fi
    log "installiere fehlende System-Abhängigkeiten via pacman: ${missing[*]}"
    pacman -Sy --needed --noconfirm "${missing[@]}"
}

install_system_deps() {
    local family
    family=$(detect_distro_family)
    case "$family" in
        fedora) install_system_deps_fedora ;;
        debian) install_system_deps_debian ;;
        arch)   install_system_deps_arch ;;
        *)
            warn "Distro-Familie nicht erkannt — überspringe System-Deps"
            warn "stelle sicher dass python3 + venv, pip, PyGObject (gi), dbus und polkit installiert sind"
            ;;
    esac
}

create_venv() {
    if [[ ! -x "$VENV_PY" ]]; then
        log "erstelle venv unter $VENV_DIR (mit --system-site-packages für gi/PyGObject)"
        install -d -m 0755 "$(dirname "$VENV_DIR")"
        "$PY" -m venv --system-site-packages "$VENV_DIR"
    else
        log "venv existiert bereits unter $VENV_DIR — verwende es"
    fi
    "$VENV_PY" -m pip install --quiet --upgrade pip
}

install_python_packages() {
    create_venv
    log "installiere tpfan-daemon und tpfan-gui ins venv"
    "$VENV_PY" -m pip install --upgrade "$REPO_DIR/daemon"
    "$VENV_PY" -m pip install --upgrade "$REPO_DIR/gui"
}

install_packaging() {
    log "kopiere Packaging-Dateien"
    install -D -m 0755 "$PACKAGING/tpfan-daemon-launcher" /usr/local/bin/tpfan-daemon
    install -D -m 0755 "$PACKAGING/tpfan-gui-launcher"    /usr/local/bin/tpfan-gui
    install -D -m 0644 "$PACKAGING/tpfan-daemon.service"  /etc/systemd/system/tpfan-daemon.service
    install -D -m 0644 "$PACKAGING/org.tpfan1.conf"       /etc/dbus-1/system.d/org.tpfan1.conf
    install -D -m 0644 "$PACKAGING/org.tpfan1.service"    /usr/share/dbus-1/system-services/org.tpfan1.service
    install -D -m 0644 "$PACKAGING/org.tpfan1.policy"     /usr/share/polkit-1/actions/org.tpfan1.policy
    install -D -m 0644 "$PACKAGING/tpfan-modprobe.conf"   /etc/modprobe.d/tpfan.conf
    install -D -m 0644 "$PACKAGING/tpfan-gui.desktop"     /usr/share/applications/tpfan-gui.desktop
    install -D -m 0644 "$PACKAGING/tpfan.svg"             /usr/share/icons/hicolor/scalable/apps/tpfan.svg
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache --quiet /usr/share/icons/hicolor 2>/dev/null || true
    fi
    systemctl daemon-reload
}

FAN_CONTROL_ACTIVE=0

fan_control_is_active() {
    local p=/sys/module/thinkpad_acpi/parameters/fan_control
    [[ -r $p ]] && [[ "$(cat "$p")" == "Y" ]]
}

reload_kernel_module() {
    log "lade thinkpad_acpi mit fan_control=1 neu"
    if lsmod | grep -q '^thinkpad_acpi'; then
        if ! modprobe -r thinkpad_acpi 2>/dev/null; then
            warn "konnte thinkpad_acpi nicht entladen (in Benutzung) — Reboot nötig"
            return 0
        fi
    fi
    modprobe thinkpad_acpi || warn "modprobe thinkpad_acpi fehlgeschlagen"

    if fan_control_is_active; then
        FAN_CONTROL_ACTIVE=1
        log "  fan_control=1 ist aktiv"
    else
        warn "  fan_control=1 NICHT aktiv (vermutlich wurde das Modul auto-reloaded ohne neue Optionen)"
        warn "  Reboot durchführen, dann greift /etc/modprobe.d/tpfan.conf"
    fi
}

enable_service() {
    if [[ $FAN_CONTROL_ACTIVE -eq 1 ]]; then
        log "aktiviere und starte tpfan-daemon.service"
        systemctl enable --now tpfan-daemon.service
        # Pickt neuen Code/Service-Unit bei Re-Installs auf; auf der
        # frischen Installation ist der Service gerade erst gestartet,
        # try-restart ist dort idempotent.
        log "lade tpfan-daemon neu, falls bereits aktiv"
        systemctl try-restart tpfan-daemon.service || true
    else
        log "aktiviere tpfan-daemon.service (Start verschoben bis nach Reboot)"
        systemctl enable tpfan-daemon.service
        warn ""
        warn "WICHTIG: Reboot erforderlich, damit fan_control=1 wirksam wird."
        warn "Nach dem Reboot startet der Service automatisch."
        warn ""
    fi
}

smoke_check() {
    if [[ $FAN_CONTROL_ACTIVE -ne 1 ]]; then
        log "Smoke-Check übersprungen (Reboot ausstehend)"
        return 0
    fi
    log "Smoke-Check"
    sleep 1
    if systemctl is-active --quiet tpfan-daemon.service; then
        log "  systemd: active"
    else
        err "  systemd: NICHT aktiv — siehe 'journalctl -u tpfan-daemon -n 30'"
        return 1
    fi
    if busctl --system list 2>/dev/null | grep -q '^org\.tpfan1 '; then
        log "  D-Bus: org.tpfan1 registriert"
    else
        warn "  D-Bus: org.tpfan1 noch nicht sichtbar (kann beim Erststart verzögert sein)"
    fi
}

uninstall_python_packages() {
    if [[ -d "$VENV_DIR" ]]; then
        log "entferne venv $VENV_DIR"
        rm -rf "$VENV_DIR"
        # leere Eltern-Verzeichnisse aufräumen (z. B. /opt/tpfan)
        rmdir -p --ignore-fail-on-non-empty "$(dirname "$VENV_DIR")" 2>/dev/null || true
    else
        log "kein venv unter $VENV_DIR gefunden — überspringe"
    fi
}

uninstall_packaging() {
    log "entferne Packaging-Dateien"
    rm -f /usr/local/bin/tpfan-daemon
    rm -f /usr/local/bin/tpfan-gui
    rm -f /etc/systemd/system/tpfan-daemon.service
    rm -f /etc/dbus-1/system.d/org.tpfan1.conf
    rm -f /usr/share/dbus-1/system-services/org.tpfan1.service
    rm -f /usr/share/polkit-1/actions/org.tpfan1.policy
    rm -f /etc/modprobe.d/tpfan.conf
    rm -f /usr/share/applications/tpfan-gui.desktop
    rm -f /usr/share/icons/hicolor/scalable/apps/tpfan.svg
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache --quiet /usr/share/icons/hicolor 2>/dev/null || true
    fi
    systemctl daemon-reload
}

do_install() {
    require_root
    step "System-Abhängigkeiten prüfen"  install_system_deps
    step "Python-Pakete installieren"    install_python_packages
    step "Packaging-Dateien kopieren"    install_packaging
    step "Kernel-Modul neu laden"        reload_kernel_module
    step "systemd-Service aktivieren"    enable_service
    step "Smoke-Check"                   smoke_check
    ok "fertig. GUI starten mit: tpfan-gui"
}

remove_config() {
    if [[ -e /etc/tpfan ]]; then
        log "entferne Config-Verzeichnis /etc/tpfan"
        rm -rf /etc/tpfan
    fi
}

remove_state() {
    if [[ -e /var/lib/tpfan ]]; then
        log "entferne State-Verzeichnis /var/lib/tpfan (RPM-Statistik)"
        rm -rf /var/lib/tpfan
    fi
}

reload_module_without_fan_control() {
    log "lade thinkpad_acpi neu (ohne fan_control=1)"
    if lsmod | grep -q '^thinkpad_acpi'; then
        if modprobe -r thinkpad_acpi 2>/dev/null; then
            modprobe thinkpad_acpi || warn "modprobe thinkpad_acpi fehlgeschlagen"
        else
            warn "konnte thinkpad_acpi nicht entladen (in Benutzung) — Reboot durchführen"
        fi
    fi
}

stop_service() {
    systemctl disable --now tpfan-daemon.service 2>/dev/null || true
}

do_uninstall() {
    require_root
    step "Service stoppen und deaktivieren" stop_service
    step "Packaging-Dateien entfernen"      uninstall_packaging
    step "Python-Pakete deinstallieren"     uninstall_python_packages
    step "Config-Verzeichnis entfernen"     remove_config
    step "State-Verzeichnis entfernen"      remove_state
    step "Kernel-Modul ohne fan_control neu laden" reload_module_without_fan_control
    ok "fertig."
}

case "${1:-install}" in
    install)   do_install ;;
    --uninstall|uninstall) do_uninstall ;;
    -h|--help)
        cat <<EOF
tpfan-Installer

Usage:
  sudo $0              # Voll-Installation
  sudo $0 --uninstall  # Deinstallation
  sudo $0 --help       # diese Hilfe

Umgebungsvariablen:
  TPFAN_PY=/path/to/python3   # Python-Interpreter zum Erzeugen des venv (default: /usr/bin/python3)
  TPFAN_VENV=/path/to/venv    # Zielverzeichnis des venv (default: /opt/tpfan/venv)
EOF
        ;;
    *)
        err "unbekanntes Argument: $1 (siehe --help)"
        exit 2
        ;;
esac
