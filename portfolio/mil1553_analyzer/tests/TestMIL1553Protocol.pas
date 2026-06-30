unit TestMIL1553Protocol;

{
  TestMIL1553Protocol.pas — DUnit test suite for MIL-STD-1553B protocol decoder.

  Tests cover:
    - Command word bit-field extraction
    - Status word bit-flag decoding
    - Message type classification
    - Decoder state machine (BC→RT, RT→BC, mode codes)
    - Error detection (parity, timeout, sync)
    - Statistics counters
    - Simulator output validation

  Run via: DUnitTestRunner or Project > Compile + Run from Delphi IDE.

  Author : Stanislav Perfilyev
  License: MIT
}

{$MODE DELPHI}

interface

uses
  TestFramework,      // DUnit
  SysUtils,
  MIL1553Types,
  MIL1553Protocol;

type
  // ── Command Word tests ─────────────────────────────────────────────────────

  TTestCommandWord = class(TTestCase)
  published
    procedure TestRTAddressExtraction;
    procedure TestTransmitBitTrue;
    procedure TestTransmitBitFalse;
    procedure TestSubAddressExtraction;
    procedure TestWordCountExtraction;
    procedure TestWordCountZeroMeans32;
    procedure TestIsModeCodeSubAddr0;
    procedure TestIsModeCodeSubAddr31;
    procedure TestIsModeCodeNegative;
    procedure TestDirectionReceive;
    procedure TestDirectionTransmit;
    procedure TestToStringFormat;
  end;

  // ── Status Word tests ──────────────────────────────────────────────────────

  TTestStatusWord = class(TTestCase)
  published
    procedure TestRTAddressExtraction;
    procedure TestMessageErrorBit;
    procedure TestServiceRequestBit;
    procedure TestBusyBit;
    procedure TestSubsystemFlagBit;
    procedure TestTerminalFlagBit;
    procedure TestBroadcastReceivedBit;
    procedure TestIsHealthyAllClear;
    procedure TestIsHealthyWithError;
    procedure TestToStringHealthy;
    procedure TestToStringWithFlags;
  end;

  // ── Message tests ──────────────────────────────────────────────────────────

  TTestMil1553Message = class(TTestCase)
  published
    procedure TestIsValidNoErrors;
    procedure TestIsValidParityError;
    procedure TestIsValidTimeout;
    procedure TestIsValidSyncError;
    procedure TestErrorSummaryNone;
    procedure TestErrorSummaryMultiple;
    procedure TestToLogLineFormat;
  end;

  // ── Decoder state machine ──────────────────────────────────────────────────

  TTestDecoder = class(TTestCase)
  private
    FDecoder   : TMil1553Decoder;
    FMessages  : array of TMil1553Message;
    FMsgCount  : Integer;
    FErrors    : TStringList;

    procedure OnMessage(const Msg: TMil1553Message);
    procedure OnError(const ErrMsg: string);

    function MakeCW(RT, SA, WC: Byte; Tx: Boolean): TMil1553Word;
    function MakeSW(RT: Byte): TMil1553Word;

    procedure FeedCW(Raw: TMil1553Word; Parity: Boolean = True);
    procedure FeedDW(Raw: TMil1553Word; Parity: Boolean = True);
  protected
    procedure SetUp; override;
    procedure TearDown; override;
  published
    procedure TestBCtoRTSingleWord;
    procedure TestBCtoRT4Words;
    procedure TestRTtoBC2Words;
    procedure TestModeCodeNoData;
    procedure TestParityErrorFlagged;
    procedure TestTimeoutFlagged;
    procedure TestSyncErrorCausesAbort;
    procedure TestMultipleMessagesSequential;
    procedure TestStatsCounters;
  end;

  // ── Simulator tests ────────────────────────────────────────────────────────

  TTestSimulator = class(TTestCase)
  published
    procedure TestNormalScenario10Messages;
    procedure TestFlightDataScenario;
    procedure TestHighErrorHasErrors;
    procedure TestTimestampsAreMonotonic;
    procedure TestSequenceNumbersIncrement;
  end;

  // ── Utility function tests ─────────────────────────────────────────────────

  TTestUtils = class(TTestCase)
  published
    procedure TestModeCodeFromByteKnown;
    procedure TestModeCodeFromByteUnknown;
    procedure TestModeCodeNameSync;
    procedure TestMessageTypeNameBCtoRT;
    procedure TestFormatTimestampISO;
  end;

