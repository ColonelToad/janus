// JANUS core: two barrel-interleaved contexts sharing single-port memories.
//
// Context 0 owns even cycles and context 1 odd cycles. In its slot a context
// executes the instruction fetched in the previous slot and starts the fetch
// of its next instruction, so each context retires one instruction every two
// cycles and the pair sustains 1 IPC. Instruction and data memory are separate
// single-port SRAMs, which is what lets a fetch and a load/store share a slot.
//
// Loads write the register file one cycle after issue, while the other context
// owns the slot. The destination context only executes again a cycle later, so
// load-use hazards disappear without interlocks or forwarding.

`default_nettype none

module janus_core (
    input  logic        clk,
    input  logic        rst_n,
    // instruction memory port
    output logic        imem_men,
    output logic        imem_ren,
    output logic [9:0]  imem_addr,
    input  logic [31:0] imem_dout,
    // data memory port
    output logic        dmem_men,
    output logic        dmem_wen,
    output logic        dmem_ren,
    output logic [8:0]  dmem_addr,
    output logic [31:0] dmem_din,
    output logic [31:0] dmem_bm,
    input  logic [31:0] dmem_dout,
    // memory-mapped I/O port
    output logic        io_we,
    output logic        io_re,
    output logic [31:0] io_addr,
    output logic [31:0] io_wdata,
    input  logic [31:0] io_rdata,
    input  logic [23:0] pin_edge,
    // global cycle counter (also visible to firmware at IO_CYCLE)
    input  logic [31:0] cycle,
    // status
    output logic [1:0]  halted
);

  import isa_pkg::*;

  localparam logic [31:0] INPUT_MASK = 32'h00FF_00FF;

  // Per-context architectural state.
  logic [31:0] pc       [0:1];
  logic [31:0] iword    [0:1];
  logic        ivalid   [0:1];
  logic        waiting  [0:1];
  logic        is_halt  [0:1];
  logic [31:0] deadline [0:1];
  logic        dl_en    [0:1];
  logic [31:0] wait_mask[0:1];
  logic [31:0] regs     [0:1][0:15];

  // Return-path tags for the access issued in the previous cycle.
  logic        dly_fetch;
  logic        dly_fetch_ctx;
  logic        dly_load;
  logic        dly_load_ctx;
  logic        dly_load_io;
  logic [3:0]  dly_load_rd;
  logic [1:0]  dly_load_size;
  logic        dly_load_signed;
  logic [1:0]  dly_load_off;

  wire cur = cycle[0];

  // ---------------------------------------------------------------------
  // Execution
  // ---------------------------------------------------------------------
  wire [31:0] instr = iword[cur];

  wire wake = waiting[cur] &&
              (((wait_mask[cur] != 32'd0) && (({8'd0, pin_edge} & wait_mask[cur]) != 32'd0)) ||
               (dl_en[cur] && (cycle >= deadline[cur])));

  wire exec = rst_n && !is_halt[cur] && ivalid[cur] && (!waiting[cur] || wake);

  wire do_fetch = rst_n && !is_halt[cur] && (!ivalid[cur] || exec);

  function automatic logic [31:0] sext16(input logic [15:0] v);
    sext16 = {{16{v[15]}}, v};
  endfunction

  function automatic logic [31:0] sext20(input logic [19:0] v);
    sext20 = {{12{v[19]}}, v};
  endfunction

  function automatic logic [31:0] sext8(input logic [7:0] v);
    sext8 = {{24{v[7]}}, v};
  endfunction

  wire [31:0] imm16 = sext16(instr[15:0]);
  wire [31:0] imm20 = sext20(instr[19:0]);
  wire [4:0]  shamt = instr[12:8];

  logic [31:0] next_pc;
  logic        rf_we;
  logic [3:0]  rf_rd;
  logic [31:0] rf_val;
  logic        start_wait;

  // Data-memory / I/O decode.
  logic [31:0] ea;

  assign ea = regs[cur][instr[19:16]] + imm16;

  wire io_sel = ((ea & 32'hFFFF_FF00) == IO_BASE);

  always @* begin
    next_pc  = pc[cur] + 32'd1;
    rf_we    = 1'b0;
    rf_rd    = 4'd0;
    rf_val   = 32'd0;
    start_wait = 1'b0;

    dmem_men = 1'b0;
    dmem_wen = 1'b0;
    dmem_ren = 1'b0;
    dmem_addr = 9'd0;
    dmem_din  = 32'd0;
    dmem_bm   = 32'd0;

    io_we    = 1'b0;
    io_re    = 1'b0;
    io_addr  = 32'd0;
    io_wdata = 32'd0;

    if (exec) begin
      case (instr[31:24])
        // -- register-register ---------------------------------------------
        OP_ADD: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] + regs[cur][instr[15:12]]; end
        OP_SUB: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] - regs[cur][instr[15:12]]; end
        OP_AND: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] & regs[cur][instr[15:12]]; end
        OP_OR:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] | regs[cur][instr[15:12]]; end
        OP_XOR: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] ^ regs[cur][instr[15:12]]; end
        OP_SLL: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] << regs[cur][instr[15:12]][4:0]; end
        OP_SRL: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] >> regs[cur][instr[15:12]][4:0]; end
        OP_SRA: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = $unsigned($signed(regs[cur][instr[19:16]]) >>> regs[cur][instr[15:12]][4:0]); end
        OP_SLT: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {31'b0, $signed(regs[cur][instr[19:16]]) < $signed(regs[cur][instr[15:12]])}; end
        OP_SLTU: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {31'b0, regs[cur][instr[19:16]] < regs[cur][instr[15:12]]}; end
        OP_NOT: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = ~regs[cur][instr[19:16]]; end

        // -- immediate ------------------------------------------------------
        OP_ADDI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] + imm16; end
        OP_ANDI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] & {16'b0, instr[15:0]}; end
        OP_ORI:   begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] | {16'b0, instr[15:0]}; end
        OP_XORI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] ^ {16'b0, instr[15:0]}; end
        OP_SLTI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {31'b0, $signed(regs[cur][instr[19:16]]) < $signed(imm16)}; end
        OP_SLTIU: begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {31'b0, regs[cur][instr[19:16]] < imm16}; end
        OP_LI:    begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {16'b0, instr[15:0]}; end
        OP_LUI:   begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = {instr[15:0], 16'b0}; end

        OP_SLLI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] << shamt; end
        OP_SRLI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = regs[cur][instr[19:16]] >> shamt; end
        OP_SRAI:  begin rf_we = 1'b1; rf_rd = instr[23:20]; rf_val = $unsigned($signed(regs[cur][instr[19:16]]) >>> shamt); end

        // -- loads ----------------------------------------------------------
        OP_LB, OP_LH, OP_LW, OP_LBU, OP_LHU: begin
          if (io_sel) begin
            io_re  = 1'b1;
            io_addr = ea;
          end else begin
            dmem_men  = 1'b1;
            dmem_ren  = 1'b1;
            dmem_addr = ea[10:2];
          end
        end

        // -- stores ---------------------------------------------------------
        OP_SB: begin
          if (io_sel) begin
            io_we = 1'b1; io_addr = ea; io_wdata = regs[cur][instr[23:20]];
          end else begin
            dmem_men = 1'b1; dmem_wen = 1'b1; dmem_addr = ea[10:2];
            dmem_din = regs[cur][instr[23:20]] << (8 * ea[1:0]);
            dmem_bm  = 32'h0000_00FF << (8 * ea[1:0]);
          end
        end
        OP_SH: begin
          if (io_sel) begin
            io_we = 1'b1; io_addr = ea; io_wdata = regs[cur][instr[23:20]];
          end else begin
            dmem_men = 1'b1; dmem_wen = 1'b1; dmem_addr = ea[10:2];
            dmem_din = regs[cur][instr[23:20]] << (16 * ea[1]);
            dmem_bm  = 32'h0000_FFFF << (16 * ea[1]);
          end
        end
        OP_SW: begin
          if (io_sel) begin
            io_we = 1'b1; io_addr = ea; io_wdata = regs[cur][instr[23:20]];
          end else begin
            dmem_men = 1'b1; dmem_wen = 1'b1; dmem_addr = ea[10:2];
            dmem_din = regs[cur][instr[23:20]];
            dmem_bm  = 32'hFFFF_FFFF;
          end
        end

        // -- control flow ---------------------------------------------------
        OP_BEQ:  if (regs[cur][instr[23:20]] == regs[cur][instr[19:16]]) next_pc = pc[cur] + imm16;
        OP_BNE:  if (regs[cur][instr[23:20]] != regs[cur][instr[19:16]]) next_pc = pc[cur] + imm16;
        OP_BLT:  if ($signed(regs[cur][instr[23:20]]) < $signed(regs[cur][instr[19:16]])) next_pc = pc[cur] + imm16;
        OP_BGE:  if ($signed(regs[cur][instr[23:20]]) >= $signed(regs[cur][instr[19:16]])) next_pc = pc[cur] + imm16;
        OP_BLTU: if (regs[cur][instr[23:20]] < regs[cur][instr[19:16]]) next_pc = pc[cur] + imm16;
        OP_BGEU: if (regs[cur][instr[23:20]] >= regs[cur][instr[19:16]]) next_pc = pc[cur] + imm16;

        OP_JMP:  next_pc = pc[cur] + imm20;
        OP_CALL: begin
          rf_we  = 1'b1;
          rf_rd  = instr[23:20];
          rf_val = pc[cur] + 32'd1;
          next_pc = pc[cur] + imm20;
        end
        OP_JR:   next_pc = regs[cur][instr[19:16]];

        // -- waits ----------------------------------------------------------
        OP_WAITABS: start_wait = 1'b1;
        OP_WAITREL: start_wait = 1'b1;
        OP_WAITPIN: start_wait = 1'b1;

        OP_NOP:  ;
        OP_HALT: ;
        default: ;
      endcase
    end
  end

  // ---------------------------------------------------------------------
  // Memory request
  // ---------------------------------------------------------------------
  assign imem_men  = do_fetch;
  assign imem_ren  = do_fetch;
  assign imem_addr = do_fetch ? (exec ? next_pc[9:0] : pc[cur][9:0]) : 10'd0;

  // ---------------------------------------------------------------------
  // Load alignment
  // ---------------------------------------------------------------------
  wire [31:0] load_raw = dly_load_io ? io_rdata : dmem_dout;

  logic [31:0] load_val;

  always @* begin
    case (dly_load_size)
      2'd1: begin
        load_val = load_raw >> (8 * dly_load_off);
        load_val = dly_load_signed ? sext8(load_val[7:0]) : {24'b0, load_val[7:0]};
      end
      2'd2: begin
        load_val = load_raw >> (16 * dly_load_off[1]);
        load_val = dly_load_signed ? sext16(load_val[15:0]) : {16'b0, load_val[15:0]};
      end
      default: load_val = load_raw;
    endcase
  end

  // ---------------------------------------------------------------------
  // Sequential state
  // ---------------------------------------------------------------------
  integer i, j;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      dly_fetch     <= 1'b0;
      dly_fetch_ctx <= 1'b0;
      dly_load      <= 1'b0;
      dly_load_ctx  <= 1'b0;
      dly_load_io   <= 1'b0;
      dly_load_rd   <= 4'd0;
      dly_load_size <= 2'd3;
      dly_load_signed <= 1'b0;
      dly_load_off  <= 2'd0;
      for (i = 0; i < 2; i = i + 1) begin
        pc[i]        <= 32'd0;
        iword[i]     <= 32'd0;
        ivalid[i]    <= 1'b0;
        waiting[i]   <= 1'b0;
        is_halt[i]   <= 1'b0;
        deadline[i]  <= 32'd0;
        dl_en[i]     <= 1'b0;
        wait_mask[i] <= 32'd0;
        for (j = 0; j < 16; j = j + 1) begin
          regs[i][j] <= 32'd0;
        end
      end
    end else begin
      // Tag the access issued this cycle for the return path.
      dly_fetch     <= do_fetch;
      dly_fetch_ctx <= cur;
      dly_load      <= exec && (instr[31:24] == OP_LB || instr[31:24] == OP_LH ||
                                instr[31:24] == OP_LW || instr[31:24] == OP_LBU ||
                                instr[31:24] == OP_LHU);
      dly_load_ctx  <= cur;
      dly_load_io   <= io_sel;
      dly_load_rd   <= instr[23:20];
      dly_load_size <= (instr[31:24] == OP_LB || instr[31:24] == OP_LBU) ? 2'd1 :
                       (instr[31:24] == OP_LH || instr[31:24] == OP_LHU) ? 2'd2 : 2'd3;
      dly_load_signed <= (instr[31:24] == OP_LB) || (instr[31:24] == OP_LH) ||
                         (instr[31:24] == OP_LW);
      dly_load_off  <= ea[1:0];

      // Return path: instruction fetch, then load writeback. Both belong to
      // the context that owned the previous slot, so they never collide with
      // the context executing now.
      if (dly_fetch) begin
        iword[dly_fetch_ctx]  <= imem_dout;
        ivalid[dly_fetch_ctx] <= 1'b1;
      end

      if (dly_load && (dly_load_rd != 4'd0)) begin
        regs[dly_load_ctx][dly_load_rd] <= load_val;
      end

      if (exec) begin
        ivalid[cur] <= 1'b0;
        pc[cur]     <= next_pc;

        if (rf_we && (rf_rd != 4'd0)) begin
          regs[cur][rf_rd] <= rf_val;
        end

        case (instr[31:24])
          OP_WAITABS: begin
            waiting[cur]    <= 1'b1;
            dl_en[cur]      <= 1'b1;
            deadline[cur]   <= regs[cur][instr[19:16]];
            wait_mask[cur]  <= 32'd0;
          end
          OP_WAITREL: begin
            waiting[cur]    <= 1'b1;
            dl_en[cur]      <= 1'b1;
            deadline[cur]   <= cycle + regs[cur][instr[19:16]];
            wait_mask[cur]  <= 32'd0;
          end
          OP_WAITPIN: begin
            waiting[cur]    <= 1'b1;
            dl_en[cur]      <= regs[cur][instr[15:12]] != 32'd0;
            deadline[cur]   <= cycle + regs[cur][instr[15:12]];
            wait_mask[cur]  <= regs[cur][instr[19:16]] & INPUT_MASK;
          end
          OP_HALT: begin
            is_halt[cur] <= 1'b1;
          end
          default: waiting[cur] <= 1'b0;
        endcase
      end else if (wake) begin
        waiting[cur] <= 1'b0;
      end
    end
  end

  assign halted = {is_halt[1], is_halt[0]};

  // Simulation-only observation port. Synthesis never sees this.
`ifdef SIM
  logic [63:0]   dbg_pc;
  logic [1023:0] dbg_regs;
  logic [1:0]    dbg_ivalid;
  logic [1:0]    dbg_waiting;
  logic [1:0]    dbg_halted;

  assign dbg_pc      = {pc[1], pc[0]};
  assign dbg_ivalid  = {ivalid[1], ivalid[0]};
  assign dbg_waiting = {waiting[1], waiting[0]};
  assign dbg_halted  = {is_halt[1], is_halt[0]};

  genvar gc, gr;
  generate
    for (gc = 0; gc < 2; gc = gc + 1) begin : g_ctx
      for (gr = 0; gr < 16; gr = gr + 1) begin : g_reg
        assign dbg_regs[gc*512 + gr*32+:32] = regs[gc][gr];
      end
    end
  endgenerate
`endif

endmodule

`default_nettype wire
