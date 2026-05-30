param(
    [string]$DocsRoot = (Join-Path $PSScriptRoot "..\docs")
)

$ErrorActionPreference = "Stop"
$docsPath = (Resolve-Path $DocsRoot).Path
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$excludedSections = @("about", "contact", "editorial-policy", "privacy", "terms")
$headMarker = "adsense-config.js"
$footerSlot = @'
    <section class="ad-placement ad-placement-footer" aria-label="Advertisement">
      <div class="adsense-slot" data-ad-slot-key="contentFooter"></div>
    </section>

'@
$homeSlot = @'
      <section class="ad-placement ad-placement-home" aria-label="Advertisement">
        <div class="adsense-slot" data-ad-slot-key="homeFeed"></div>
      </section>

'@

function Get-RootPrefix([System.IO.FileInfo]$Page) {
    $relativePath = $Page.DirectoryName.Substring($docsPath.Length).TrimStart("\")
    if (-not $relativePath) {
        return "./"
    }

    $depth = $relativePath.Split([System.IO.Path]::DirectorySeparatorChar).Count
    return "../" * $depth
}

function Get-RelativePath([System.IO.FileInfo]$Page) {
    return $Page.FullName.Substring($docsPath.Length).TrimStart("\").Replace("\", "/")
}

function Test-MonetizedPage([System.IO.FileInfo]$Page) {
    $parts = (Get-RelativePath $Page).Split("/")

    if ($parts[0] -eq "zh-cn" -and $parts.Count -gt 2) {
        return $excludedSections -notcontains $parts[1]
    }

    return $excludedSections -notcontains $parts[0]
}

$updated = 0
Get-ChildItem -Path $docsPath -Recurse -Filter "index.html" | ForEach-Object {
    if (-not (Test-MonetizedPage $_)) {
        return
    }

    $content = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
    $original = $content
    $prefix = Get-RootPrefix $_
    $relative = Get-RelativePath $_

    if ($content -notmatch [regex]::Escape($headMarker)) {
        $scripts = "    <script src=`"${prefix}adsense-config.js`"></script>`n" +
            "    <script src=`"${prefix}adsense.js`"></script>`n"
        $content = $content.Replace("</head>", "$scripts  </head>")
    }

    if ($content -notmatch 'data-ad-slot-key="contentFooter"') {
        $footerIndex = $content.IndexOf('<footer class="site-footer">')
        if ($footerIndex -ge 0) {
            $content = $content.Insert($footerIndex, $footerSlot)
        } else {
            Write-Host "skipped_footer=$relative"
        }
    }

    if (($relative -eq "index.html" -or $relative -eq "zh-cn/index.html") -and
        $content -notmatch 'data-ad-slot-key="homeFeed"') {
        $foodsIndex = $content.IndexOf('<section id="foods">')
        if ($foodsIndex -lt 0) {
            throw "Cannot find foods section in $($_.FullName)"
        }
        $content = $content.Insert($foodsIndex, $homeSlot)
    }

    if ($content -ne $original) {
        [System.IO.File]::WriteAllText($_.FullName, $content, $utf8NoBom)
        $updated++
    }
}

Write-Host "updated_pages=$updated"
