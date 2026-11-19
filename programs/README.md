# `programs/`

Example JANUS firmware, assembled by `python -m janus asm` and run by
`python -m janus run`.

- `hello.s` — writes a counting sequence into data memory and halts
- `two_contexts.s` — two independent timed loops toggling output pins

Planned examples:

- `uart_tx.s`, `uart_rx.s`
- `spi_master.s` — SPI modes 0-3
- `i2c_controller.s`, `i2c_target.s`
- `concurrent.s` — two protocols sharing the chip
- `logic_analyzer.s` — capture pin transitions into data memory
