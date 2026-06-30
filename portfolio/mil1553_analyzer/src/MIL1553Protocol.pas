unit MIL1553Protocol;

{
  MIL1553Protocol.pas — MIL-STD-1553B protocol decoder and simulator.

  Provides:
    TMil1553Decoder  — decodes raw word streams into TMil1553Message records
    TMil1553Simulator — generates realistic bus traffic for testing / demo

  Architecture:
    The decoder is a state machine. Each call to ProcessWord() feeds one
    16-bit word (with its sync type) and updates internal state.  When a
    complete message is assembled it fires OnMessage.

  Author : Stanislav Perfilyev
  License: MIT
}

{$MODE DELPHI}

interface

uses
  SysUtils, Classes, Contnrs, MIL1553Types;

type
  // ── Decoder state machine ──────────────────────────────────────────────────

  TDecoderState = (
    dsIdle,             // Waiting for first command word
    dsAwaitData,        // BC→RT or RT→RT: expecting N data words
    dsAwaitStatus,      // Expecting status word from RT
    dsAwaitStatus2,     // RT→RT: expecting second status word
    dsAwaitModeData     // Mode code with single data word
  );

  TMessageEvent  = procedure(const Msg: TMil1553Message) of object;
  TErrorEvent    = procedure(const Msg: string) of object;

  /// Stateful MIL-STD-1553B decoder.
  /// Feed words one at a time via ProcessWord(); complete messages fire OnMessage.
  TMil1553Decoder = class
  private
    FState        : TDecoderState;
    FBus          : Char;
    FSeqCounter   : UInt64;
    FCurrentMsg   : TMil1553Message;
    FExpectedWords: Integer;       // data words still expected
    FStats        : TMil1553Stats;
    FOnMessage    : TMessageEvent;
    FOnError      : TErrorEvent;

    procedure ResetState;
    procedure FinalizeMessage;
    procedure EmitError(const Msg: string);
    function  DetermineMessageType(const CW: TMil1553CommandWord): TMil1553MessageType;
  public
    constructor Create(BusChannel: Char = 'A');

    /// Feed one decoded word into the state machine.
    /// SyncType distinguishes command/status words from data words.
    procedure ProcessWord(
      Word      : TMil1553Word;
      SyncType  : TMil1553SyncType;
      Timestamp : TDateTime;
      Parity    : Boolean   // true = parity OK
    );

    /// Signal a response timeout (no word received within 14 µs).
    procedure SignalTimeout;

    /// Reset decoder state (call on bus error or session restart).
    procedure Reset;

    property Stats     : TMil1553Stats  read FStats;
    property OnMessage : TMessageEvent  read FOnMessage  write FOnMessage;
    property OnError   : TErrorEvent    read FOnError    write FOnError;
  end;

  // ── Bus Simulator ──────────────────────────────────────────────────────────

  TSimScenario = (
    ssNormal,         // Healthy bus: mix of BC-RT, RT-BC, RT-RT, mode codes
    ssHighError,      // 15% error injection
    ssFlightData,     // Avionics-style data: IMU, NAV, FUEL sub-systems
    ssModeCodeSweep   // Sweep through all mode codes
  );

  /// Generates realistic MIL-STD-1553B message sequences for demo / testing.
  TMil1553Simulator = class
  private
    FScenario  : TSimScenario;
    FSeqNo     : UInt64;
    FBusChannel: Char;
    FRandom    : TRandom;   // deterministic seed for reproducibility

    function MakeCommandWord(RT, SA, WC: Byte; Transmit: Boolean): TMil1553CommandWord;
    function MakeStatusWord(RT: Byte; Healthy: Boolean = True): TMil1553StatusWord;
    function MakeDataWord(Value: Word = 0): TMil1553Word;
    function NextTimestamp(BaseTime: TDateTime; MsgIndex: Integer): TDateTime;

    function GenBCtoRT(BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
    function GenRTtoBC(BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
    function GenRTtoRT(BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
    function GenModeCode(BaseTime: TDateTime; MsgIdx: Int; MC: TMil1553ModeCode): TMil1553Message;
    procedure InjectError(var Msg: TMil1553Message);
  public
    constructor Create(Scenario: TSimScenario = ssNormal; BusCh: Char = 'A');

    /// Generate Count messages starting at BaseTime.
    procedure Generate(
      BaseTime   : TDateTime;
      Count      : Integer;
      Dest       : TObjectList   // receives TMil1553Message (cloned onto heap)
    );

    /// Generate a single message and return it (caller must free if heap-allocated).
    function GenerateOne(BaseTime: TDateTime; MsgIndex: Integer): TMil1553Message;

    property Scenario   : TSimScenario  read FScenario   write FScenario;
    property BusChannel : Char          read FBusChannel write FBusChannel;
  end;

  // ── Export helpers ─────────────────────────────────────────────────────────

  /// Writes messages to a CSV file (UTF-8, semicolon-delimited).
  procedure ExportToCSV(Messages: TList; const FilePath: string);

  /// Writes messages to plain-text log (human-readable, one message per line).
  procedure ExportToLog(Messages: TList; const FilePath: string);

implementation

uses
  DateUtils, Math;

// ── TMil1553Decoder ────────────────────────────────────────────────────────

constructor TMil1553Decoder.Create(BusChannel: Char);
begin
  inherited Create;
  FBus := BusChannel;
  FStats.Reset;
  Reset;
end;

procedure TMil1553Decoder.Reset;
begin
  ResetState;
  FSeqCounter := 0;
end;

procedure TMil1553Decoder.ResetState;
begin
  FState         := dsIdle;
  FExpectedWords := 0;
  FillChar(FCurrentMsg, SizeOf(FCurrentMsg), 0);
end;

procedure TMil1553Decoder.EmitError(const Msg: string);
begin
  if Assigned(FOnError) then
    FOnError(Msg);
end;

function TMil1553Decoder.DetermineMessageType(
  const CW: TMil1553CommandWord): TMil1553MessageType;
begin
  if CW.RTAddress = MIL1553_MAX_RT then
    Result := mtBroadcast
  else if CW.IsModeCode then
    Result := mtModeCode
  else if CW.TransmitBit then
    Result := mtRTtoBC
  else
    Result := mtBCtoRT;
end;

procedure TMil1553Decoder.ProcessWord(
  Word      : TMil1553Word;
  SyncType  : TMil1553SyncType;
  Timestamp : TDateTime;
  Parity    : Boolean);
var
  CW : TMil1553CommandWord;
  SW : TMil1553StatusWord;
  WC : Byte;
begin
  case FState of
    // ── Waiting for a command word ──────────────────────────────────────────
    dsIdle:
    begin
      if SyncType <> stCommand then
      begin
        EmitError('Expected command-sync at bus idle; got data-sync — discarding');
        Exit;
      end;

      // Start new message
      Inc(FSeqCounter);
      FillChar(FCurrentMsg, SizeOf(FCurrentMsg), 0);
      FCurrentMsg.SequenceNo := FSeqCounter;
      FCurrentMsg.Timestamp  := Timestamp;
      FCurrentMsg.BusChannel := FBus;

      CW.Raw := Word;
      FCurrentMsg.Command1 := CW;

      if not Parity then
        FCurrentMsg.ParityError := True;

      FCurrentMsg.MessageType := DetermineMessageType(CW);

      case FCurrentMsg.MessageType of
        mtBCtoRT, mtBroadcast:
        begin
          WC := CW.WordCount;
          if WC = 0 then WC := 32;
          FExpectedWords := WC;
          FCurrentMsg.DataCount := 0;
          FState := dsAwaitData;
        end;

        mtRTtoBC:
        begin
          WC := CW.WordCount;
          if WC = 0 then WC := 32;
          FExpectedWords := WC;
          FCurrentMsg.DataCount := 0;
          FState := dsAwaitStatus;
        end;

        mtModeCode:
        begin
          // Mode code with transmit bit = RT sends 1 data word after status
          if CW.TransmitBit then
            FState := dsAwaitStatus
          else
          begin
            // Receive mode code: optional 1 data word (if mode code requires it)
            // For simplicity treat all as no-data; data word handled in dsAwaitStatus
            FState := dsAwaitStatus;
          end;
          FExpectedWords := 0;
        end;
      else
        // Unknown / RT-to-RT needs special handling (two command words)
        // Simplified: treat as BC→RT
        FState := dsAwaitData;
        FExpectedWords := 1;
      end;
    end;

    // ── Collecting data words (BC→RT direction) ────────────────────────────
    dsAwaitData:
    begin
      if SyncType <> stData then
      begin
        EmitError(Format('Expected data-sync, got command-sync at word %d/%d — message aborted',
          [FCurrentMsg.DataCount + 1, FExpectedWords]));
        FCurrentMsg.SyncError := True;
        FinalizeMessage;
        // Re-process as start of new message
        ProcessWord(Word, SyncType, Timestamp, Parity);
        Exit;
      end;

      if not Parity then
        FCurrentMsg.ParityError := True;

      FCurrentMsg.DataWords[FCurrentMsg.DataCount] := Word;
      Inc(FCurrentMsg.DataCount);
      Dec(FExpectedWords);

      if FExpectedWords = 0 then
        FState := dsAwaitStatus;
    end;

    // ── Expecting status word from RT ──────────────────────────────────────
    dsAwaitStatus:
    begin
      if SyncType <> stCommand then
      begin
        // Data word where status expected: could be RT-TX data
        if FCurrentMsg.MessageType in [mtRTtoBC, mtModeCode] then
        begin
          if not Parity then
            FCurrentMsg.ParityError := True;
          if FCurrentMsg.DataCount < MIL1553_MAX_DATA_WORDS then
          begin
            FCurrentMsg.DataWords[FCurrentMsg.DataCount] := Word;
            Inc(FCurrentMsg.DataCount);
          end;
          // Keep waiting for status
          Exit;
        end;
        EmitError('Expected status-sync from RT; got data-sync');
        FCurrentMsg.SyncError := True;
        FinalizeMessage;
        Exit;
      end;

      if not Parity then
        FCurrentMsg.ParityError := True;

      SW.Raw := Word;
      FCurrentMsg.Status1 := SW;
      FinalizeMessage;
    end;
  end;
end;

procedure TMil1553Decoder.SignalTimeout;
begin
  if FState <> dsIdle then
  begin
    FCurrentMsg.ResponseTimeout := True;
    EmitError(Format('RT response timeout (seq=%d)', [FCurrentMsg.SequenceNo]));
    FinalizeMessage;
  end;
end;

procedure TMil1553Decoder.FinalizeMessage;
begin
  Inc(FStats.TotalMessages);

  if FCurrentMsg.IsValid then
    Inc(FStats.ValidMessages)
  else
  begin
    Inc(FStats.ErrorMessages);
    if FCurrentMsg.ParityError     then Inc(FStats.ParityErrors);
    if FCurrentMsg.ResponseTimeout then Inc(FStats.TimeoutErrors);
  end;

  case FCurrentMsg.MessageType of
    mtBCtoRT:    Inc(FStats.BCtoRTCount);
    mtRTtoBC:    Inc(FStats.RTtoBCCount);
    mtRTtoRT:    Inc(FStats.RTtoRTCount);
    mtModeCode:  Inc(FStats.ModeCodeCount);
    mtBroadcast: Inc(FStats.BroadcastCount);
  end;

  if Assigned(FOnMessage) then
    FOnMessage(FCurrentMsg);

  ResetState;
end;

// ── TMil1553Simulator ──────────────────────────────────────────────────────

constructor TMil1553Simulator.Create(Scenario: TSimScenario; BusCh: Char);
begin
  inherited Create;
  FScenario   := Scenario;
  FBusChannel := BusCh;
  FSeqNo      := 0;
  // Fixed seed for reproducibility in tests
  FRandom.Init(42);
end;

function TMil1553Simulator.MakeCommandWord(
  RT, SA, WC: Byte; Transmit: Boolean): TMil1553CommandWord;
var
  Raw: Word;
begin
  Raw := (Word(RT and $1F) shl 11)
       or (Word(Ord(Transmit)) shl 10)
       or (Word(SA and $1F) shl 5)
       or  Word(WC and $1F);
  Result.Raw := Raw;
end;

function TMil1553Simulator.MakeStatusWord(
  RT: Byte; Healthy: Boolean): TMil1553StatusWord;
begin
  Result.Raw := Word(RT and $1F) shl 11;
  if not Healthy then
    Result.Raw := Result.Raw or $0400; // MessageError bit
end;

function TMil1553Simulator.MakeDataWord(Value: Word): TMil1553Word;
begin
  Result := Value;
end;

function TMil1553Simulator.NextTimestamp(
  BaseTime: TDateTime; MsgIndex: Integer): TDateTime;
const
  // Average inter-message gap ~100 µs at 1 Mbit/s with typical bus loading
  GAP_US = 100;
begin
  Result := BaseTime + (MsgIndex * GAP_US / (SecsPerDay * 1_000_000));
end;

function TMil1553Simulator.GenBCtoRT(
  BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
var
  RT, SA, WC, I: Integer;
begin
  FillChar(Result, SizeOf(Result), 0);
  Inc(FSeqNo);
  Result.SequenceNo := FSeqNo;
  Result.Timestamp  := NextTimestamp(BaseTime, MsgIdx);
  Result.BusChannel := FBusChannel;
  Result.MessageType := mtBCtoRT;

  RT := 1 + (MsgIdx mod 8);   // RT 1..8
  SA := 1 + (MsgIdx mod 15);  // SA 1..15
  WC := 1 + (MsgIdx mod 4);   // 1..4 words

  Result.Command1 := MakeCommandWord(RT, SA, WC, False);  // Receive
  Result.Status1  := MakeStatusWord(RT, True);
  Result.DataCount := WC;
  for I := 0 to WC - 1 do
    Result.DataWords[I] := MakeDataWord(Word($1000 + MsgIdx * WC + I));
end;

function TMil1553Simulator.GenRTtoBC(
  BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
var
  RT, SA, WC, I: Integer;
begin
  FillChar(Result, SizeOf(Result), 0);
  Inc(FSeqNo);
  Result.SequenceNo  := FSeqNo;
  Result.Timestamp   := NextTimestamp(BaseTime, MsgIdx);
  Result.BusChannel  := FBusChannel;
  Result.MessageType := mtRTtoBC;

  RT := 2 + (MsgIdx mod 6);
  SA := 2 + (MsgIdx mod 12);
  WC := 1 + (MsgIdx mod 8);

  Result.Command1  := MakeCommandWord(RT, SA, WC, True);   // Transmit
  Result.Status1   := MakeStatusWord(RT, True);
  Result.DataCount := WC;
  for I := 0 to WC - 1 do
    Result.DataWords[I] := MakeDataWord(Word($2000 + MsgIdx * WC + I));
end;

function TMil1553Simulator.GenRTtoRT(
  BaseTime: TDateTime; MsgIdx: Int): TMil1553Message;
var
  RTsrc, RTdst, SA, WC, I: Integer;
begin
  FillChar(Result, SizeOf(Result), 0);
  Inc(FSeqNo);
  Result.SequenceNo  := FSeqNo;
  Result.Timestamp   := NextTimestamp(BaseTime, MsgIdx);
  Result.BusChannel  := FBusChannel;
  Result.MessageType := mtRTtoRT;

  RTsrc := 3 + (MsgIdx mod 5);
  RTdst := 10 + (MsgIdx mod 5);
  SA    := 3 + (MsgIdx mod 10);
  WC    := 2 + (MsgIdx mod 3);

  Result.Command1  := MakeCommandWord(RTdst, SA, WC, False);  // Receive cmd (dst)
  Result.Command2  := MakeCommandWord(RTsrc, SA, WC, True);   // Transmit cmd (src)
  Result.Status1   := MakeStatusWord(RTsrc, True);
  Result.Status2   := MakeStatusWord(RTdst, True);
  Result.DataCount := WC;
  for I := 0 to WC - 1 do
    Result.DataWords[I] := MakeDataWord(Word($3000 + MsgIdx * WC + I));
end;

function TMil1553Simulator.GenModeCode(
  BaseTime: TDateTime; MsgIdx: Int; MC: TMil1553ModeCode): TMil1553Message;
var
  RT: Integer;
begin
  FillChar(Result, SizeOf(Result), 0);
  Inc(FSeqNo);
  Result.SequenceNo  := FSeqNo;
  Result.Timestamp   := NextTimestamp(BaseTime, MsgIdx);
  Result.BusChannel  := FBusChannel;
  Result.MessageType := mtModeCode;

  RT := 1 + (MsgIdx mod 10);
  // Mode code: SA=0, WC=mode code value
  Result.Command1 := MakeCommandWord(RT, 0, Ord(MC), False);
  Result.Status1  := MakeStatusWord(RT, True);
  Result.DataCount := 0;
end;

procedure TMil1553Simulator.InjectError(var Msg: TMil1553Message);
var
  R: Integer;
begin
  R := FRandom.Next(3);
  case R of
    0: Msg.ParityError     := True;
    1: Msg.ResponseTimeout := True;
    2: Msg.ManchesterError := True;
  end;
end;

function TMil1553Simulator.GenerateOne(
  BaseTime: TDateTime; MsgIndex: Integer): TMil1553Message;
const
  ModeCodeList: array[0..5] of TMil1553ModeCode = (
    mcSynchronize, mcInitiateSelfTest, mcTransmitStatusWord,
    mcResetRemoteTerminal, mcTransmitBITWord, mcTransmitVectorWord
  );
var
  Roll: Integer;
begin
  case FScenario of
    ssNormal:
    begin
      Roll := MsgIndex mod 10;
      case Roll of
        0..4: Result := GenBCtoRT(BaseTime, MsgIndex);
        5..7: Result := GenRTtoBC(BaseTime, MsgIndex);
        8:    Result := GenRTtoRT(BaseTime, MsgIndex);
      else
        Result := GenModeCode(BaseTime, MsgIndex,
          ModeCodeList[MsgIndex mod Length(ModeCodeList)]);
      end;
    end;

    ssHighError:
    begin
      Roll := MsgIndex mod 3;
      case Roll of
        0: Result := GenBCtoRT(BaseTime, MsgIndex);
        1: Result := GenRTtoBC(BaseTime, MsgIndex);
      else
        Result := GenRTtoRT(BaseTime, MsgIndex);
      end;
      // 33% chance of error
      if (MsgIndex mod 3) = 0 then
        InjectError(Result);
    end;

    ssFlightData:
    begin
      // Simulate: IMU (RT1), NAV (RT2), FUEL (RT3), DISPLAY (RT4)
      Roll := MsgIndex mod 4;
      case Roll of
        0: // IMU → BC (accelerometer data, 8 words)
        begin
          Result.SequenceNo  := FSeqNo + 1;
          Result.Timestamp   := NextTimestamp(BaseTime, MsgIndex);
          Result.BusChannel  := FBusChannel;
          Result.MessageType := mtRTtoBC;
          Result.Command1    := MakeCommandWord(1, 1, 8, True);
          Result.Status1     := MakeStatusWord(1, True);
          Result.DataCount   := 8;
          // Simulated IMU readings (fixed-point Q8.8)
          Result.DataWords[0] := $0100; // AccelX = 1.0 g
          Result.DataWords[1] := $0000; // AccelY = 0.0 g
          Result.DataWords[2] := $FF00; // AccelZ = -1.0 g (gravity)
          Result.DataWords[3] := $0010; // GyroX
          Result.DataWords[4] := $0005; // GyroY
          Result.DataWords[5] := $0002; // GyroZ
          Result.DataWords[6] := Word(MsgIndex and $FFFF); // Counter
          Result.DataWords[7] := $A5A5; // Checksum pattern
        end;
        1: // BC → NAV (waypoint update, 4 words)
        begin
          Result := GenBCtoRT(BaseTime, MsgIndex);
          Result.Command1 := MakeCommandWord(2, 5, 4, False);
        end;
        2: // BC → FUEL (pump command, 2 words)
        begin
          Result := GenBCtoRT(BaseTime, MsgIndex);
          Result.Command1 := MakeCommandWord(3, 2, 2, False);
          Result.DataWords[0] := $0001; // pump on
          Result.DataWords[1] := $0064; // flow rate 100%
          Result.DataCount := 2;
        end;
        3: // BC → DISPLAY (refresh, 16 words)
        begin
          Result := GenBCtoRT(BaseTime, MsgIndex);
          Result.Command1 := MakeCommandWord(4, 1, 16, False);
          Result.DataCount := 16;
          Inc(FSeqNo);
        end;
      end;
      Inc(FSeqNo);
      Result.SequenceNo := FSeqNo;
    end;

    ssModeCodeSweep:
    begin
      Result := GenModeCode(BaseTime, MsgIndex,
        ModeCodeList[MsgIndex mod Length(ModeCodeList)]);
    end;
  else
    Result := GenBCtoRT(BaseTime, MsgIndex);
  end;
end;

procedure TMil1553Simulator.Generate(
  BaseTime : TDateTime;
  Count    : Integer;
  Dest     : TObjectList);
var
  I   : Integer;
  Msg : PMil1553Message;
begin
  for I := 0 to Count - 1 do
  begin
    New(Msg);
    Msg^ := GenerateOne(BaseTime, I);
    Dest.Add(Msg);
  end;
end;

// ── Export helpers ─────────────────────────────────────────────────────────

procedure ExportToCSV(Messages: TList; const FilePath: string);
var
  F   : TextFile;
  I   : Integer;
  Msg : PMil1553Message;
begin
  AssignFile(F, FilePath);
  Rewrite(F);
  try
    WriteLn(F, 'Seq;Timestamp;Bus;Type;RT;SA;WC;DataCount;Valid;Errors;Data');
    for I := 0 to Messages.Count - 1 do
    begin
      Msg := PMil1553Message(Messages[I]);
      Write(F,
        Msg^.SequenceNo, ';',
        FormatTimestamp(Msg^.Timestamp), ';',
        Msg^.BusChannel, ';',
        Msg^.MessageTypeStr, ';',
        Msg^.Command1.RTAddress, ';',
        Msg^.Command1.SubAddress, ';',
        Msg^.Command1.WordCount, ';',
        Msg^.DataCount, ';',
        BoolToStr(Msg^.IsValid, 'OK', 'ERR'), ';',
        Msg^.ErrorSummary
      );
      // Append hex data words
      if Msg^.DataCount > 0 then
      begin
        Write(F, ';');
        var DI: Integer;
        for DI := 0 to Msg^.DataCount - 1 do
        begin
          if DI > 0 then Write(F, ' ');
          Write(F, IntToHex(Msg^.DataWords[DI], 4));
        end;
      end
      else
        Write(F, ';');
      WriteLn(F);
    end;
  finally
    CloseFile(F);
  end;
end;

procedure ExportToLog(Messages: TList; const FilePath: string);
const
  SEP = '────────────────────────────────────────────────────────────';
var
  F   : TextFile;
  I, J: Integer;
  Msg : PMil1553Message;
begin
  AssignFile(F, FilePath);
  Rewrite(F);
  try
    WriteLn(F, 'MIL-STD-1553B Protocol Analyzer — Message Log');
    WriteLn(F, 'Generated: ', FormatTimestamp(Now));
    WriteLn(F, SEP);

    for I := 0 to Messages.Count - 1 do
    begin
      Msg := PMil1553Message(Messages[I]);
      WriteLn(F, Format('#%-6d  %s  Bus-%s  %s',
        [Msg^.SequenceNo, FormatTimestamp(Msg^.Timestamp),
         Msg^.BusChannel, Msg^.MessageTypeStr]));
      WriteLn(F, '  ', Msg^.Command1.ToString);
      if Msg^.Status1.Raw <> 0 then
        WriteLn(F, '  ', Msg^.Status1.ToString);
      if Msg^.DataCount > 0 then
      begin
        Write(F, '  Data[', Msg^.DataCount, ']: ');
        for J := 0 to Msg^.DataCount - 1 do
        begin
          if J > 0 then Write(F, ' ');
          Write(F, IntToHex(Msg^.DataWords[J], 4));
        end;
        WriteLn(F);
      end;
      if not Msg^.IsValid then
        WriteLn(F, '  *** ERRORS: ', Msg^.ErrorSummary, ' ***');
    end;

    WriteLn(F, SEP);
    WriteLn(F, 'Total messages: ', Messages.Count);
  finally
    CloseFile(F);
  end;
end;

// ── TRandom helper (simple LCG, no SysUtils dependency) ───────────────────

// Embedded in implementation section to avoid unit pollution

end.
