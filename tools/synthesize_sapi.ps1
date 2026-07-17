param(
    [Parameter(Mandatory=$true)][string]$VoiceId,
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$Rate = 0,
    [int]$Volume = 100
)

$ErrorActionPreference = 'Stop'
$text = [System.IO.File]::ReadAllText($InputFile, [System.Text.Encoding]::UTF8)
$voice = New-Object -ComObject SAPI.SpVoice
$tokens = $voice.GetVoices()
$selected = $null
for ($index = 0; $index -lt $tokens.Count; $index++) {
    $candidate = $tokens.Item($index)
    if ($candidate.Id -eq $VoiceId) {
        $selected = $candidate
        break
    }
}
if ($null -eq $selected) { throw "SAPI voice not found: $VoiceId" }

$stream = New-Object -ComObject SAPI.SpFileStream
try {
    $voice.Voice = $selected
    $voice.Rate = [Math]::Max(-10, [Math]::Min(10, $Rate))
    $voice.Volume = [Math]::Max(0, [Math]::Min(100, $Volume))
    # SSFMCreateForWrite = 3. SAPI writes a standard PCM WAV stream.
    $stream.Open($OutputFile, 3, $false)
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak($text, 0)
}
finally {
    try { $stream.Close() } catch {}
    if ($null -ne $stream) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($stream) }
    if ($null -ne $tokens) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($tokens) }
    if ($null -ne $voice) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($voice) }
}
