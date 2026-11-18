# CloudSubscribe 自维护 Fork（网盘订阅助手）

基于 [odomu/MoviePilot-Plugins](https://github.com/odomu/MoviePilot-Plugins) 的「网盘订阅助手」
（CloudSubscribe，GPL-3.0）二次开发维护。插件 ID 不变，MoviePilot 可直接从本仓库安装，
原有配置与数据无缝接管。

## 与上游的差异

| 版本 | 内容 |
|---|---|
| 1.7.11.2 | 新增“观影”搜索渠道：自动完成站点 PoW 验证并使用账号登录；按电影/剧集、标题、年份和季号严格匹配，返回真实可用的网盘分享及未加密磁力资源。 |
| 1.7.11.1 | 电影洗版基线修复：媒体服务器（Emby STRM 库）/整理历史/手动基线已给出有效评分时，不再因 115 目标目录没有同名实体文件而被整体清零。见 `patches/0001-movie-baseline-strm.patch`，上游 issue：[odomu/MoviePilot-Plugins#42](https://github.com/odomu/MoviePilot-Plugins/issues/42) |
| 1.7.11 | 上游原版，未改动（`plugins.v3/cloudsubscribe` 基底即 MP 中实际运行的版本） |

## 维护规矩

1. 上游发新版时：拉上游新版代码 → 逐条重套 `patches/` 里的补丁 → 版本号在上游版本后加后缀
   （如上游 1.7.12 → 本仓库 1.7.12.1）→ 本地仓库重装 → 实测一轮再收尾。
2. 每次改动必须对应一条 patch 文件或在本 README 的差异表里登记，不留无记录的修改。
3. 配置、Cookie、账号数据不进本仓库（只存代码）；那些在 MoviePilot 的插件数据目录里。
4. 若上游修复了 #42 且实测通过，可直接回归官方版（从 MP 插件市场重装即可，配置不丢）。
5. 本仓库副本不含 `search/hdhive/web/captcha.bin`（二进制文件，推送接口只支持文本）；
   该文件在 NAS 本地仓库的安装副本中完整保留，功能不受影响。

## 安装

把本仓库内容同步到 MoviePilot 的本地插件仓库目录（package.v3.json + plugins.v3/），
在 MP 插件页从本地仓库安装 CloudSubscribe 即可。

## 许可

GPL-3.0（继承自上游），见 LICENSE。
