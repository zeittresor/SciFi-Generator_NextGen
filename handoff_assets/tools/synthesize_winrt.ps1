param(
    [Parameter(Mandatory=$true)][string]$VoiceId,
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [double]$Rate = 1.0,
    [double]$Volume = 1.0
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime] | Out-Null

function Await-Result($Operation, [Type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
        Select-Object -First 1
    if ($null -eq $method) { throw 'Windows Runtime AsTask helper was not found.' }
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$text = [System.IO.File]::ReadAllText($InputFile, [System.Text.Encoding]::UTF8)
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
    Where-Object { $_.Id -eq $VoiceId } |
    Select-Object -First 1
if ($null -eq $voice) { throw "WinRT voice not found: $VoiceId" }

$synth.Voice = $voice
$synth.Options.SpeakingRate = [Math]::Max(0.5, [Math]::Min(2.0, $Rate))
$synth.Options.AudioVolume = [Math]::Max(0.0, [Math]::Min(1.0, $Volume))
$operation = $synth.SynthesizeTextToStreamAsync($text)
$stream = Await-Result $operation ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$source = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
$target = [System.IO.File]::Create($OutputFile)
try {
    $source.CopyTo($target)
}
finally {
    $target.Dispose()
    $source.Dispose()
    $stream.Dispose()
    $synth.Dispose()
}
