#!/usr/bin/env bash

# mcu-mdt — dependency installer
# Tested on Ubuntu 22.04 / 24.04
#
# Usage:
#   ./install.sh              # core deps only
#   ./install.sh --avr        # + AVR toolchain
#   ./install.sh --stm32      # + STM32/ARM toolchain
#   ./install.sh --dev        # + Python dev/test tools
#   ./install.sh --avr --stm32 --dev   # everything

set -euo pipefail

INSTALL_AVR=0
INSTALL_STM32=0
INSTALL_DEV=0

for arg in "$@"; do
    case "$arg" in
        --avr)   INSTALL_AVR=1   ;;
        --stm32) INSTALL_STM32=1 ;;
        --dev)   INSTALL_DEV=1   ;;
        --help|-h)
            echo "Usage: $0 [--avr] [--stm32] [--dev]"
            echo ""
            echo "  (no flags)  Install Python runtime dependencies only"
            echo "  --avr       Also install AVR toolchain (avr-gcc, avrdude)"
            echo "  --stm32     Also install ARM toolchain (arm-none-eabi-gcc, st-flash)"
            echo "  --dev       Also install Python dev/test tools (pytest, ruff)"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg  (use --help for usage)"
            exit 1
            ;;
    esac
done

info()    { echo "[mcu-mdt] $*"; }
success() { echo "[mcu-mdt] ✓ $*"; }
section() { echo ""; echo "── $* ──────────────────────────────────────────"; }

require_ubuntu() {
    if ! command -v apt-get &>/dev/null; then
        echo "[mcu-mdt] ERROR: This script requires apt-get (Ubuntu/Debian)."
        exit 1
    fi
}

require_ubuntu

section "Updating package index"
sudo apt-get update -qq

section "Python runtime dependencies"

PYTHON_PKGS=(
    python3
    python3-serial      # pyserial
    python3-yaml        # pyyaml
)

info "Installing: ${PYTHON_PKGS[*]}"
sudo apt-get install -y "${PYTHON_PKGS[@]}"
success "Python runtime dependencies installed"

if [ "$INSTALL_DEV" -eq 1 ]; then
    section "Python dev/test dependencies"

    DEV_PKGS=(
        python3-pytest      # pytest
        python3-pytest-cov  # pytest-cov
    )

    info "Installing: ${DEV_PKGS[*]}"
    sudo apt-get install -y "${DEV_PKGS[@]}"

    # ruff is not packaged in apt: install via pip with --break-system-packages
    info "Installing ruff via pip..."
    pip3 install --break-system-packages ruff

    success "Dev/test dependencies installed"
fi

if [ "$INSTALL_AVR" -eq 1 ]; then
    section "AVR toolchain"

    AVR_PKGS=(
        gcc-avr        # avr-gcc, avr-ar, avr-objcopy
        binutils-avr   # avr-objcopy, avr-size
        avr-libc       # AVR C standard library
        avrdude        # flash programmer
    )

    info "Installing: ${AVR_PKGS[*]}"
    sudo apt-get install -y "${AVR_PKGS[@]}"
    success "AVR toolchain installed"
fi

if [ "$INSTALL_STM32" -eq 1 ]; then
    section "STM32 / ARM toolchain"

    ARM_PKGS=(
        gcc-arm-none-eabi       # arm-none-eabi-gcc, ar, objcopy, size
        binutils-arm-none-eabi  # arm-none-eabi-objcopy, objdump
    )

    info "Installing: ${ARM_PKGS[*]}"
    sudo apt-get install -y "${ARM_PKGS[@]}"

    # st-flash (stlink) — check apt first, fall back to snap
    if apt-cache show stlink-tools &>/dev/null; then
        info "Installing st-flash via apt..."
        sudo apt-get install -y stlink-tools
    else
        info "stlink-tools not in apt — trying snap..."
        if command -v snap &>/dev/null; then
            sudo snap install stlink
        else
            echo "[mcu-mdt] WARNING: Could not install st-flash automatically."
            echo "          Install it manually from https://github.com/stlink-org/stlink"
        fi
    fi

    success "STM32/ARM toolchain installed"
fi

# Summary
section "Done"
echo ""
echo "  Installed:"
echo "    ✓ Python runtime (python3, pyserial, pyyaml)"
[ "$INSTALL_DEV"   -eq 1 ] && echo "    ✓ Dev/test tools (pytest, pytest-cov, ruff)"
[ "$INSTALL_AVR"   -eq 1 ] && echo "    ✓ AVR toolchain  (avr-gcc, avrdude)"
[ "$INSTALL_STM32" -eq 1 ] && echo "    ✓ ARM toolchain  (arm-none-eabi-gcc, st-flash)"
echo ""
echo "  Run the host tool:"
echo "    python3 mcu_mdt.py build/<MCU>/build_info.yaml"
echo ""