unit MIL1553Types;

{
  MIL1553Types.pas — Type definitions for MIL-STD-1553B protocol.

  MIL-STD-1553B is a military avionics data bus standard (МКО — Мультиплексный
  Канал Обмена) widely used in aircraft, spacecraft and defense systems.

  Protocol overview:
    - Serial data bus, 1 Mbit/s, Manchester II encoding
    - Bus Controller (BC) manages all communication
    - Remote Terminals (RT, up to 31) respond to BC commands
    - Bus Monitor (BM) passively observes all traffic

  Author : Stanislav Perfilyev
  License: MIT
}

{$MODE DELPHI}

interface

uses
  SysUtils;

const
  // ── Protocol constants ────────────────────────────────────────────────────

  MIL1553_MAX_RT          = 31;    // Maximum Remote Terminal address
  MIL1553_MAX_DATA_WORDS  = 32;    // Maximum data words per message
  MIL1553_BIT_RATE_BPS    = 1_000_000; // 1 Mbit/s
  MIL1553_WORD_BITS       = 20;    // 3 sync + 16 data + 1 parity
  MIL1553_SYNC_BITS       = 3;

  // ── Subaddress special values ─────────────────────────────────────────────

  MIL1553_SA_MODE_CODE    = $00;   // Subaddress 0 or 31 = Mode Code
  MIL1553_SA_MODE_CODE2   = $1F;

