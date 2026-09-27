# 源码与发布资产验证

本页说明如何核验“鉴权未来”署名声明，以及本次发布源码和安装包是否与签名摘要一致。

- 署名团队：鉴权未来（GitHub：[@mingx2915-lab](https://github.com/mingx2915-lab)）
- GPG 公钥指纹：`DE6B D11D 08FA 19BF F9F8 2B4B B7F2 07B0 2407 7535`
- 公钥文件：[`AUTHENTICITY-public-key.asc`](AUTHENTICITY-public-key.asc)
- 署名声明：[`AUTHORS.md`](AUTHORS.md)

## 核验 Release 资产

从 GitHub Release 下载 `AUTHENTICITY-public-key.asc`、`SHA256SUMS.txt`、`SHA256SUMS.txt.asc`，以及摘要文件列出的安装包和源码 ZIP。先核对公钥指纹与本页完全一致，再执行：

```sh
gpg --import AUTHENTICITY-public-key.asc
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

Windows 可用 Git Bash 执行以上命令；也可用 PowerShell 的 `Get-FileHash -Algorithm SHA256 <文件>`，将结果与 `SHA256SUMS.txt` 比对。

## GitHub 提交标记

署名代码注释和本页位于本次源码快照对应的签名提交中。将公钥登记到 `mingx2915-lab` 账户后，GitHub 会对匹配此密钥的有效签名提交显示 `Verified`。本次只为后续署名提交使用该密钥；已有 `v0.1.2` 标签没有重签或改写。签名验证说明本密钥认可对应提交与文件摘要，不替代可复现构建、逐行贡献统计或独立安全审计。
