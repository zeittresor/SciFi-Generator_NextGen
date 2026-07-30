$ErrorActionPreference = 'Stop'
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime] | Out-Null
$items = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | ForEach-Object {
    [PSCustomObject]@{
        id = $_.Id
        name = $_.DisplayName
        language = $_.Language
        gender = $_.Gender.ToString()
        description = $_.Description
    }
})
$items | ConvertTo-Json -Compress -Depth 3