type
  // ── Word types ────────────────────────────────────────────────────────────

  /// Raw 16-bit MIL-STD-1553 word (data payload)
  TMil1553Word = Word;

  /// Direction of data transfer
  TMil1553Direction = (
    dirReceive,   // RT receives data from BC (Receive command: T/R=0)
    dirTransmit   // RT transmits data to BC  (Transmit command: T/R=1)
  );

  /// Message types as decoded from command word
  TMil1553MessageType = (
    mtBCtoRT,         // Bus Controller → Remote Terminal
    mtRTtoBC,         // Remote Terminal → Bus Controller
    mtRTtoRT,         // Remote Terminal → Remote Terminal
    mtModeCode,       // Mode Code command (no data or 1 word)
    mtBroadcast,      // Broadcast (RT address = 31)
    mtUnknown         // Malformed or unrecognized
  );

  /// Word sync pulse type (determines word category)
  TMil1553SyncType = (
    stCommand,  // 3-bit sync for Command/Status words  (high→low)
    stData      // 3-bit sync for Data words            (low→high)
  );

  // ── Command Word (bits 15..0) ──────────────────────────────────────────────
  //
  //  15..11  RT address   (5 bits)
  //  10      T/R bit      (1=Transmit, 0=Receive)
  //   9.. 5  Subaddress   (5 bits, 00000/11111 = Mode Code)
  //   4.. 0  Word count / Mode code  (5 bits)

  TMil1553CommandWord = packed record
    Raw        : TMil1553Word;

    function RTAddress   : Byte;    // bits 15..11
    function TransmitBit : Boolean; // bit 10 (true=RT transmits)
    function SubAddress  : Byte;    // bits  9.. 5
    function WordCount   : Byte;    // bits  4.. 0 (0=32 words)
    function IsModeCode  : Boolean;
    function Direction   : TMil1553Direction;
    function ToString    : string;
  end;

  // ── Status Word (bits 15..0) ───────────────────────────────────────────────
  //
  //  15..11  RT address        (5 bits)
  //  10      Message Error     (1=error detected)
  //   9      Instrumentation   (reserved for BC, always 0 from RT)
  //   8      Service Request   (RT requests service)
  //   7.. 5  Reserved          (must be 0)
  //   4      Broadcast Command Received
  //   3      Busy              (RT cannot respond now)
  //   2      Subsystem Flag    (RT subsystem needs attention)
  //   1      Dynamic Bus Control Acceptance
  //   0      Terminal Flag     (RT hardware fault)

  TMil1553StatusWord = packed record
    Raw : TMil1553Word;

    function RTAddress          : Byte;
    function MessageError       : Boolean;
    function ServiceRequest     : Boolean;
    function Busy               : Boolean;
    function SubsystemFlag      : Boolean;
    function TerminalFlag       : Boolean;
    function BroadcastReceived  : Boolean;
    function IsHealthy          : Boolean;  // No error flags set
    function ToString           : string;
  end;

  // ── Complete decoded message ───────────────────────────────────────────────

  TMil1553DataArray = array[0..MIL1553_MAX_DATA_WORDS - 1] of TMil1553Word;

  TMil1553Message = record
    // Identification
    SequenceNo  : UInt64;           // Auto-incremented capture counter
    Timestamp   : TDateTime;        // Capture timestamp (UTC)
    BusChannel  : Char;             // 'A' or 'B' (dual-redundant bus)

    // Decoded fields
    MessageType : TMil1553MessageType;
    Command1    : TMil1553CommandWord;   // Primary command
    Command2    : TMil1553CommandWord;   // RT-to-RT receive command
    Status1     : TMil1553StatusWord;    // Response from RT (or RT1 in RT-RT)
    Status2     : TMil1553StatusWord;    // Response from RT2 in RT-RT

    // Data payload
    DataWords   : TMil1553DataArray;
    DataCount   : Byte;             // Actual number of data words (0..32)

    // Error flags (any true = message invalid)
    ParityError     : Boolean;
    SyncError       : Boolean;
    ManchesterError : Boolean;
    ResponseTimeout : Boolean;      // No status word received within 14 µs

    function IsValid       : Boolean;
    function ErrorSummary  : string;
    function MessageTypeStr: string;
    function ToLogLine     : string;  // CSV-friendly single-line summary
  end;

  PMil1553Message = ^TMil1553Message;

  // ── Statistics counters ───────────────────────────────────────────────────

  TMil1553Stats = record
    TotalMessages   : UInt64;
    ValidMessages   : UInt64;
    ErrorMessages   : UInt64;
    BCtoRTCount     : UInt64;
    RTtoBCCount     : UInt64;
    RTtoRTCount     : UInt64;
    ModeCodeCount   : UInt64;
    BroadcastCount  : UInt64;
    ParityErrors    : UInt64;
    TimeoutErrors   : UInt64;
    StartTime       : TDateTime;

    function MessageRate : Double;  // messages/sec since StartTime
    function ErrorRate   : Double;  // 0.0..1.0
    procedure Reset;
  end;

  // ── Mode codes (MIL-STD-1553B Table 30-1) ────────────────────────────────

  TMil1553ModeCode = (
    mcDynamicBusControl          = $00,
    mcSynchronize                = $01,
    mcTransmitStatusWord         = $02,
    mcInitiateSelfTest           = $03,
    mcTransmitterShutdown        = $04,
    mcOverrideTransmitterShutdown= $05,
    mcInhibitTerminalFlagBit     = $06,
    mcOverrideInhibitTermFlag    = $07,
    mcResetRemoteTerminal        = $08,
    mcTransmitVectorWord         = $10,
    mcSynchronizeWithDataWord    = $11,
    mcTransmitLastCommandWord    = $12,
    mcTransmitBITWord            = $13,
    mcSelectedTransmitterShutdown= $14,
    mcOverrideSelectedTxShutdown = $15,
    mcUnknown                    = $FF
  );

function ModeCodeFromByte(Value: Byte): TMil1553ModeCode;
function ModeCodeName(MC: TMil1553ModeCode): string;
function MessageTypeName(MT: TMil1553MessageType): string;
function FormatTimestamp(DT: TDateTime): string;

implementation

// ── TMil1553CommandWord ────────────────────────────────────────────────────

function TMil1553CommandWord.RTAddress: Byte;
begin
  Result := (Raw shr 11) and $1F;
end;

function TMil1553CommandWord.TransmitBit: Boolean;
begin
  Result := (Raw and $0400) <> 0;
end;

function TMil1553CommandWord.SubAddress: Byte;
begin
  Result := (Raw shr 5) and $1F;
