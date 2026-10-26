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
`build` (`lib hal_dir example_dir part_flag flags.compile flags.link hex`), `flash` (a command
template with `{mcu} {port} {hex}`), `dist`.

`<platform>/tree_branch_<name>.yaml`: `platform`, `branch`, `nodes`.

Quote any flag that contains a comma (`"-Wl,--gc-sections"`): in YAML a bare comma splits the item.

## AVR

Only the parts listed in `avr/tree_branch_*.yaml` are supported (80: the table in
`docs/avr/info.md`). Nodes carry no data: flash, RAM and EEPROM sizes stay in the ATDF files
(`pc_tool/mcu_db/avr`), so there is one source for them.

## Generator

    python3 build_system/generate.py <part> [key=value ...]
    python3 build_system/generate.py atmega328p F_CPU=8000000 BAUDRATE=38400

The root `Makefile` runs it on every build (`make MCU=<part> F_CPU=...`) and includes
`build.mk`; the Makefile has no platform knowledge. The **leaf** is the `key=value` list: any key
of the merged `mdt_defaults` (root, then trunk), case-insensitive.
Unknown keys, unsupported parts and out-of-range values are errors. It writes, under
`<files.build>/<part>/`:

| File | Holds |
|---|---|
| `build.mk` | Make variables: `CC AR OBJCOPY SIZE`, `CFLAGS LDFLAGS HEX_FLAGS`, source/build dirs, `LIB ELF HEX`, `FLASH_CMD`, dist files |
| `mdt_target.h` | `PLATFORM_<P>`, `MDT_TARGET_MCU`, `F_CPU`, `MDT_FEATURE_UART_IDLE`, `MDT_UART_BAUDRATE`, `MDT_BUFFER_SIZE`, `MDT_MAX_BREAKPOINTS`, `MDT_MAX_WATCHPOINTS`, and `_Static_assert`s on them. Force-included into every C file; it replaces `mcu_mdt_config.h` |
| `build_info.yaml` | `platform mcu port baudrate elf`, for the PC tool |

A file is rewritten only when its content changes, so Make can run the generator on every build.

## Checks

    python3 -m test.pymdtest unit                           # test_build_system_{descriptors,generator}.py
    python3 test/firmware/check_avr_parts.py                # builds the 80 listed parts; needs avr-gcc