implementation

uses
  Contnrs, DateUtils;

// ══════════════════════════════════════════════════════════════════════════════
// TTestCommandWord
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestCommandWord.TestRTAddressExtraction;
var CW: TMil1553CommandWord;
begin
  // RT=5 sits at bits 15..11 = 5 shl 11 = $2800
  CW.Raw := $2800;
  CheckEquals(5, CW.RTAddress, 'RT address extraction');
end;

procedure TTestCommandWord.TestTransmitBitTrue;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0400;  // bit 10 set
  CheckTrue(CW.TransmitBit, 'T/R=1 should be Transmit');
end;

procedure TTestCommandWord.TestTransmitBitFalse;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0000;
  CheckFalse(CW.TransmitBit, 'T/R=0 should be Receive');
end;

procedure TTestCommandWord.TestSubAddressExtraction;
var CW: TMil1553CommandWord;
begin
  // SA=7 sits at bits 9..5 = 7 shl 5 = $00E0
  CW.Raw := $00E0;
  CheckEquals(7, CW.SubAddress, 'Subaddress extraction');
end;

procedure TTestCommandWord.TestWordCountExtraction;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $000A;  // bits 4..0 = 10
  CheckEquals(10, CW.WordCount, 'Word count extraction');
end;

procedure TTestCommandWord.TestWordCountZeroMeans32;
var CW: TMil1553CommandWord;
begin
  // WC=0 means 32 — but extraction returns 0; caller must handle per spec
  CW.Raw := $0000;
  CheckEquals(0, CW.WordCount, 'Raw WC=0 returned as 0');
end;

procedure TTestCommandWord.TestIsModeCodeSubAddr0;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0000;  // SA=0 → mode code
  CheckTrue(CW.IsModeCode, 'SA=0 should be mode code');
end;

procedure TTestCommandWord.TestIsModeCodeSubAddr31;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $03E0;  // SA=31 (bits 9..5)
  CheckTrue(CW.IsModeCode, 'SA=31 should be mode code');
end;

procedure TTestCommandWord.TestIsModeCodeNegative;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0020;  // SA=1 → not mode code
  CheckFalse(CW.IsModeCode, 'SA=1 should not be mode code');
end;

procedure TTestCommandWord.TestDirectionReceive;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0000;
  CheckEquals(Ord(dirReceive), Ord(CW.Direction), 'T/R=0 → Receive');
end;

procedure TTestCommandWord.TestDirectionTransmit;
var CW: TMil1553CommandWord;
begin
  CW.Raw := $0400;
  CheckEquals(Ord(dirTransmit), Ord(CW.Direction), 'T/R=1 → Transmit');
end;

procedure TTestCommandWord.TestToStringFormat;
var CW: TMil1553CommandWord;
begin
  // RT=1, T/R=0, SA=2, WC=4
  CW.Raw := (Word(1) shl 11) or (Word(2) shl 5) or Word(4);
  CheckEquals('CW[RT=01 T/R=0 SA=02 WC=04]', CW.ToString, 'ToString format');
end;

// ══════════════════════════════════════════════════════════════════════════════
// TTestStatusWord
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestStatusWord.TestRTAddressExtraction;
var SW: TMil1553StatusWord;
begin
  SW.Raw := Word(12) shl 11;  // RT=12
  CheckEquals(12, SW.RTAddress, 'SW RT address');
end;

procedure TTestStatusWord.TestMessageErrorBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0400;
  CheckTrue(SW.MessageError, 'MessageError bit');
end;

procedure TTestStatusWord.TestServiceRequestBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0100;
  CheckTrue(SW.ServiceRequest, 'ServiceRequest bit');
end;