end;

function TMil1553CommandWord.WordCount: Byte;
begin
  Result := Raw and $1F;
  // Per spec: word count 0 = 32 words
end;

function TMil1553CommandWord.IsModeCode: Boolean;
var
  SA: Byte;
begin
  SA := SubAddress;
  Result := (SA = MIL1553_SA_MODE_CODE) or (SA = MIL1553_SA_MODE_CODE2);
end;

function TMil1553CommandWord.Direction: TMil1553Direction;
begin
  if TransmitBit then
    Result := dirTransmit
  else
    Result := dirReceive;
end;

function TMil1553CommandWord.ToString: string;
begin
  Result := Format('CW[RT=%02d T/R=%d SA=%02d WC=%02d]',
    [RTAddress, Ord(TransmitBit), SubAddress, WordCount]);
end;

// ── TMil1553StatusWord ─────────────────────────────────────────────────────

function TMil1553StatusWord.RTAddress: Byte;
begin
  Result := (Raw shr 11) and $1F;
end;

function TMil1553StatusWord.MessageError: Boolean;
begin
  Result := (Raw and $0400) <> 0;
end;

function TMil1553StatusWord.ServiceRequest: Boolean;
begin
  Result := (Raw and $0100) <> 0;
end;

function TMil1553StatusWord.Busy: Boolean;
begin
  Result := (Raw and $0008) <> 0;
end;

function TMil1553StatusWord.SubsystemFlag: Boolean;
begin
  Result := (Raw and $0004) <> 0;
end;

function TMil1553StatusWord.TerminalFlag: Boolean;
begin
  Result := (Raw and $0001) <> 0;
end;

function TMil1553StatusWord.BroadcastReceived: Boolean;
begin
  Result := (Raw and $0010) <> 0;
end;

function TMil1553StatusWord.IsHealthy: Boolean;
begin
  Result := not (MessageError or Busy or SubsystemFlag or TerminalFlag);
end;

function TMil1553StatusWord.ToString: string;
var
  Flags: string;
begin
  Flags := '';
  if MessageError    then Flags := Flags + 'ME ';
  if ServiceRequest  then Flags := Flags + 'SR ';
  if Busy            then Flags := Flags + 'BY ';
  if SubsystemFlag   then Flags := Flags + 'SF ';
  if TerminalFlag    then Flags := Flags + 'TF ';
  if Flags = ''      then Flags := 'OK';
  Result := Format('SW[RT=%02d %s]', [RTAddress, Trim(Flags)]);
end;

// ── TMil1553Message ────────────────────────────────────────────────────────

function TMil1553Message.IsValid: Boolean;
begin
  Result := not (ParityError or SyncError or ManchesterError or ResponseTimeout);
end;

function TMil1553Message.ErrorSummary: string;
var
  Parts: array of string;
begin
  SetLength(Parts, 0);
  if ParityError     then begin SetLength(Parts, Length(Parts)+1); Parts[High(Parts)] := 'PARITY'; end;
  if SyncError       then begin SetLength(Parts, Length(Parts)+1); Parts[High(Parts)] := 'SYNC'; end;
  if ManchesterError then begin SetLength(Parts, Length(Parts)+1); Parts[High(Parts)] := 'MANCHESTER'; end;
  if ResponseTimeout then begin SetLength(Parts, Length(Parts)+1); Parts[High(Parts)] := 'TIMEOUT'; end;
  if Length(Parts) = 0 then
    Result := 'NONE'
  else
    Result := String.Join(' | ', Parts);
end;

function TMil1553Message.MessageTypeStr: string;
begin
  Result := MessageTypeName(MessageType);
end;

function TMil1553Message.ToLogLine: string;
begin
  // CSV: Seq,Time,Bus,Type,RT,SA,WC,Valid,Errors
  Result := Format('%d,%s,%s,%s,%d,%d,%d,%s,%s', [
    SequenceNo,
    FormatTimestamp(Timestamp),
    BusChannel,
    MessageTypeStr,
    Command1.RTAddress,
    Command1.SubAddress,
    Command1.WordCount,
    BoolToStr(IsValid, 'OK', 'ERR'),
    ErrorSummary
  ]);
