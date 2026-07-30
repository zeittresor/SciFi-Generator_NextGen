$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$tokens = $voice.GetVoices()
$items = @()
try {
    for ($index = 0; $index -lt $tokens.Count; $index++) {
        $candidate = $tokens.Item($index)
        $items += [PSCustomObject]@{
            id = $candidate.Id
            name = $candidate.GetDescription()
            language = ''
            gender = ''
            description = $candidate.GetDescription()
        }
    }
}
finally {
    if ($null -ne $tokens) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($tokens) }
    if ($null -ne $voice) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($voice) }
}
$items | ConvertTo-Json -Compress -Depth 3
