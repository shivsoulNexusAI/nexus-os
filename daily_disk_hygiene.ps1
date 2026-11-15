Get-ChildItem "C:\MT5_Quant_278017866\bases" -Recurse -Filter "*.tkc" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-24) } |
    Remove-Item -Force -ErrorAction SilentlyContinue