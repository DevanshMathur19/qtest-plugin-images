$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedDigest = $env:EXPECTED_IMAGE_DIGEST
if (-not $expectedDigest) {
    if ($env:CANDIDATE_IMAGE -notmatch '@(sha256:[0-9a-f]{64})$') {
        throw 'CANDIDATE_IMAGE must be pinned by digest or EXPECTED_IMAGE_DIGEST must be set'
    }
    $expectedDigest = $Matches[1]
}
if ($expectedDigest -notmatch '^sha256:[0-9a-f]{64}$') {
    throw 'EXPECTED_IMAGE_DIGEST must be a sha256 digest'
}
$actualBuild = [System.Environment]::OSVersion.Version.Build.ToString()
if ($actualBuild -ne $env:EXPECTED_WINDOWS_BUILD) {
    throw "Expected Windows build $env:EXPECTED_WINDOWS_BUILD; observed $actualBuild"
}

$tokenPath = 'C:\var\run\secrets\kubernetes.io\serviceaccount\token'
$caPath = 'C:\var\run\secrets\kubernetes.io\serviceaccount\ca.crt'
if (-not (Test-Path -LiteralPath $tokenPath) -or -not (Test-Path -LiteralPath $caPath)) {
    throw 'Kubernetes service-account credentials are not mounted'
}
$token = Get-Content -LiteralPath $tokenPath -Raw
$namespace = $env:POD_NAMESPACE
$pod = if ($env:POD_NAME) { $env:POD_NAME } else { $env:COMPUTERNAME }
$base = "https://$($env:KUBERNETES_SERVICE_HOST):$($env:KUBERNETES_SERVICE_PORT_HTTPS)/api/v1/namespaces/$namespace/pods"
$curl = @(
    '--fail', '--silent', '--show-error', '--ssl-no-revoke', '--cacert', $caPath,
    '-H', "Authorization: Bearer $token"
)
$json = & curl.exe @curl "$base/$pod"
if ($LASTEXITCODE -ne 0) {
    $listing = (& curl.exe @curl $base | ConvertFrom-Json).items
    $addresses = @(
        [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object AddressFamily -eq ([System.Net.Sockets.AddressFamily]::InterNetwork) |
            ForEach-Object IPAddressToString
    )
    $matches = @($listing | Where-Object { $addresses -contains [string] $_.status.podIP })
    if ($matches.Count -ne 1) {
        throw "Could not identify the current Pod in namespace $namespace"
    }
    $podResource = $matches[0]
} else {
    $podResource = $json | ConvertFrom-Json
}

$requestedImages = @(
    @($podResource.spec.containers) + @($podResource.spec.initContainers) |
        Where-Object { $null -ne $_ } |
        ForEach-Object { [string] $_.image }
)
$normalizedCandidate = $env:CANDIDATE_IMAGE -replace '^docker\.io/', ''
$requestedMatch = @(
    $requestedImages | Where-Object {
        ($_ -replace '^docker\.io/', '') -eq $normalizedCandidate
    }
)
if ($requestedMatch.Count -lt 1) {
    throw "Expected Pod image $($env:CANDIDATE_IMAGE); requested: $($requestedImages -join ', ')"
}

$status = $podResource.status
$imageIds = @($status.containerStatuses | ForEach-Object { [string] $_.imageID })
$matching = @($imageIds | Where-Object { $_ -match "@$([regex]::Escape($expectedDigest))$" })
if ($matching.Count -lt 1) {
    throw "Expected running imageID $expectedDigest; observed: $($imageIds -join ', ')"
}
Write-Output "Requested image verified: $($env:CANDIDATE_IMAGE)"
Write-Output "Running digest verified: $expectedDigest"
