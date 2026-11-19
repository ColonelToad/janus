// Simulation model of the IHP single-port SRAM, used by RTL cocotb tests.
// Gate-level simulation uses the PDK model instead (see test/sram_model).
// The memory array is deliberately exposed so tests can preload programs.

`default_nettype none

module janus_sram_1p #(
    parameter int ADDR_W = 10,
    parameter int DATA_W = 32
) (
    input  logic                  clk,
    input  logic                  men,
    input  logic                  wen,
    input  logic                  ren,
    input  logic [ADDR_W-1:0]     addr,
    input  logic [DATA_W-1:0]     din,
    input  logic [DATA_W-1:0]     bm,
    output logic [DATA_W-1:0]     dout
);

  logic [DATA_W-1:0] mem [0:(1<<ADDR_W)-1];

  always_ff @(posedge clk) begin
    if (men && wen) begin
      mem[addr] <= (mem[addr] & ~bm) | (din & bm);
    end
    if (men && ren) begin
      dout <= mem[addr];
    end
  end

endmodule

`default_nettype wire