procedure TTestStatusWord.TestBusyBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0008;
  CheckTrue(SW.Busy, 'Busy bit');
end;

procedure TTestStatusWord.TestSubsystemFlagBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0004;
  CheckTrue(SW.SubsystemFlag, 'SubsystemFlag bit');
end;

procedure TTestStatusWord.TestTerminalFlagBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0001;
  CheckTrue(SW.TerminalFlag, 'TerminalFlag bit');
end;

procedure TTestStatusWord.TestBroadcastReceivedBit;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0010;
  CheckTrue(SW.BroadcastReceived, 'BroadcastReceived bit');
end;

procedure TTestStatusWord.TestIsHealthyAllClear;
var SW: TMil1553StatusWord;
begin
  SW.Raw := Word(5) shl 11;  // Only RT address, no error bits
  CheckTrue(SW.IsHealthy, 'All clear = healthy');
end;

procedure TTestStatusWord.TestIsHealthyWithError;
var SW: TMil1553StatusWord;
begin
  SW.Raw := $0400;  // MessageError set
  CheckFalse(SW.IsHealthy, 'MessageError → not healthy');
end;

procedure TTestStatusWord.TestToStringHealthy;
var SW: TMil1553StatusWord;
begin
  SW.Raw := Word(3) shl 11;
  CheckEquals('SW[RT=03 OK]', SW.ToString, 'Healthy status string');
end;

procedure TTestStatusWord.TestToStringWithFlags;
var SW: TMil1553StatusWord;
begin
  SW.Raw := (Word(7) shl 11) or $0009;  // RT=7, Busy + TerminalFlag
  CheckTrue(Pos('BY', SW.ToString) > 0, 'Busy flag in string');
  CheckTrue(Pos('TF', SW.ToString) > 0, 'TerminalFlag in string');
end;

// ══════════════════════════════════════════════════════════════════════════════
// TTestMil1553Message
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestMil1553Message.TestIsValidNoErrors;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  CheckTrue(Msg.IsValid, 'Default message has no errors');
end;

procedure TTestMil1553Message.TestIsValidParityError;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  Msg.ParityError := True;
  CheckFalse(Msg.IsValid, 'ParityError invalidates message');
end;

procedure TTestMil1553Message.TestIsValidTimeout;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  Msg.ResponseTimeout := True;
  CheckFalse(Msg.IsValid, 'Timeout invalidates message');
end;

procedure TTestMil1553Message.TestIsValidSyncError;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  Msg.SyncError := True;
  CheckFalse(Msg.IsValid, 'SyncError invalidates message');
end;

procedure TTestMil1553Message.TestErrorSummaryNone;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  CheckEquals('NONE', Msg.ErrorSummary, 'No errors = NONE');
end;

procedure TTestMil1553Message.TestErrorSummaryMultiple;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  Msg.ParityError     := True;
  Msg.ResponseTimeout := True;
  CheckTrue(Pos('PARITY',  Msg.ErrorSummary) > 0, 'PARITY in summary');
  CheckTrue(Pos('TIMEOUT', Msg.ErrorSummary) > 0, 'TIMEOUT in summary');
end;

procedure TTestMil1553Message.TestToLogLineFormat;
var Msg: TMil1553Message;
begin
  FillChar(Msg, SizeOf(Msg), 0);
  Msg.SequenceNo  := 42;
  Msg.Timestamp   := EncodeDateTime(2026, 1, 15, 10, 30, 0, 0);
  Msg.BusChannel  := 'A';
  Msg.MessageType := mtBCtoRT;
  Msg.Command1.Raw := (Word(5) shl 11) or Word(3);  // RT=5, WC=3
  // CSV contains seq number
  CheckTrue(Pos('42', Msg.ToLogLine) > 0, 'SeqNo in log line');
  CheckTrue(Pos('A',  Msg.ToLogLine) > 0, 'Bus channel in log line');
end;

