/*
 * Copyright (c) 2026 Christopher Onyiuke
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

/*
 * JANUS top level.
 *
 * Placeholder bring-up: pass the dedicated inputs through to the outputs so
 * the Tiny Tapeout harness stays green. The core, memory and peripherals
 * replace this logic in the next milestone.
 */
module tt_um_coloneltoad_janus (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  assign uo_out  = ui_in;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, clk, rst_n, uio_in, 1'b0};

endmodule
