# build_system

One declarative description of every target. A generator (added in step 2) will walk it and
write the files a build needs. Only AVR is described so far.

## The tree

| Level | File | Owns |
|---|---|---|
| **root** | `tree_root.yaml` | the platforms, where the common code is, defaults for every target |
| **trunk** | `<platform>/tree_trunk.yaml` | one platform: toolchain, flags, recipes' data, platform defaults |
| **branch** | `<platform>/tree_branch_<name>.yaml` | one family; lists its nodes |
| **node** | inside a branch (`nodes:`) | one supported part |

Each file has `version: 1` and `type: tree_root | tree_trunk | tree_branch`. Unknown keys are
errors, so a key can never be written and silently ignored. Paths are relative to the repository
root (the folder that contains `build_system/`); absolute paths are rejected.

## Keys (as of step 1)

`tree_root.yaml`: `platform` (list, each needs a directory), `mdt_defaults`
(`port baudrate buffer_size breakpoints watchpoints elf`), `files` (`src inc build`).

`<platform>/tree_trunk.yaml`: `platform`, `mdt_defaults` (`f_cpu uart_idle`), `features`
(`uart_idle`: whether the platform can do interrupt mode at all), `toolchain.prefix`,
`build` (`lib hal_dir example_dir part_flag flags.compile flags.link hex`), `flash`, `dist`.

`<platform>/tree_branch_<name>.yaml`: `platform`, `branch`, `nodes`.

Quote any flag that contains a comma (`"-Wl,--gc-sections"`): in YAML a bare comma splits the item.

## AVR

Only the parts listed in `avr/tree_branch_*.yaml` are supported (80: the table in
`docs/avr/info.md`). Nodes carry no data: flash, RAM and EEPROM sizes stay in the ATDF files
(`pc_tool/mcu_db/avr`), so there is one source for them.

## Where each fact of `hal/avr/Makefile` lives

| Makefile | Descriptor |
|---|---|
| `CC AR OBJCOPY SIZE` | `toolchain.prefix` + `gcc ar objcopy size` |
| `LIB_NAME`, `-lmcu_mdt_avr` | `build.lib` |
| `ELF_NAME`, `HEX_NAME` | `tree_root: mdt_defaults.elf` (hex = same name) |
| `EXAMPLES_DIR`, `HAL_DIR`, `BUILD_DIR` | `build.example_dir`, `build.hal_dir`, `tree_root: files.build` |
| `-mmcu=$(MCU)` | `build.part_flag` + the node name, lowercased |
| `-Wall -Wextra -Os ...`, `-Wl,--gc-sections ...` | `build.flags.compile`, `build.flags.link` |
| `objcopy -O ihex -R .eeprom` | `build.hex` |
| `F_CPU ?= 16000000UL`, `MDT_USE_UART_IDLE = 0` | trunk `mdt_defaults.f_cpu`, `mdt_defaults.uart_idle` |
| `PORT ?= /dev/ttyACM0` | `tree_root: mdt_defaults.port` |
| `avrdude -c arduino -b 115200` | `flash.tool`, `flash.programmer`, `flash.programmer_baud` |
| `copy_files`, `touch mcu.h` | `dist.headers`, `dist.example`, `dist.empty` |
| `build_info.yaml` keys | `platform`, `mcu`, `port`, `elf` |

## Checks

    python3 -m test.pymdtest unit                           # test_build_system_descriptors.py
    python3 test/firmware/check_avr_parts.py --all          # builds all 135 parts; needs avr-gcc

`test_build_system_descriptors.py` also compares the descriptors with `hal/avr/Makefile`; that
comparison is transitional and goes away when the Makefile does.