// ══════════════════════════════════════════════════════════════════════════════
// TTestDecoder
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestDecoder.OnMessage(const Msg: TMil1553Message);
begin
  if FMsgCount >= Length(FMessages) then
    SetLength(FMessages, Length(FMessages) + 16);
  FMessages[FMsgCount] := Msg;
  Inc(FMsgCount);
end;

procedure TTestDecoder.OnError(const ErrMsg: string);
begin
  FErrors.Add(ErrMsg);
end;

function TTestDecoder.MakeCW(RT, SA, WC: Byte; Tx: Boolean): TMil1553Word;
begin
  Result := (Word(RT and $1F) shl 11)
          or (Word(Ord(Tx)) shl 10)
          or (Word(SA and $1F) shl 5)
          or  Word(WC and $1F);
end;

function TTestDecoder.MakeSW(RT: Byte): TMil1553Word;
begin
  Result := Word(RT and $1F) shl 11;
end;

procedure TTestDecoder.FeedCW(Raw: TMil1553Word; Parity: Boolean);
begin
  FDecoder.ProcessWord(Raw, stCommand, Now, Parity);
end;

procedure TTestDecoder.FeedDW(Raw: TMil1553Word; Parity: Boolean);
begin
  FDecoder.ProcessWord(Raw, stData, Now, Parity);
end;

procedure TTestDecoder.SetUp;
begin
  FDecoder  := TMil1553Decoder.Create('A');
  FDecoder.OnMessage := OnMessage;
  FDecoder.OnError   := OnError;
  FErrors   := TStringList.Create;
  FMsgCount := 0;
  SetLength(FMessages, 32);
end;

procedure TTestDecoder.TearDown;
begin
  FDecoder.Free;
  FErrors.Free;
end;

procedure TTestDecoder.TestBCtoRTSingleWord;
begin
  // BC→RT: RT=3, SA=1, WC=1, Receive
  FeedCW(MakeCW(3, 1, 1, False));
  FeedDW($ABCD);
  FeedCW(MakeSW(3));   // Status from RT

  CheckEquals(1, FMsgCount, 'One message assembled');
  CheckEquals(Ord(mtBCtoRT), Ord(FMessages[0].MessageType), 'Type = BC→RT');
  CheckEquals(3, FMessages[0].Command1.RTAddress, 'RT address');
  CheckEquals(1, FMessages[0].DataCount, 'Data word count');
  CheckEquals($ABCD, FMessages[0].DataWords[0], 'Data word value');
  CheckTrue(FMessages[0].IsValid, 'Message valid');
end;

procedure TTestDecoder.TestBCtoRT4Words;
begin
  FeedCW(MakeCW(7, 2, 4, False));
  FeedDW($0001);
  FeedDW($0002);
  FeedDW($0003);
  FeedDW($0004);
  FeedCW(MakeSW(7));

  CheckEquals(1, FMsgCount, 'One message');
  CheckEquals(4, FMessages[0].DataCount, '4 data words');
  CheckEquals($0003, FMessages[0].DataWords[2], 'Third data word');
end;

procedure TTestDecoder.TestRTtoBC2Words;
begin
  // RT→BC: transmit 2 words
  FeedCW(MakeCW(5, 3, 2, True));   // Transmit command
  FeedCW(MakeSW(5));                // Status first
  FeedDW($1111);
  FeedDW($2222);

  CheckEquals(1, FMsgCount, 'One RT→BC message');
  CheckEquals(Ord(mtRTtoBC), Ord(FMessages[0].MessageType), 'Type = RT→BC');
end;

procedure TTestDecoder.TestModeCodeNoData;
begin
  // Mode code: SA=0 (mode code), WC=mode code value
  FeedCW(MakeCW(10, 0, Ord(mcResetRemoteTerminal), False));
  FeedCW(MakeSW(10));

  CheckEquals(1, FMsgCount, 'Mode code message');
  CheckEquals(Ord(mtModeCode), Ord(FMessages[0].MessageType), 'Type = Mode Code');
  CheckEquals(10, FMessages[0].Command1.RTAddress, 'RT=10');
end;

