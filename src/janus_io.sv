// Pin registers, edge detection and memory-mapped I/O for JANUS.
//
// The core accesses this block through a word-addressed window. Reads are
// registered to match the one-cycle latency of the data SRAM, so the core's
// load-writeback stage treats both sources identically.

`default_nettype none

module janus_io (
    input  logic        clk,
    input  logic        rst_n,
    // raw pin inputs, already mapped to the 24-pin numbering
    input  logic [23:0] pin_in_raw,
    output logic [23:0] pin_out,
    output logic [23:0] pin_dir,
    output logic [23:0] pin_edge,
    // core memory port
    input  logic        io_we,
    input  logic        io_re,
    input  logic [31:0] io_addr,
    input  logic [31:0] io_wdata,
    output logic [31:0] io_rdata,
    // global state
    input  logic [31:0] cycle,
    input  logic        ctx_id,
    // hand-back to the bootloader
    output logic        boot_req
);

  // Constants are written as isa_pkg::NAME rather than imported: the Yosys in
  // the Tiny Tapeout flow does not parse `import isa_pkg::*;`.

  localparam logic [23:0] OUTPUT_MASK = isa_pkg::PIN_OUTPUT_MASK;
  localparam logic [23:0] BIDIR_MASK  = isa_pkg::PIN_BIDIR_MASK;
  localparam logic [31:0] BOOT_MAGIC  = 32'h4A4E5553;

  // Two-flop synchroniser, plus one more stage for edge detection.
  logic [23:0] sync0, sync1, sync2;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      sync0 <= 24'b0;
      sync1 <= 24'b0;
      sync2 <= 24'b0;
    end else begin
      sync0 <= pin_in_raw;
      sync1 <= sync0;
      sync2 <= sync1;
    end
  end

  wire [23:0] edge_pulse = sync1 ^ sync2;

  logic [23:0] pin_out_q;
  logic [23:0] pin_dir_q;
  logic [23:0] pin_edge_q;
  logic [31:0] io_rdata_q;
  logic        boot_req_q;

  logic [23:0] edge_next;

  always @* begin
    edge_next = pin_edge_q | edge_pulse;
    if (io_we && (io_addr == isa_pkg::IO_PIN_EDGE)) begin
      edge_next &= ~io_wdata[23:0];
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      pin_out_q  <= 24'b0;
      pin_dir_q  <= 24'b0;
      pin_edge_q <= 24'b0;
      boot_req_q <= 1'b0;
    end else begin
      pin_edge_q <= edge_next;

      if (io_we) begin
        case (io_addr)
          isa_pkg::IO_PIN_OUT: pin_out_q <= io_wdata[23:0] & OUTPUT_MASK;
          isa_pkg::IO_PIN_DIR: pin_dir_q <= io_wdata[23:0] & BIDIR_MASK;
          isa_pkg::IO_PIN_SET: pin_out_q <= pin_out_q | (io_wdata[23:0] & OUTPUT_MASK);
          isa_pkg::IO_PIN_CLR: pin_out_q <= pin_out_q & ~(io_wdata[23:0] & OUTPUT_MASK);
          isa_pkg::IO_PIN_XOR: pin_out_q <= pin_out_q ^ (io_wdata[23:0] & OUTPUT_MASK);
          isa_pkg::IO_BOOT_REQ: begin
            if (io_wdata == BOOT_MAGIC) boot_req_q <= 1'b1;
          end
          default: ;
        endcase
      end
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      io_rdata_q <= 32'b0;
    end else if (io_re) begin
      case (io_addr)
        isa_pkg::IO_CYCLE:    io_rdata_q <= cycle;
        isa_pkg::IO_PIN_IN:   io_rdata_q <= {8'b0, sync1[23:16], 8'b0, sync1[7:0]};
        isa_pkg::IO_PIN_OUT:  io_rdata_q <= {8'b0, pin_out_q};
        isa_pkg::IO_PIN_DIR:  io_rdata_q <= {8'b0, pin_dir_q};
        isa_pkg::IO_PIN_EDGE: io_rdata_q <= {8'b0, pin_edge_q};
        isa_pkg::IO_CTX_ID:   io_rdata_q <= {31'b0, ctx_id};
        default:     io_rdata_q <= 32'b0;
      endcase
    end
  end

  assign pin_out  = pin_out_q;
  assign pin_dir  = pin_dir_q;
  assign pin_edge = pin_edge_q;
  assign io_rdata = io_rdata_q;
  assign boot_req = boot_req_q;

endmodule

`default_nettype wire
