# ✈️ 特价机票雷达

宁波 / 杭州 / 上海 出发，监控冲绳、济州、长滩等 20+ 个目的地的**周末 + 法定假期往返最低价**，
降价或跌破心理价位时**微信提醒**，并自动生成价格看板。零服务器，Fork 后靠 GitHub Actions 免费定时运行。

参考项目：
- [AWeirdDev/flights](https://github.com/AWeirdDev/flights)（fast-flights）— Google Flights 取价
- [zhanglong-ustc/flight-price-monitor](https://github.com/zhanglong-ustc/flight-price-monitor) — Actions 定时 + Server酱 + 看板 的思路

## 5 分钟部署

1. 在 GitHub 新建仓库（建议 **Public**，Actions 分钟数不限），把本目录所有文件推上去。
2. 微信提醒：打开 [sct.ftqq.com](https://sct.ftqq.com/) 微信扫码，复制 SendKey；
   仓库 **Settings → Secrets and variables → Actions → New repository secret**，
   Name 填 `SERVERCHAN_SEND_KEY`，Value 粘贴 SendKey。
3. 看板：**Settings → Pages → Source: Deploy from a branch → main / docs**。
   几分钟后访问 `https://<你的用户名>.github.io/<仓库名>/`。
4. 手动跑一次验证：**Actions → Flight Radar → Run workflow**。
   跑完 `data/latest.json` 有数据、微信收到消息，就成功了。之后每天北京时间 8:10 / 20:10 自动运行。

## 改配置

全部在 `config.yaml`：出发地、目的地、周末模式、假期日期、提醒阈值、心理价位。
改完 push 即生效。

## 本地运行

```bash
pip install -r requirements.txt
python monitor.py --dry-run          # 不联网，测试流程
python monitor.py --only NGB --limit 10   # 真实查询（本地需能访问 Google）
```

## 已知限制

- 查的是 Google Flights 展示价，实际购买价以航司/代理为准，微信里的链接直达 Google Flights 对应搜索。
- fast-flights 是社区维护的爬虫，Google 改版时可能失效；失败率超过一半会收到告警，届时 `pip install -U fast-flights` 或看该项目 issues。
- 默认 3 出发地 × 22 目的地 × ~13 个日期 ≈ 860 次查询，每轮约 40–60 分钟。想更快就删目的地或减少 `weeks_ahead`。
- 春节等假期日期请按官方放假通知核对。