procedure TTestDecoder.TestParityErrorFlagged;
begin
  FeedCW(MakeCW(1, 1, 1, False), {Parity=}False);  // Bad parity
  FeedDW($FFFF);
  FeedCW(MakeSW(1));

  CheckEquals(1, FMsgCount, 'Message still assembled');
  CheckTrue(FMessages[0].ParityError, 'Parity error flagged');
  CheckFalse(FMessages[0].IsValid, 'Message invalid due to parity');
end;

procedure TTestDecoder.TestTimeoutFlagged;
begin
  FeedCW(MakeCW(2, 1, 1, False));
  FeedDW($1234);
  // No status — signal timeout
  FDecoder.SignalTimeout;

  CheckEquals(1, FMsgCount, 'Timeout produces message');
  CheckTrue(FMessages[0].ResponseTimeout, 'Timeout flagged');
  CheckFalse(FMessages[0].IsValid, 'Message invalid');
end;

procedure TTestDecoder.TestSyncErrorCausesAbort;
begin
  FeedCW(MakeCW(4, 1, 2, False));
  // Expected data word, but we send a command-sync word instead
  FeedCW($1234);  // Wrong sync type — should abort current, start new

  // Error should have been raised
  CheckTrue(FErrors.Count > 0, 'Sync error reported');
end;

procedure TTestDecoder.TestMultipleMessagesSequential;
var I: Integer;
begin
  for I := 1 to 5 do
  begin
    FeedCW(MakeCW(I, 1, 1, False));
    FeedDW(Word(I * $100));
    FeedCW(MakeSW(I));
  end;

  CheckEquals(5, FMsgCount, '5 sequential messages');
  for I := 0 to 4 do
    CheckEquals(I + 1, Integer(FMessages[I].SequenceNo), Format('SeqNo msg %d', [I + 1]));
end;

procedure TTestDecoder.TestStatsCounters;
begin
  // 3 BC→RT messages
  FeedCW(MakeCW(1, 1, 1, False)); FeedDW($0001); FeedCW(MakeSW(1));
  FeedCW(MakeCW(2, 1, 1, False)); FeedDW($0002); FeedCW(MakeSW(2));
  FeedCW(MakeCW(3, 1, 1, False)); FeedDW($0003); FeedCW(MakeSW(3));

  CheckEquals(3, Integer(FDecoder.Stats.TotalMessages), 'Total = 3');
  CheckEquals(3, Integer(FDecoder.Stats.ValidMessages), 'Valid = 3');
  CheckEquals(0, Integer(FDecoder.Stats.ErrorMessages), 'Errors = 0');
  CheckEquals(3, Integer(FDecoder.Stats.BCtoRTCount),   'BC→RT = 3');
end;

// ══════════════════════════════════════════════════════════════════════════════
// TTestSimulator
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestSimulator.TestNormalScenario10Messages;
var
  Sim  : TMil1553Simulator;
  List : TObjectList;
begin
  Sim  := TMil1553Simulator.Create(ssNormal);
  List := TObjectList.Create(True);
  try
    Sim.Generate(Now, 10, List);
    CheckEquals(10, List.Count, '10 messages generated');
  finally
    Sim.Free;
    List.Free;
  end;
end;

procedure TTestSimulator.TestFlightDataScenario;
var
  Sim  : TMil1553Simulator;
  List : TObjectList;
  Msg  : PMil1553Message;
begin
  Sim  := TMil1553Simulator.Create(ssFlightData);
  List := TObjectList.Create(True);
  try
    Sim.Generate(Now, 8, List);
    // First message should be IMU (RT1, SA1, 8 words, RT→BC)
    Msg := PMil1553Message(List[0]);
    CheckEquals(Ord(mtRTtoBC), Ord(Msg^.MessageType), 'First = RT→BC (IMU)');
    CheckEquals(1, Msg^.Command1.RTAddress, 'RT=1 (IMU)');
    CheckEquals(8, Msg^.DataCount, '8 IMU words');
  finally
    Sim.Free;
    List.Free;
  end;
end;

procedure TTestSimulator.TestHighErrorHasErrors;
var
  Sim     : TMil1553Simulator;
  List    : TObjectList;
  I       : Integer;
  ErrCount: Integer;
  Msg     : PMil1553Message;
