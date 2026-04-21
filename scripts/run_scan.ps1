param(
    [switch]$UseClaude,
    [string]$FromFile = ""
)

if ($FromFile -ne "") {
    $argsList = @("-m", "app.main", "scan-json")
    $argsList += @("--from-file", $FromFile)
} else {
    $argsList = @("-m", "app.main", "scan-company-sites")
}
if ($UseClaude) {
    $argsList += "--use-claude"
}

python @argsList
