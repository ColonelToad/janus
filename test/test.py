# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


@cocotb.test()
async def test_project(dut):
    dut._log.info("Start")

    # 50 MHz target clock
    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1

    # Placeholder top passes ui_in through to uo_out.
    dut._log.info("Check placeholder passthrough")
    dut.ui_in.value = 0xA5
    dut.uio_in.value = 0x3C
    await ClockCycles(dut.clk, 1)

    assert dut.uo_out.value == 0xA5
    assert dut.uio_oe.value == 0