begin
  Sim     := TMil1553Simulator.Create(ssHighError);
  List    := TObjectList.Create(True);
  ErrCount := 0;
  try
    Sim.Generate(Now, 30, List);
    for I := 0 to List.Count - 1 do
    begin
      Msg := PMil1553Message(List[I]);
      if not Msg^.IsValid then Inc(ErrCount);
    end;
    CheckTrue(ErrCount > 0, 'High-error scenario must produce some errors');
  finally
    Sim.Free;
    List.Free;
  end;
end;

procedure TTestSimulator.TestTimestampsAreMonotonic;
var
  Sim  : TMil1553Simulator;
  List : TObjectList;
  I    : Integer;
  Prev : TDateTime;
begin
  Sim  := TMil1553Simulator.Create(ssNormal);
  List := TObjectList.Create(True);
  try
    Sim.Generate(Now, 20, List);
    Prev := 0;
    for I := 0 to List.Count - 1 do
    begin
      CheckTrue(PMil1553Message(List[I])^.Timestamp >= Prev,
        Format('Timestamp[%d] must not go backward', [I]));
      Prev := PMil1553Message(List[I])^.Timestamp;
    end;
  finally
    Sim.Free;
    List.Free;
  end;
end;

procedure TTestSimulator.TestSequenceNumbersIncrement;
var
  Sim  : TMil1553Simulator;
  List : TObjectList;
  I    : Integer;
  Prev : UInt64;
begin
  Sim  := TMil1553Simulator.Create(ssNormal);
  List := TObjectList.Create(True);
  try
    Sim.Generate(Now, 10, List);
    Prev := 0;
    for I := 0 to List.Count - 1 do
    begin
      CheckTrue(PMil1553Message(List[I])^.SequenceNo > Prev,
        Format('SeqNo[%d] must increase', [I]));
      Prev := PMil1553Message(List[I])^.SequenceNo;
    end;
  finally
    Sim.Free;
    List.Free;
  end;
end;

// ══════════════════════════════════════════════════════════════════════════════
// TTestUtils
// ══════════════════════════════════════════════════════════════════════════════

procedure TTestUtils.TestModeCodeFromByteKnown;
begin
  CheckEquals(Ord(mcSynchronize),
    Ord(ModeCodeFromByte($01)), 'Synchronize = $01');
  CheckEquals(Ord(mcResetRemoteTerminal),
    Ord(ModeCodeFromByte($08)), 'Reset RT = $08');
end;

procedure TTestUtils.TestModeCodeFromByteUnknown;
begin
  CheckEquals(Ord(mcUnknown),
    Ord(ModeCodeFromByte($FF)), 'Unknown mode code');
end;

procedure TTestUtils.TestModeCodeNameSync;
begin
  CheckEquals('Synchronize', ModeCodeName(mcSynchronize), 'Sync name');
end;

procedure TTestUtils.TestMessageTypeNameBCtoRT;
begin
  CheckEquals('BC→RT', MessageTypeName(mtBCtoRT), 'BC→RT name');
end;

procedure TTestUtils.TestFormatTimestampISO;
var
  DT  : TDateTime;
  Str : string;
begin
  DT  := EncodeDateTime(2026, 6, 29, 12, 00, 00, 500);
  Str := FormatTimestamp(DT);
  CheckTrue(Pos('2026-06-29', Str) > 0, 'Date in ISO format');
  CheckTrue(Pos('12:00:00',   Str) > 0, 'Time in format');
  CheckTrue(Pos('500',        Str) > 0, 'Milliseconds in format');
end;

// ── Test registration ──────────────────────────────────────────────────────

initialization
  RegisterTest(TTestCommandWord.Suite);
  RegisterTest(TTestStatusWord.Suite);
  RegisterTest(TTestMil1553Message.Suite);
  RegisterTest(TTestDecoder.Suite);
  RegisterTest(TTestSimulator.Suite);
  RegisterTest(TTestUtils.Suite);

end.
