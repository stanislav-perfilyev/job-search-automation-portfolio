program mil1553_analyzer;

{
  MIL-STD-1553B Protocol Analyzer
  ================================
  Delphi/Object Pascal demonstration project for the MIL-STD-1553B (МКО)
  avionics data bus protocol.

  Project structure:
    src/MIL1553Types.pas    — protocol types, constants, word structures
    src/MIL1553Protocol.pas — decoder state machine + bus simulator
    tests/TestMIL1553Protocol.pas — DUnit test suite

  Build configurations:
    Release — VCL GUI analyzer (requires Delphi VCL)
    Test    — DUnit console runner

  Author : Stanislav Perfilyev
  License: MIT
}

{$APPTYPE CONSOLE}
{$MODE DELPHI}

uses
  SysUtils,
  Contnrs,
  MIL1553Types    in 'src\MIL1553Types.pas',
  MIL1553Protocol in 'src\MIL1553Protocol.pas';

// ── Demo: run a simulation and display results ────────────────────────────────

procedure RunDemo(Scenario: TSimScenario; Title: string; Count: Integer = 20);
var
  Sim     : TMil1553Simulator;
  List    : TObjectList;
  I       : Integer;
  Msg     : PMil1553Message;
  Valid   : Integer;
  Errors  : Integer;
begin
  WriteLn;
  WriteLn('═══════════════════════════════════════════════════════');
  WriteLn('  ', Title);
  WriteLn('═══════════════════════════════════════════════════════');

  Sim  := TMil1553Simulator.Create(Scenario, 'A');
  List := TObjectList.Create(True);
  Valid  := 0;
  Errors := 0;

  try
    Sim.Generate(Now, Count, List);

    for I := 0 to List.Count - 1 do
    begin
      Msg := PMil1553Message(List[I]);
      if Msg^.IsValid then Inc(Valid) else Inc(Errors);

      // Print first 10 messages
      if I < 10 then
      begin
        Write(Format('  #%-4d  %-12s  Bus-%s  RT=%02d  SA=%02d  WC=%02d  DC=%d',
          [Msg^.SequenceNo,
           Msg^.MessageTypeStr,
           Msg^.BusChannel,
           Msg^.Command1.RTAddress,
           Msg^.Command1.SubAddress,
           Msg^.Command1.WordCount,
           Msg^.DataCount]));

        if not Msg^.IsValid then
          Write('  *** ', Msg^.ErrorSummary, ' ***');
        WriteLn;
      end;
    end;

    if List.Count > 10 then
      WriteLn(Format('  ... and %d more messages', [List.Count - 10]));

    WriteLn;
    WriteLn(Format('  Summary: %d total, %d valid (%.0f%%), %d errors',
      [List.Count, Valid, Valid / List.Count * 100.0, Errors]));

    // Export to files
    var BaseName := ExtractFilePath(ParamStr(0)) +
      LowerCase(StringReplace(Title, ' ', '_', [rfReplaceAll]));
    ExportToCSV(TList(List), BaseName + '.csv');
    ExportToLog(TList(List), BaseName + '.log');
    WriteLn(Format('  Exported: %s.{csv,log}', [BaseName]));

  finally
    Sim.Free;
    List.Free;
  end;
end;

// ── Decoder smoke test ────────────────────────────────────────────────────────

var
  GDecodedCount : Integer = 0;
  GErrorCount   : Integer = 0;

procedure OnDecodedMessage(const Msg: TMil1553Message);
begin
  Inc(GDecodedCount);
  if not Msg.IsValid then Inc(GErrorCount);
end;

procedure RunDecoderSmokeTest;
var
  Decoder : TMil1553Decoder;
  // Manually craft BC→RT: RT=5, SA=2, WC=3, Receive
  CW, SW  : TMil1553Word;
begin
  WriteLn;
  WriteLn('═══════════════════════════════════════════════════════');
  WriteLn('  Decoder Smoke Test');
  WriteLn('═══════════════════════════════════════════════════════');

  Decoder := TMil1553Decoder.Create('B');
  Decoder.OnMessage := OnDecodedMessage;
  GDecodedCount := 0;

  // BC→RT command: RT=5, T/R=0, SA=2, WC=3
  CW := (Word(5) shl 11) or (Word(0) shl 10) or (Word(2) shl 5) or Word(3);
  Decoder.ProcessWord(CW, stCommand, Now, True);
  WriteLn('  [CMD] CW=', IntToHex(CW, 4), ' (RT=05, SA=02, WC=03, Receive)');

  // 3 data words
  Decoder.ProcessWord($A001, stData, Now, True);
  WriteLn('  [DW1] $A001');
  Decoder.ProcessWord($B002, stData, Now, True);
  WriteLn('  [DW2] $B002');
  Decoder.ProcessWord($C003, stData, Now, True);
  WriteLn('  [DW3] $C003');

  // Status from RT=5
  SW := Word(5) shl 11;
  Decoder.ProcessWord(SW, stCommand, Now, True);
  WriteLn('  [SW]  SW=', IntToHex(SW, 4), ' (RT=05, OK)');

  WriteLn;
  WriteLn(Format('  Result: %d message decoded, %d errors', [GDecodedCount, GErrorCount]));

  Decoder.Free;
end;

// ── Main ──────────────────────────────────────────────────────────────────────

begin
  WriteLn('┌───────────────────────────────────────────────────────┐');
  WriteLn('│  MIL-STD-1553B Protocol Analyzer  (МКО Анализатор)    │');
  WriteLn('│  Stanislav Perfilyev — github.com/stanislav-perfilyev  │');
  WriteLn('└───────────────────────────────────────────────────────┘');

  try
    RunDecoderSmokeTest;
    RunDemo(ssNormal,     'Normal Bus Traffic',  30);
    RunDemo(ssFlightData, 'Avionics Flight Data', 20);
    RunDemo(ssHighError,  'High Error Injection', 20);
    RunDemo(ssModeCodeSweep, 'Mode Code Sweep',  12);

    WriteLn;
    WriteLn('All demos complete. Press Enter to exit.');
    ReadLn;
  except
    on E: Exception do
    begin
      WriteLn('Fatal error: ', E.ClassName, ': ', E.Message);
      ExitCode := 1;
    end;
  end;
end.
