# build_system

One declarative description of every target. `generate.py` walks it and writes the files a
build needs; Make does the building. AVR, STM32 F0 and STM32 F1 are described.

## The tree

| Level | File | Owns |
|---|---|---|
| **root** | `tree_root.yaml` | the platforms, where the common code is, defaults for every target |
| **trunk** | `<platform>/tree_trunk.yaml` | one platform: toolchain, flags, outputs, commands, platform defaults |
| **branch** | `<platform>/tree_branch_<name>.yaml` | one family: what differs from the trunk (HAL, CPU, linker script...), and its nodes |
| **node** | inside a branch (`nodes:`) | one supported part: what differs from its family (memory sizes) |
| **leaf** | the command line | the user's settings for one build (`F_CPU=`, `BAUDRATE=`, ...) |

A trunk, a branch and a node can each carry the same **sections**. They are merged
root → trunk → branch → node → leaf: **mappings merge key by key, lists are appended, a
single value is replaced**. Replacing a list or a mapping with a value of another shape is an
error. So the trunk holds `-mthumb`, the F0 branch adds `-mcpu=cortex-m0`, and a node adds
only its sizes.

Each file has `version: 1` and `type: tree_root | tree_trunk | tree_branch`. Unknown keys are
errors, so a key can never be written and silently ignored. Paths are relative to the repository
root (the folder that contains `build_system/`).

## Sections

| Section | Keys |
|---|---|
| `mdt_defaults` | `f_cpu uart_idle` (root: `port baudrate buffer_size breakpoints watchpoints elf`); every key can be set from the command line |
| `features` | `uart_idle`: whether the platform can do interrupt mode at all |
| `toolchain` | `prefix` (`avr-`, `arm-none-eabi-`) |
| `memory` | regions by name (`flash`, `ram`): `origin`, `size`, `page` (erase page), `access` (`rx`, `rwx`). Sizes: `16384`, `0x4000`, `16K`, `1M` |
| `defines` | `NAME: value` written to `mdt_target.h` as `#define NAME value`: part facts the C code needs (vector table length, flash banks) |
| `build` | `lib`, `hal_dir` (every `.c` in it goes into the library), `startup` (optional: linked into the program, not the library), `example`, `flags.compile`, `flags.link`, `flags.libs` (after the objects), `outputs` (format → objcopy arguments) |
| `commands` | name → shell command, run as `make MCU=<part> <name>` after a build (`flash`, `erase`, ...) |
| `dist` | `files` copied next to the library for a user project; `makefile`, shipped as `Makefile.example` |
| `host` | `mcu_db`: the part's description file for the PC tool, relative to `pc_tool/mcu_db/` |

Root also has `platform` (the list) and `files` (`src inc build`). A branch also has
`platform`, `branch` and `nodes`.

**Placeholders** in flags, commands and `host.mcu_db`: `{mcu}` (part, lower case), `{node}` (as
written in the branch), `{build_dir}`, `{image}` (`build_dir/<elf stem>`: add `.elf`, `.hex`,
`.bin`, `.map`), `{port}`, and per memory region `{flash_origin}`, `{flash_size}`... An unknown
placeholder is an error; `{ ` with a space (shell grouping) is left alone. Quote a YAML item
that holds a comma or a brace: `"-Wl,--gc-sections"`, `"-mmcu={mcu}"`.

## Generator

    python3 build_system/generate.py <part> [key=value ...]
    python3 build_system/generate.py f030f4 F_CPU=48000000 BAUDRATE=115200

The root `Makefile` runs it on every build (`make MCU=<part> F_CPU=...`) and includes
`build.mk`; the Makefile has no platform knowledge. The leaf is the `key=value` list: any key
of the merged `mdt_defaults`, case-insensitive. Unknown keys, unsupported parts, missing
sections and out-of-range values are errors. It writes, under `<files.build>/<part>/`:

| File | Holds |
|---|---|
| `build.mk` | Make variables: `CC AR OBJCOPY SIZE`, `CFLAGS LDFLAGS LDLIBS`, `HAL_DIR STARTUP EXAMPLE`, `IMAGE LIB`, `OUTPUTS` + `OBJCOPY_FLAGS_<format>`, `COMMANDS` + `CMD_<name>`, `DIST_FILES DIST_MAKEFILE` |
| `mdt_target.h` | `PLATFORM_<P>`, `MDT_TARGET_MCU`, `F_CPU`, `MDT_FEATURE_UART_IDLE`, `MDT_UART_BAUDRATE`, `MDT_BUFFER_SIZE`, `MDT_MAX_BREAKPOINTS`, `MDT_MAX_WATCHPOINTS`, per memory region `MDT_<REGION>_ORIGIN/_SIZE/_PAGE_SIZE`, the `defines`, and `_Static_assert`s. Force-included into every C file |
| `memory.ld` | the linker `MEMORY` regions, when the part describes its memory (included by the core's `linker.ld`) |
| `build_info.yaml` | `platform mcu mcu_db port baudrate uart_idle breakpoints watchpoints elf` and the memory map, for the PC tool |

A file is rewritten only when its content changes, so Make can run the generator on every build.

## Adding things

* **A part of an existing family:** one node line in the branch, plus its row in the platform's
  docs table (`docs/<platform>/info.md`; a test keeps the two equal). AVR nodes are `{}` (sizes
  come from the ATDF); STM32 nodes carry `memory` sizes.
* **A family:** a `tree_branch_<family>.yaml` with what differs from the trunk (see
  `stm32/tree_branch_f0.yaml`), and its nodes.
* **A platform:** a `<platform>/tree_trunk.yaml`, at least one branch, and the name in
  `tree_root.yaml`. Plus the HAL sources, and a parser in the PC tool if its description files
  are a new format. Nothing in the Makefile or the generator changes.

## AVR

Only the parts listed in `avr/tree_branch_*.yaml` are supported (the table in
`docs/avr/info.md`). Nodes carry no data: flash, RAM and EEPROM sizes stay in the ATDF files
(`pc_tool/mcu_db/avr`) and avr-libc.

## STM32

F0 (F030, F070) is in `stm32/tree_branch_f0.yaml` and F1 (F103) in `stm32/tree_branch_f1.yaml`,
with sizes from the datasheets (the tables in `docs/stm32/info.md`). F1 nodes also carry
`defines:` for the density (`MDT_VECTORS_*`, and `FLASH_XL_DENSITY` on XL).

## Checks

    python3 -m test.pymdtest unit                     # test_build_system_{descriptors,generator}.py
    python3 scripts/check_parts.py -j 8               # builds every listed part whose toolchain is installed