end;

// ── TMil1553Stats ──────────────────────────────────────────────────────────

function TMil1553Stats.MessageRate: Double;
var
  ElapsedSec: Double;
begin
  ElapsedSec := (Now - StartTime) * SecsPerDay;
  if ElapsedSec < 0.001 then
    Result := 0.0
  else
    Result := TotalMessages / ElapsedSec;
end;

function TMil1553Stats.ErrorRate: Double;
begin
  if TotalMessages = 0 then
    Result := 0.0
  else
    Result := ErrorMessages / TotalMessages;
end;

procedure TMil1553Stats.Reset;
begin
  FillChar(Self, SizeOf(Self), 0);
  StartTime := Now;
end;

// ── Utility functions ──────────────────────────────────────────────────────

function ModeCodeFromByte(Value: Byte): TMil1553ModeCode;
begin
  case Value of
    $00: Result := mcDynamicBusControl;
    $01: Result := mcSynchronize;
    $02: Result := mcTransmitStatusWord;
    $03: Result := mcInitiateSelfTest;
    $04: Result := mcTransmitterShutdown;
    $05: Result := mcOverrideTransmitterShutdown;
    $06: Result := mcInhibitTerminalFlagBit;
    $07: Result := mcOverrideInhibitTermFlag;
    $08: Result := mcResetRemoteTerminal;
    $10: Result := mcTransmitVectorWord;
    $11: Result := mcSynchronizeWithDataWord;
    $12: Result := mcTransmitLastCommandWord;
    $13: Result := mcTransmitBITWord;
    $14: Result := mcSelectedTransmitterShutdown;
    $15: Result := mcOverrideSelectedTxShutdown;
  else
    Result := mcUnknown;
  end;
end;

function ModeCodeName(MC: TMil1553ModeCode): string;
begin
  case MC of
    mcDynamicBusControl:           Result := 'Dynamic Bus Control';
    mcSynchronize:                 Result := 'Synchronize';
    mcTransmitStatusWord:          Result := 'Transmit Status Word';
    mcInitiateSelfTest:            Result := 'Initiate Self-Test';
    mcTransmitterShutdown:         Result := 'Transmitter Shutdown';
    mcOverrideTransmitterShutdown: Result := 'Override Transmitter Shutdown';
    mcInhibitTerminalFlagBit:      Result := 'Inhibit Terminal Flag Bit';
    mcOverrideInhibitTermFlag:     Result := 'Override Inhibit Terminal Flag';
    mcResetRemoteTerminal:         Result := 'Reset Remote Terminal';
    mcTransmitVectorWord:          Result := 'Transmit Vector Word';
    mcSynchronizeWithDataWord:     Result := 'Synchronize (with Data Word)';
    mcTransmitLastCommandWord:     Result := 'Transmit Last Command Word';
    mcTransmitBITWord:             Result := 'Transmit BIT Word';
    mcSelectedTransmitterShutdown: Result := 'Selected Transmitter Shutdown';
    mcOverrideSelectedTxShutdown:  Result := 'Override Selected TX Shutdown';
  else
    Result := Format('Unknown Mode Code ($%02X)', [Ord(MC)]);
  end;
end;

function MessageTypeName(MT: TMil1553MessageType): string;
begin
  case MT of
    mtBCtoRT:    Result := 'BC→RT';
    mtRTtoBC:    Result := 'RT→BC';
    mtRTtoRT:    Result := 'RT→RT';
    mtModeCode:  Result := 'Mode Code';
    mtBroadcast: Result := 'Broadcast';
  else
    Result := 'Unknown';
  end;
end;

function FormatTimestamp(DT: TDateTime): string;
begin
  // ISO 8601 with milliseconds
  Result := FormatDateTime('yyyy-mm-dd hh:nn:ss.zzz', DT);
end;

end.
