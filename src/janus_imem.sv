// Instruction memory: one IHP RM_IHPSG13_1P_1024x32 single-port SRAM.
//
// The macro samples controls on the rising edge and returns read data in the
// following cycle. `A_DLY` must be tied high and the BIST port is unused.

`default_nettype none

module janus_imem (
    input  logic        clk,
    input  logic        men,
    input  logic        wen,
    input  logic        ren,
    input  logic [9:0]  addr,
    input  logic [31:0] din,
    input  logic [31:0] bm,
    output logic [31:0] dout
);

`ifdef SIM
  janus_sram_1p #(
      .ADDR_W(10),
      .DATA_W(32)
  ) u_sram (
      .clk (clk),
      .men (men),
      .wen (wen),
      .ren (ren),
      .addr(addr),
      .din (din),
      .bm  (bm),
      .dout(dout)
  );
`else
  RM_IHPSG13_1P_1024x32_c2_bm_bist u_sram (
      .A_CLK      (clk),
      .A_MEN      (men),
      .A_WEN      (wen),
      .A_REN      (ren),
      .A_ADDR     (addr),
      .A_DIN      (din),
      .A_DLY      (1'b1),
      .A_DOUT     (dout),
      .A_BM       (bm),
      .A_BIST_CLK (1'b0),
      .A_BIST_EN  (1'b0),
      .A_BIST_MEN (1'b0),
      .A_BIST_WEN (1'b0),
      .A_BIST_REN (1'b0),
      .A_BIST_ADDR(10'd0),
      .A_BIST_DIN (32'd0),
      .A_BIST_BM  (32'd0)
  );
`endif

endmodule

`default_nettype wire
