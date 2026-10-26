# build_system

One declarative description of every target. `generate.py` walks it and writes the files a
build needs; Make still does the building. Only AVR is described so far.

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

## Generator

    python3 build_system/generate.py <part> [key=value ...]
    python3 build_system/generate.py atmega328p f_cpu=8000000 baudrate=38400

The **leaf** is the `key=value` list: any key of the merged `mdt_defaults` (root, then trunk).
Unknown keys, unsupported parts and out-of-range values are errors. It writes, under
`<files.build>/<part>/`:

| File | Holds |
|---|---|
| `build.mk` | Make variables: `CC AR OBJCOPY SIZE`, `CFLAGS LDFLAGS HEX_FLAGS`, source/build dirs, `LIB ELF HEX`, `PORT`, flash and dist data |
| `mdt_target.h` | `PLATFORM_<P>`, `MDT_TARGET_MCU`, `F_CPU`, `MDT_FEATURE_UART_IDLE`, `MDT_UART_BAUDRATE`, `MDT_BUFFER_SIZE`, `MDT_MAX_BREAKPOINTS`, `MDT_MAX_WATCHPOINTS` |

A file is rewritten only when its content changes, so Make can run the generator on every build.

## Checks

    python3 -m test.pymdtest unit                           # test_build_system_{descriptors,generator}.py
    python3 test/firmware/check_avr_parts.py --all          # builds all 135 parts; needs avr-gcc

`test_build_system_descriptors.py` also compares the descriptors with `hal/avr/Makefile`; that
comparison is transitional and goes away when the Makefile does.
