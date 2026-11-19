/*
 * Copyright (c) 2026 Christopher Onyiuke
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

/*
 * JANUS top level: two-context core, instruction and data SRAMs, and the
 * memory-mapped pin block.
 *
 * The 24 protocol pins are numbered as in isa/isa.yaml:
 *   pins 0..7   ui_in[7:0]    inputs only
 *   pins 8..15  uo_out[7:0]   outputs only
 *   pins 16..23 uio[7:0]      bidirectional, direction from PIN_DIR
 *
 * No bootloader is present yet; the core starts at PC 0 in both contexts.
 * Firmware images are loaded by the testbench or, later, by the boot ROM.
 */
module tt_um_coloneltoad_janus (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  logic [31:0] cycle;

  logic [23:0] pin_in_raw;
  logic [23:0] pin_out;
  logic [23:0] pin_dir;
  logic [23:0] pin_edge;

  logic        io_we;
  logic        io_re;
  logic [31:0] io_addr;
  logic [31:0] io_wdata;
  logic [31:0] io_rdata;
  logic        boot_req;

  logic        imem_men;
  logic        imem_ren;
  logic [9:0]  imem_addr;
  logic [31:0] imem_dout;

  logic        dmem_men;
  logic        dmem_wen;
  logic        dmem_ren;
  logic [8:0]  dmem_addr;
  logic [31:0] dmem_din;
  logic [31:0] dmem_bm;
  logic [31:0] dmem_dout;

  logic [1:0]  halted;

  // Free-running cycle counter. Firmware reads it at IO_CYCLE and WAIT uses it.
  always_ff @(posedge clk) begin
    if (!rst_n) cycle <= 32'd0;
    else cycle <= cycle + 32'd1;
  end

  assign pin_in_raw = {uio_in, 8'h00, ui_in};

  janus_core u_core (
      .clk       (clk),
      .rst_n     (rst_n),
      .imem_men  (imem_men),
      .imem_ren  (imem_ren),
      .imem_addr (imem_addr),
      .imem_dout (imem_dout),
      .dmem_men  (dmem_men),
      .dmem_wen  (dmem_wen),
      .dmem_ren  (dmem_ren),
      .dmem_addr (dmem_addr),
      .dmem_din  (dmem_din),
      .dmem_bm   (dmem_bm),
      .dmem_dout (dmem_dout),
      .io_we     (io_we),
      .io_re     (io_re),
      .io_addr   (io_addr),
      .io_wdata  (io_wdata),
      .io_rdata  (io_rdata),
      .pin_edge  (pin_edge),
      .cycle     (cycle),
      .halted    (halted)
  );

  janus_imem u_imem (
      .clk (clk),
      .men (imem_men),
      .wen (1'b0),
      .ren (imem_ren),
      .addr(imem_addr),
      .din (32'd0),
      .bm  (32'hFFFF_FFFF),
      .dout(imem_dout)
  );

  janus_dmem u_dmem (
      .clk (clk),
      .men (dmem_men),
      .wen (dmem_wen),
      .ren (dmem_ren),
      .addr(dmem_addr),
      .din (dmem_din),
      .bm  (dmem_bm),
      .dout(dmem_dout)
  );

  janus_io u_io (
      .clk        (clk),
      .rst_n      (rst_n),
      .pin_in_raw (pin_in_raw),
      .pin_out    (pin_out),
      .pin_dir    (pin_dir),
      .pin_edge   (pin_edge),
      .io_we      (io_we),
      .io_re      (io_re),
      .io_addr    (io_addr),
      .io_wdata   (io_wdata),
      .io_rdata   (io_rdata),
      .cycle      (cycle),
      .ctx_id     (cycle[0]),
      .boot_req   (boot_req)
  );

  assign uo_out  = pin_out[15:8];
  assign uio_out = pin_out[23:16];
  assign uio_oe  = pin_dir[23:16];

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, halted, boot_req, 1'b0};

endmodule

`default_nettype wire
