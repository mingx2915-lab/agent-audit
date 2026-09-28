# 源码与发布资产核验

本说明对应 GitHub 仓库 `mingx2915-lab/agent-audit` 的 `v0.1.3` 发布。

- 署名团队：鉴权未来（[@mingx2915-lab](https://github.com/mingx2915-lab)）
- 发布源码包：`AgentAudit-0.1.3-source-20260928.zip`
- 校验文件：`SHA256SUMS.txt` 与 `SHA256SUMS.txt.asc`
- 当前发布签名公钥：[`AUTHENTICITY-public-key.asc`](AUTHENTICITY-public-key.asc)
- 署名说明：[`AUTHORS.md`](AUTHORS.md)

## 校验下载文件

先核对当前公钥的完整指纹：

```text
AB62 DBAA C751 F68C C34B 8411 CFA7 99F4 18EF F202
```

再验证清单签名和文件哈希。Git Bash/Linux：

```sh
gpg --import AUTHENTICITY-public-key.asc
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

PowerShell 可用 `Get-FileHash -Algorithm SHA256 <文件>` 将各资产哈希与 `SHA256SUMS.txt` 比较。只有在独立确认上述指纹属于团队后，签名验证才有身份意义；SHA-256 本身仅用于完整性检查。

## 历史密钥

`AUTHENTICITY-public-key-20260927.asc` 保留历史公钥，指纹为 `DE6B D11D 08FA 19BF F9F8 2B4B B7F2 07B0 2407 7535`。它用于验证历史源码快照 `AgentAudit-0.1.2-source-20260927-r3.zip` 及其旧校验文件，不签署本次 `v0.1.3` 资产。

当前 GPG 公钥登记到 GitHub 后，GitHub 才能把相应签名显示为 `Verified`。即使尚未登记，离线 GPG 验签仍可验证签名与此公钥相符；但公钥身份需要通过团队公布的完整指纹单独确认。
